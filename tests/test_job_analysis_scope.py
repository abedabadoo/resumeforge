"""Focused Job Analysis guards, using synthetic cross-domain security postings.

These tests prevent broad extraction failures rather than memorizing any
individual employer's job advertisement.
"""
import unittest
from unittest.mock import patch

from resumeforge.job_analysis import Reading, Requirement, analyze_posting
from resumeforge.models import Bullet, ModelSettings, Profile, Role
from resumeforge.planning import _role_title_evidence, analyze_job
from resumeforge.priorities import passages


class JobAnalysisSafetyTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(
            name="Example Applicant", contact="example@test.invalid",
            roles=[Role(id="r", title="Security Engineer",
                        company="Sample Platform", dates="2023 - 2026",
                        bullets=[Bullet(id="b", text="Investigated security incidents and maintained response playbooks.")])],
            skills=["Python", "AWS"])

    def test_about_company_heading_ends_requirement_section(self):
        posting = """Detection Platform Engineer
Required Qualifications
Experience with cloud security monitoring.
About Blue Fern Systems:
We build products for financial institutions.
INDSWE
Preferred Qualifications
Familiarity with Splunk."""
        sections = passages(posting)
        text = [row.text for row in sections]
        self.assertFalse(any("financial institutions" in item for item in text))
        self.assertFalse(any("INDSWE" in item for item in text))
        self.assertEqual(next(row.section for row in sections if "Splunk" in row.text), "preferred")
        self.assertEqual(next(row.section for row in sections if "monitoring" in row.text), "required")

    def test_about_role_is_not_discarded_as_company_description(self):
        posting = """Cloud Response Engineer
About the role
Design security alert pipelines.
About Alder Labs
We're a software company.
Required qualifications
Experience with Python."""
        rows = passages(posting)
        self.assertTrue(any("alert pipelines" in row.text for row in rows))
        self.assertFalse(any("software company" in row.text for row in rows))
        self.assertEqual(next(row.section for row in rows if "Python" in row.text), "required")

    def test_optional_vendor_is_not_a_required_skill(self):
        posting = """Threat Detection Engineer
Required qualifications
Experience implementing alert enrichment.
Desired Skills / Certifications
Familiarity with Splunk and Elastic."""
        results = analyze_job(self.profile, posting)
        vendor = next((x for x in results if x["term"] == "Splunk"), None)
        if vendor:
            self.assertFalse(vendor["required"])

    def test_role_titles_are_related_support_not_tenure_proof(self):
        matches = _role_title_evidence(
            "security engineering, red team, or SOC work", self.profile.roles)
        self.assertEqual(len(matches), 1)
        self.assertIn("Security Engineer", matches[0])
        self.assertEqual(_role_title_evidence("cloud data engineering", self.profile.roles), [])
        posting = """Cybersecurity Engineer
Required qualifications
Experience in security engineering."""
        result = analyze_job(self.profile, posting)
        matched = [r for r in result if r["term"].casefold() == "security engineering"]
        self.assertTrue(matched)
        self.assertIn(matched[0]["evidence"], ("related", "exact"))
        self.assertTrue(matched[0]["role_matches"])

    @patch("resumeforge.job_analysis.ask")
    @patch("resumeforge.job_analysis.analyze_job", return_value=[])
    def test_model_cannot_invent_unquoted_waf_specialization(self, _analysis, ask):
        job = """Incident Investigation Engineer
Responsibilities
Support incident response investigations and write remediation plans."""
        ask.return_value = Reading(requirements=[
            Requirement(capability="WAF incident response",
                        quote="Support incident response investigations and write remediation plans")])
        result = analyze_posting(self.profile, job, [],
                                 ModelSettings(provider="ollama", model="fixture"))
        self.assertEqual(result, [])

    @patch("resumeforge.job_analysis.ask")
    @patch("resumeforge.job_analysis.analyze_job", return_value=[])
    def test_model_can_add_source_quoted_novel_capability(self, _analysis, ask):
        job = """Security Operations Engineer
Responsibilities
Investigate security alerts and document remediation outcomes."""
        ask.return_value = Reading(requirements=[
            Requirement(capability="investigate security alerts",
                        quote="Investigate security alerts and document remediation outcomes")])
        result = analyze_posting(self.profile, job, [],
                                 ModelSettings(provider="ollama", model="fixture"))
        self.assertEqual(result[0]["term"], "investigate security alerts")


if __name__ == "__main__":
    unittest.main()
