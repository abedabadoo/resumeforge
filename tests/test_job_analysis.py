"""Regression for a local model elevating secondary duties above mandatory work."""
import unittest
from unittest.mock import patch

from resumeforge.job_analysis import Reading, Requirement, analyze_posting
from resumeforge.models import Bullet, ModelSettings, Profile, Role


class ModelPriorities(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(name="Sample", contact="", skills=["AWS", "Python", "GitHub Actions"],
            roles=[Role(id="r", company="Example", title="Engineer", dates="",
                        bullets=[Bullet(id="b", text="Used AWS to provision test environments.")])])
        self.settings = ModelSettings(provider="ollama", model="example")
        self.job = """DevOps Engineer
Required qualifications
Build CI/CD pipelines and infrastructure automation.
Strong programming and scripting skills.
Responsibilities
Implement human-in-the-loop controls.
Preferred qualifications
Experience with Model Context Protocol (MCP)."""

    def test_required_capabilities_survive_optional_model_picks_and_aliases(self):
        findings = Reading(requirements=[
            Requirement(capability="MCP", quote="Experience with Model Context Protocol (MCP)."),
            Requirement(capability="human-in-the-loop controls", quote="Implement human-in-the-loop controls."),
            Requirement(capability="CI/CD pipelines", quote="Build CI/CD pipelines and infrastructure automation."),
            Requirement(capability="data governance", quote="Build CI/CD pipelines and infrastructure automation."),
        ])
        with patch("resumeforge.job_analysis.ask", return_value=findings):
            rows = analyze_posting(self.profile, self.job, [], self.settings)
        terms = [r["term"] for r in rows]
        self.assertEqual(terms[0], "CI/CD")
        self.assertNotIn("CI/CD pipelines", terms)
        self.assertNotIn("data governance", terms)
        self.assertEqual(rows[0]["posting_quote"], findings.requirements[2].quote)
        self.assertTrue(all(terms.index(t) < terms.index("MCP")
                            for t in ["Infrastructure as Code", "Programming and scripting"]))
        infrastructure = next(r for r in rows if r["term"] == "Infrastructure as Code")
        self.assertIn("AWS", infrastructure["related_skills"])

    def test_model_can_supply_a_required_capability_with_a_real_quote(self):
        job = "Required qualifications\nUse an isotope ratio spectrometer to confirm sample composition."
        reading = Reading(requirements=[Requirement(capability="isotope ratio spectrometer",
                                    quote="Use an isotope ratio spectrometer to confirm sample composition.")])
        with patch("resumeforge.job_analysis.analyze_job", return_value=[]), \
             patch("resumeforge.job_analysis.ask", return_value=reading):
            rows = analyze_posting(self.profile, job, [], self.settings)
        self.assertEqual([r["term"] for r in rows], ["isotope ratio spectrometer"])
        self.assertTrue(rows[0]["required"])
