"""The desktop workflow should offer clean, job-specific draft accomplishments."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from resumeforge.engine import run
from resumeforge.inspiration import Stories, _supports_adjacent_priority
from resumeforge.models import Keyword
from resumeforge.models import ModelSettings, Profile, RunRequest
from resumeforge.planning import analyze_job


SOURCE = Path(__file__).resolve().parents[1] / "examples" / "abu.profile.json"
JOB = """DevOps Engineer with Claude
Responsibilities
Build agentic engineering harnesses and automate software development lifecycle activities.
Design and operate CI/CD pipelines and infrastructure automation.
Required qualifications
Use AI-assisted development tools such as Claude Code CLI or GitHub Copilot.
Build agentic workflows, AI orchestration frameworks and cloud-native solutions.
Experience with CI/CD pipelines, scripting and platform integrations.
Preferred qualifications
Experience with incident response, observability and Model Context Protocol (MCP)."""


class InspirationTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.model_validate_json(SOURCE.read_text())
        self.terms = [r["term"] for r in analyze_job(self.profile, JOB)[:7]]

    def test_default_examples_replace_content_and_leave_source_intact(self):
        request = RunRequest(profile=self.profile, job_description=JOB, reviewed_priorities=self.terms)
        with tempfile.TemporaryDirectory() as tmp:
            result = run(request, Path(tmp))
            self.assertEqual(result["status"], "ready")
            examples = result["report"]["inspiration_bullets"]
            self.assertGreaterEqual(len(examples), 2)
            self.assertEqual(result["profile"], self.profile.model_dump())
            self.assertTrue(set(["Python", "AWS", "GitHub Actions", "Infrastructure as Code (IaC)"]) <= set(result["report"]["skills"]), result["report"]["skills"])
            pdf = PdfReader(Path(tmp) / "resume.pdf")
            self.assertEqual(len(pdf.pages), 1)
            text = " ".join(pdf.pages[0].extract_text().split())
            self.assertIn("Claude Code CLI", text)
            self.assertIn("LLM-powered Slack assistant", text)
            for c in examples:
                self.assertIn(c["text"], text)
            self.assertNotRegex(text.casefold(), r"fictional|placeholder|\[|\]")

    def test_model_story_must_support_its_target_not_a_second_unrelated_priority(self):
        priorities = [Keyword(term="Claude Code CLI"), Keyword(term="CI/CD"),
                      Keyword(term="SDLC automation")]
        self.assertTrue(_supports_adjacent_priority(
            "Used Claude Code CLI to draft 20 compliance controls.", "Claude Code CLI", priorities))
        self.assertTrue(_supports_adjacent_priority(
            "Used Claude Code CLI in CI/CD to reproduce 20 failing tests.", "Claude Code CLI", priorities))
        self.assertFalse(_supports_adjacent_priority(
            "Tracked customer service cases in a spreadsheet.", "Claude Code CLI", priorities))

    @patch("resumeforge.inspiration.ask")
    def test_configured_model_receives_reviewed_order_and_draft_is_editable(self, ask):
        bullet = "Built a Rust packet parser that reduced peak allocation by 31% during nightly traffic replay."
        ask.return_value = Stories(bullets=[{"slot":1, "concise":bullet, "detailed":bullet + " Added fuzz cases for malformed headers."}])
        req = RunRequest(profile=self.profile, job_description="Build secure integrations with AWS and Rust.",
                         reviewed_priorities=["Rust"], settings=ModelSettings(provider="ollama", model="fixture"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            initial = run(req, path / "first")
            call = ask.call_args.args
            self.assertEqual(call[3]["priority_order"], ["Rust"])
            self.assertEqual(call[3]["slots"][0]["priority"], "Rust")
            row = initial["report"]["inspiration_bullets"][0]
            self.assertEqual(row["origin"], "model-example")
            self.assertTrue(row["text"].startswith(bullet))
            continuation = RunRequest.model_validate({**req.model_dump(), "plan":initial["plan"],
                "draft_edits":{row["id"]:"Wrote Rust packet validation tests that reject 12 malformed header combinations."}})
            edited = run(continuation, path / "edited")
            self.assertEqual(edited["report"]["inspiration_bullets"][0]["origin"], "edited-example")
            self.assertEqual(ask.call_count, 1)
            grounded = continuation.model_copy(update={"settings":ModelSettings(wording_policy="verified"), "draft_edits":{}})
            verified = run(grounded, path / "verified")
            self.assertFalse(verified["report"]["inspiration_bullets"])
            self.assertNotIn("Rust packet", PdfReader(path / "verified" / "preview.pdf").pages[0].extract_text())
