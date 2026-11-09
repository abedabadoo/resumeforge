"""Posting analysis regressions across technical and operational roles."""
import unittest

from resumeforge.models import Bullet, Profile, Role
from resumeforge.planning import analyze_job, reviewed_priorities


def profile():
    return Profile(name="Sample", contact="", skills=["Microsoft Azure", "GitHub Actions", "Datadog", "Python"],
                   roles=[Role(id="dev", company="Demo", title="Engineer", dates="", bullets=[
                       Bullet(id="a", text="Built a Claude assistant for operations and evaluated AI code-review tools."),
                       Bullet(id="b", text="Completed vendor risk reviews and configured SLO alerts in Datadog.")])])


class JobPriorities(unittest.TestCase):
    def test_role_specialty_and_required_capabilities_outrank_tool_examples(self):
        job = """DevOps Engineer with Claude
Responsibilities
Build agentic engineering harnesses for SDLC automation.
Required qualifications
Experience with AI-assisted development tools such as Claude Code CLI, Cursor or Aider.
Build agentic workflows and CI/CD pipelines.
Preferred qualifications
Experience with Model Context Protocol (MCP) and Azure DevOps."""
        results = analyze_job(profile(), job)
        rows = {r["term"]: r for r in results}
        terms = list(rows)
        self.assertTrue(all(terms.index(k) < terms.index("MCP") for k in
                            ["Claude Code CLI", "Agentic engineering harnesses", "CI/CD"]))
        self.assertEqual(rows["Claude Code CLI"]["evidence"], "related")
        self.assertEqual(rows["Azure DevOps"]["evidence"], "missing")
        self.assertNotIn("Azure", rows)
        self.assertEqual(rows["CI/CD"]["related_skills"], ["GitHub Actions"])
        self.assertIn("agentic workflows", rows["Agentic engineering harnesses"]["terms"])

    def test_nontech_short_qualification_lists_and_context(self):
        for job, required, preferred in [
            ("Collections Coordinator\nRequired: Invoice reconciliation, customer outreach and payment arrangements.\nPreferred: Salesforce.",
             {"invoice reconciliation", "customer outreach", "payment arrangements"}, "Salesforce"),
            ("Registered Nurse\nRequired qualifications\nPatient assessment, medication administration, and discharge planning.\nPreferred: Epic.",
             {"patient assessment", "medication administration", "discharge planning"}, "Epic"),
        ]:
            with self.subTest(job=job):
                rows = analyze_job(profile(), job)
                self.assertEqual({r["term"].casefold() for r in rows[:3]}, required)
                self.assertTrue(all(r["required"] for r in rows[:3]))
                self.assertEqual(rows[-1]["term"], preferred)

    def test_user_shortlist_replaces_suggestions_in_supplied_order(self):
        job = "DevOps Engineer\nRequirements: AWS and CI/CD.\nPreferred: Azure DevOps."
        picked = reviewed_priorities(profile(), job, ["REST APIs", "custom integration", "AWS"])
        self.assertEqual([k.term for k in picked], ["REST API", "custom integration", "AWS"])
        self.assertEqual(reviewed_priorities(profile(), job, []), [])

    def test_explicit_nonuse_is_not_source_evidence(self):
        source = profile()
        source.roles[0].bullets.append(Bullet(id="c", text="Ran GitHub Actions, but never used Azure DevOps."))
        rows = {r["term"]: r for r in analyze_job(source, "Required: Azure DevOps, GitHub Actions.")}
        self.assertEqual(rows["Azure DevOps"]["evidence"], "missing")
        self.assertIn("c", rows["GitHub Actions"]["evidence_ids"])

    def test_related_evidence_is_distinct_from_an_exact_skill(self):
        rows = {r["term"]: r for r in analyze_job(profile(), "Required: risk management, observability, and Datadog.")}
        self.assertEqual(rows["risk management"]["evidence_ids"], ["b"])
        self.assertEqual(rows["risk management"]["evidence"], "related")
        self.assertEqual(rows["observability"]["evidence"], "related")
        self.assertEqual(rows["Datadog"]["evidence"], "exact")
