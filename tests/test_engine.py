"""Engine integration checks: real typesetting/PDF inspection, mocked network AI.

These tests do not establish real-model rewrite quality. They exercise the
measure/refine/review/export contract with actual rendered document geometry.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pdfplumber

from resumeforge.engine import merge_plans, run
from resumeforge.models import Candidate, Keyword, ModelSettings, Plan, Profile, Proposal, Review, RunRequest
from resumeforge.planning import build_plan


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    profile = Profile.model_validate_json((ROOT / "examples" / "abu.profile.json").read_text())
    plan = build_plan(profile, "", [], ModelSettings())
    return profile, plan


def short_plan(plan):
    """Four source-grounded concise alternatives, deliberately below full-page fit."""
    concise = [
        "Drove the annual internal audit to zero nonconformities.",
        "Ran SOC 2 and ISO 27001 evidence operations.",
        "Operationalized security monitoring in Datadog.",
        "Deployed weekly OWASP ZAP baseline scans on production.",
    ]
    chosen = [plan.candidates[i].model_copy(deep=True) for i in (0, 1, 6, 7)]
    for candidate, text in zip(chosen, concise):
        candidate.text = text
        candidate.rationale = "Concise source-grounded alternative for the integration fixture."
    return Plan(candidates=chosen)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.profile, self.plan = fixture()

    def test_source_only_full_page_is_export_ready_actual_pdf(self):
        result = run(RunRequest(profile=self.profile), self.output)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["report"]["geometry_passed"])
        self.assertTrue(result["report"]["quality_review"]["passed"])
        self.assertIsNone(result["report"]["model_used"])
        with pdfplumber.open(self.output / "resume.pdf") as pdf:
            self.assertEqual(len(pdf.pages), 1)
            self.assertIn("zero nonconformities", pdf.pages[0].extract_text())
            self.assertTrue(pdf.pages[0].chars)

    @patch("resumeforge.engine.review_content", return_value=Review(passed=True))
    @patch("resumeforge.engine.build_plan")
    def test_actual_render_refines_underfill_then_exports(self, build, review):
        build.side_effect = [short_plan(self.plan), self.plan]
        messages = []
        settings = ModelSettings(provider="ollama", model="mock-model", max_rounds=2)
        result = run(RunRequest(profile=self.profile, settings=settings), self.output, messages.append)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["report"]["iterations"]), 2)
        first, second = result["report"]["iterations"]
        self.assertTrue(first["geometry_passed"])  # safe one-page draft
        self.assertFalse(first["full_page_passed"])  # optional aesthetic target
        self.assertTrue(second["geometry_passed"])
        self.assertTrue(second["full_page_passed"])
        self.assertGreater(first["bottom_gap_pt"], second["bottom_gap_pt"])
        self.assertEqual(review.call_count, 2)
        self.assertIn("bottom_gap_pt", build.call_args.kwargs["feedback"])
        self.assertIn("ink_bottom_gap_pt", build.call_args.kwargs["feedback"])
        self.assertTrue((self.output / "pass-1.pdf").exists())
        self.assertTrue((self.output / "pass-2.pdf").exists())
        self.assertTrue((self.output / "resume.pdf").exists())
        self.assertTrue(any("revised wording" in m for m in messages))
        with pdfplumber.open(self.output / "pass-1.pdf") as first_pdf, pdfplumber.open(self.output / "pass-2.pdf") as second_pdf:
            first_sizes = {round(c["size"], 2) for c in first_pdf.pages[0].chars}
            second_sizes = {round(c["size"], 2) for c in second_pdf.pages[0].chars}
            self.assertEqual(first_sizes, second_sizes)

    def test_proposed_question_cannot_be_confirmed(self):
        self.plan.proposed_claims.append(Proposal(id="q", role_id=self.profile.roles[0].id,
            text="Have you used Prometheus in this role?", reason="No source evidence."))
        with self.assertRaisesRegex(ValueError, "actual accomplishment"):
            run(RunRequest(profile=self.profile, plan=self.plan, confirmed_claim_ids=["q"]), self.output)
        self.assertFalse((self.output / "resume.pdf").exists())

    def test_confirmation_cannot_shadow_original_evidence_id(self):
        self.profile.roles[0].bullets[0].id = "confirmed:collision"
        self.plan = build_plan(self.profile, "", [], ModelSettings())
        self.plan.proposed_claims.append(Proposal(id="collision", role_id=self.profile.roles[0].id,
            text="Implemented Prometheus alerts for application latency and documented response procedures.",
            reason="User supplied proposal."))
        with self.assertRaisesRegex(ValueError, "existing source bullet"):
            run(RunRequest(profile=self.profile, plan=self.plan, confirmed_claim_ids=["collision"]), self.output)
        self.assertFalse((self.output / "resume.pdf").exists())

    def test_unconfirmed_proposal_and_candidate_are_excluded(self):
        role = self.profile.roles[0]
        self.plan.proposed_claims.append(Proposal(id="pending", role_id=role.id,
            text="Implemented Prometheus observability dashboards for production services.",
            reason="Awaiting user confirmation."))
        self.plan.candidates.append(Candidate(id="pending-candidate", role_id=role.id,
            slot_id=role.bullets[0].id, text="Implemented Prometheus dashboards for production services.",
            evidence_ids=[role.bullets[0].id], needs_confirmation=True))
        result = run(RunRequest(profile=self.profile, plan=self.plan), self.output)
        self.assertEqual(result["status"], "ready")
        selected = json.loads((self.output / "selected.json").read_text())
        self.assertNotIn("pending-candidate", [c["id"] for c in selected])
        with pdfplumber.open(self.output / "resume.pdf") as pdf:
            self.assertNotIn("Prometheus", pdf.pages[0].extract_text())
        self.assertTrue(any("Unconfirmed" in w for w in result["report"]["warnings"]))

    def test_confirmed_proposal_becomes_exact_role_evidence(self):
        role = self.profile.roles[0]
        text = "Implemented Prometheus alerts for application latency and documented operational response procedures."
        self.plan.proposed_claims.append(Proposal(id="approved", role_id=role.id, text=text,
            reason="User supplied actual experience.", keywords=["Prometheus"]))
        self.plan.keywords = [Keyword(term="Prometheus", kind="tool", weight=5)]
        result = run(RunRequest(profile=self.profile, plan=self.plan,
                               confirmed_claim_ids=["approved"]), self.output)
        fact = next(f for f in result["profile"]["facts"] if f["id"] == "confirmed:approved")
        self.assertEqual(fact["text"], text)
        self.assertEqual(fact["role_id"], role.id)
        selected = json.loads((self.output / "selected.json").read_text())
        candidate = next(c for c in selected if c["id"] == "confirmed:approved")
        self.assertEqual(candidate["evidence_ids"], ["confirmed:approved"])
        self.assertEqual(candidate["slot_id"], "fact:confirmed:approved")
        self.assertEqual(result["report"]["confirmed_claim_ids"], ["approved"])

    @patch("resumeforge.engine.review_content", return_value=Review(passed=False, issues=["Unsupported ownership claim."]))
    def test_semantic_review_failure_blocks_final_export(self, review):
        settings = ModelSettings(provider="ollama", model="mock-model", max_rounds=1)
        # A stale successful file must not survive a failed rerun in this directory.
        (self.output / "resume.pdf").write_bytes(b"stale")
        import hashlib
        (self.output / "result.json").write_text(json.dumps({'report':{'pdf_sha256':hashlib.sha256(b'stale').hexdigest()}}))
        result = run(RunRequest(profile=self.profile, plan=self.plan, settings=settings), self.output)
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(result["report"]["geometry_passed"])
        self.assertFalse((self.output / "resume.pdf").exists())
        self.assertTrue((self.output / "preview.pdf").exists())

    def test_unsupported_plan_evidence_fails_before_export(self):
        self.plan.candidates[0].evidence_ids = ["missing"]
        with self.assertRaisesRegex(ValueError, "same job"):
            run(RunRequest(profile=self.profile, plan=self.plan), self.output)
        self.assertFalse((self.output / "resume.pdf").exists())

    def test_merge_revises_same_id_without_mutating_earlier_plan(self):
        old_text = self.plan.candidates[0].text
        new = short_plan(self.plan)
        merged = merge_plans(self.plan, new)
        self.assertEqual(len({c.id for c in merged.candidates}), len(merged.candidates))
        self.assertEqual(merged.candidates[0].text, new.candidates[0].text)
        self.assertEqual(self.plan.candidates[0].text, old_text)

    @patch("resumeforge.engine.review_content", return_value=Review(passed=False, issues=["Fixture quality failure."]))
    @patch("resumeforge.engine.build_plan")
    def test_best_pass_keeps_its_own_plan_after_id_revision(self, build, review):
        build.return_value = short_plan(self.plan)
        settings = ModelSettings(provider="ollama", model="mock-model", max_rounds=2)
        result = run(RunRequest(profile=self.profile, plan=self.plan, settings=settings), self.output)
        self.assertEqual(len(result["report"]["iterations"]), 2)
        self.assertEqual(result["plan"]["candidates"][0]["text"], self.plan.candidates[0].text)
        self.assertEqual(result["report"]["bottom_gap_pt"], result["report"]["iterations"][0]["bottom_gap_pt"])
        self.assertEqual(result["status"], "needs_review")
        self.assertFalse((self.output / "resume.pdf").exists())


if __name__ == "__main__":
    unittest.main()
