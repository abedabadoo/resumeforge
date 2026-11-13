"""Regression tests for the export-blocking Tenet3 preview failure.

Page fill is a style objective. A valid single-page PDF must export even if
the optimizer cannot fill its final 13.2-point band exactly.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pdfplumber

from resumeforge.engine import run
from resumeforge.job_analysis import Reading, Requirement, analyze_posting
from resumeforge.layout import clean
from resumeforge.models import Bullet, Keyword, ModelSettings, Plan, Profile, Role, RunRequest
from resumeforge.planning import selected_skills
from resumeforge.priorities import passages


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return Profile.model_validate_json((ROOT / "examples" / "abu.profile.json").read_text())


class AutomaticExportRecoveryTests(unittest.TestCase):
    def test_source_cid_artifact_is_cleaned_before_render_and_review(self):
        profile = fixture()
        bullet = profile.roles[-1].bullets[-1]
        bullet.text = bullet.text + " / (cid:11) ISO 27001"
        original = bullet.text
        self.assertNotIn("(cid:11)", clean(original))

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result = run(RunRequest(profile=profile), directory)
            self.assertEqual(result["status"], "ready", result["report"]["issues"])
            self.assertTrue(result["report"]["bounds_passed"])
            self.assertTrue((directory / "resume.pdf").exists())
            with pdfplumber.open(directory / "resume.pdf") as pdf:
                contents = pdf.pages[0].extract_text() or ""
            self.assertNotIn("(cid:11)", contents)
            self.assertIn("ISO 27001", contents)
        # The original user-supplied profile object remains untouched.
        self.assertEqual(bullet.text, original)

    def test_long_laptop_skill_order_does_not_override_relevance_pruning(self):
        profile = fixture()
        plan = Plan(
            keywords=[Keyword(term="Infrastructure as Code", weight=5),
                      Keyword(term="CI/CD", weight=5),
                      Keyword(term="Datadog", weight=4)],
            skill_order=list(profile.skills))
        settings = ModelSettings(provider="ollama", model="test-model", strategy="laptop")
        ranked = selected_skills(profile, plan, settings)
        self.assertLessEqual(len(ranked), 18)
        self.assertIn("Datadog", ranked)

    @patch("resumeforge.job_analysis.ask")
    def test_model_paraphrase_gets_related_source_evidence(self, ask):
        profile = fixture()
        listing = """DevOps Engineer
Essential Responsibilities
Develop, maintain, and optimize infrastructure-as-code (IaC) for repeatable and secure cloud deployments.
Required Skills & Qualifications
Experience with CI/CD pipelines and observability tools."""
        quote = "Develop, maintain, and optimize infrastructure-as-code (IaC) for repeatable and secure cloud deployments"
        ask.return_value = Reading(requirements=[Requirement(
            capability="Infrastructure-as-Code (IaC) development and optimization",
            quote=quote)])
        result = analyze_posting(profile, listing, [],
                                 ModelSettings(provider="ollama", model="test-model"))
        matched = [row for row in result if row["term"] ==
                   "Infrastructure-as-Code (IaC) development and optimization"]
        self.assertTrue(matched)
        self.assertEqual(matched[0]["evidence"], "related")
        self.assertNotIn("Essential Responsibilities", [row["term"] for row in result])
        self.assertNotIn("Required Skills & Qualifications", [row["term"] for row in result])
        self.assertFalse(any(row.text == "Essential Responsibilities"
                             for row in passages(listing)))


if __name__ == "__main__":
    unittest.main()
