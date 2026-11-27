import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from resumeforge import cover_research
from resumeforge import cover_workflow as letters
from resumeforge.cover_letter import workspace_role_folder
from resumeforge.engine import run
from resumeforge.models import ModelSettings, Profile, RunRequest


class CoverWorkflowTests(unittest.TestCase):
    def test_corrections_keep_other_paragraphs_and_require_an_exact_anchor(self):
        opening = "This paragraph relates our release monitoring work to the posting."
        unsupported = "I led the identity review program for the entire organization."
        supported = "I would bring my experience checking deployment records to your identity reviews."
        draft = letters.LetterProse(paragraphs=[opening, unsupported], source_number=0)
        changes = [
            {
                "paragraph": 1,
                "original": "This opening was entirely different.",
                "replacement": "This change must have no effect.",
            },
            {"paragraph": 2, "original": unsupported, "replacement": supported},
        ]
        with patch.object(letters, "call_json", return_value={"changes": changes}):
            corrected = letters._correct_prose(
                draft, "The claim overstates ownership.", ModelSettings(), {}
            )
        self.assertEqual(corrected.paragraphs, [opening, supported])

    def test_checked_resume_creates_role_specific_letter_and_keeps_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            checked = workspace / "runs" / ("a" * 32)
            profile = Profile.model_validate_json(
                (
                    Path(letters.__file__).with_name("data") / "abu.profile.json"
                ).read_text()
            )
            description = (
                "Build AWS release pipelines and Python automation. Improve monitoring, "
                "incident response, and test environments for application teams."
            )
            company, title = "Signal Orchard", "Platform Engineer"
            result = run(
                RunRequest(
                    profile=profile,
                    settings=ModelSettings(),
                    job_description=description,
                ),
                checked,
            )
            self.assertEqual(result["status"], "ready")
            with patch.object(Path, "home", lambda: root):
                folder = workspace_role_folder(company, title, workspace, description)
                distinct = workspace_role_folder(
                    company, title, workspace, "A separate posting"
                )
            self.assertNotEqual(folder, distinct)
            self.assertEqual(folder.parent, distinct.parent)
            context = letters.LetterWorkspace(
                workspace,
                checked,
                folder / letters.RESUME_NAME,
                company,
                title,
                description,
                ModelSettings(provider="ollama", model="fixture"),
            )
            knowledge = {
                "sources": [],
                "hiring_manager": None,
                "message": "No company source was verified.",
            }
            sentence = (
                "Releasing a change safely means connecting reliable test environments with useful "
                "monitoring evidence and giving the team a way to investigate a regression. "
            )
            for length in range(3, 12):
                draft = letters.LetterProse(
                    paragraphs=[
                        sentence.strip() * 1 + (" " + sentence.strip()) * (length - 1)
                    ]
                    * 4,
                    source_number=0,
                )
                text = letters._merge_text(context, draft, knowledge)
                if letters._typeset(context, text, root / "measure.pdf")[
                    "full_page_passed"
                ]:
                    break
            else:
                self.fail("The test letter could not fill the locked layout.")
            self.assertFalse(context.letter.exists())
            with (
                patch.object(letters, "research", return_value=knowledge),
                patch.object(
                    letters,
                    "call_json",
                    side_effect=[draft.model_dump(), {"issues": []}],
                ),
            ):
                state = context.generate(0)
            self.assertTrue(state["ready"])
            self.assertEqual(len(PdfReader(context.letter).pages), 1)
            saved_resume = context.resume.read_bytes()
            self.assertEqual(saved_resume, (checked / "resume.pdf").read_bytes())
            before = context.letter.read_bytes()
            revised = context.save(
                "Dear Hiring Team,\n\nAn unfinished revision.", state["revision"]
            )
            self.assertFalse(revised["ready"])
            self.assertIn("unfinished revision", context.state()["draft"]["text"])
            self.assertEqual(context.letter.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "Confirm replacing"):
                context.generate(revised["revision"])

    def test_public_research_uses_explicit_posting_recruiter_and_relevant_company_article(
        self,
    ):
        posting = "https://jobs.signalorchard.example/jobs/engineer"
        article = "https://signalorchard.example/news/monitoring"
        pages = {
            posting: "<p>Hiring manager: Dana Bell</p>"
            "<p>Alicia Example is the communications director.</p>",
            article: '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "NewsArticle",
                    "datePublished": "2025-10-03",
                    "headline": "Release monitoring and automation",
                    "description": "The release monitoring project sends automation evidence to engineering teams.",
                }
            )
            + "</script>",
        }
        with patch.object(
            cover_research,
            "_read_page",
            side_effect=lambda url, _, **kw: (cover_research._parse(pages[url]), url),
        ):
            result = cover_research.research(
                "Signal Orchard", "Release monitoring and automation.", posting, article
            )
        self.assertEqual(result["sources"][0]["url"], article)
        self.assertEqual(result["hiring_manager"]["name"], "Dana Bell")
        with patch.object(cover_research, "_read_page", side_effect=TimeoutError):
            unavailable = cover_research.research(
                "Signal Orchard", "Release monitoring.", posting, article
            )
        self.assertFalse(unavailable["sources"])
        self.assertIsNone(unavailable["hiring_manager"])
