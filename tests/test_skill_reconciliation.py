"""Hold-out tests for the Skills section across unrelated occupations."""
import tempfile
import unittest
from pathlib import Path

from resumeforge.engine import _fit_reconciled_skills
from resumeforge.layout import Typesetter
from resumeforge.models import Bullet, Candidate, Keyword, ModelSettings, Plan, Profile, Role, RunRequest
from resumeforge.planning import rank_skills, selected_skills
from resumeforge.skills import choices, select_skills


SECURITY_POSTING = """Security Automation Engineer
Position Responsibilities:
Develop integrations using REST APIs, webhooks, SDKs, Python and PowerShell.
Design automation across SIEM, SOAR, identity, cloud and ticketing platforms.
Automate Jira case creation and endpoint evidence collection with Intune.
Implement secure authentication, access restrictions and audit logging.
Maintain automation code with Git, testing, and code review.
Other Qualifications:
Experience with Azure, LLMs, CI/CD pipelines and data automation.
"""

def security_profile():
    return Profile(name="Example", contact="example@test.invalid",
        roles=[Role(id="r", company="Example", title="Security Engineer", dates="2024 - 2026",
                    bullets=[Bullet(id="source", text="Built incident-response alert ingestion, runbooks and detection workflows.")])],
        skills=["AWS", "Docker", "Drata", "Git", "Infrastructure as Code (IaC)",
                "ISO/IEC 27001", "Linux/Unix", "LLM", "MongoDB", "OWASP ZAP",
                "REST APIs", "RBAC", "Salesforce", "SAML", "SOC 2 Type II Compliance",
                "SQL", "Tableau", "TCP/IP", "Vulnerability Analysis", "OneTrust",
                "Gitlab", "Google Cloud Platform", "Microsoft Azure", "Python",
                "Datadog", "GitHub Actions"])


def selected_tools():
    return [Candidate(id="example:siem", role_id="r", slot_id="source",
                      origin="model-example", evidence_ids=["source"],
                      text="Automated Jira case creation from SIEM alerts and removed 200 manual tickets weekly."),
            Candidate(id="example:investigation", role_id="r", slot_id="new",
                      origin="model-example", evidence_ids=["source"],
                      text="Developed a PowerShell script integrated with Intune to collect forensic artifacts from endpoints.")]


class SkillReconciliationTests(unittest.TestCase):
    def test_job_explicit_tools_outrank_unrelated_inventory(self):
        p = security_profile()
        ranked = select_skills(p, [
            Keyword(term="Automation workflows", weight=5),
            Keyword(term="API integrations", weight=5),
            Keyword(term="Evidence collection", weight=4)],
            job_description=SECURITY_POSTING, selected=selected_tools())
        for skill in ("Python", "REST APIs", "Git", "PowerShell", "Intune", "Jira"):
            self.assertIn(skill, ranked)
            self.assertLess(ranked.index(skill), ranked.index("Salesforce") if "Salesforce" in ranked else 99,
                            skill)
        self.assertNotIn("case creation", ranked)
        self.assertNotIn("ITAR", ranked)
        self.assertNotIn("SOAR", ranked)  # no demonstrated use
        self.assertLessEqual(len(ranked), 18)

    def test_only_selected_examples_promote_new_tools(self):
        p = security_profile()
        none_selected = [selected_tools()[0]]
        first = select_skills(p, [Keyword(term="Investigation", weight=5)],
                              job_description=SECURITY_POSTING, selected=none_selected)
        second = select_skills(p, [Keyword(term="Investigation", weight=5)],
                               job_description=SECURITY_POSTING, selected=selected_tools())
        self.assertNotIn("PowerShell", first)
        self.assertNotIn("Intune", first)
        self.assertIn("PowerShell", second)
        self.assertIn("Intune", second)

    def test_source_aliases_are_not_duplicated(self):
        p = security_profile()
        p.skills = ["Amazon Web Services", "AWS", "REST APIs", "REST API",
                    "Infrastructure as Code (IaC)", "IaC", "Python"]
        ranked = select_skills(p, ["AWS", "REST API", "Infrastructure as Code"])
        self.assertEqual(len(ranked), 4)
        self.assertIn("Amazon Web Services", ranked)
        self.assertNotIn("AWS", ranked)
        self.assertEqual(sum("Infrastructure" in skill for skill in ranked), 1)

    def test_model_skill_order_cannot_readd_low_value_skills(self):
        p = security_profile()
        plan = Plan(keywords=[Keyword(term="Python", weight=5),
                              Keyword(term="REST API", weight=5)],
                    skill_order=list(reversed(p.skills)))
        ranked = selected_skills(p, plan, ModelSettings(provider="ollama", strategy="laptop"),
                                 job_description=SECURITY_POSTING)
        self.assertEqual(ranked[:2], ["Python", "REST APIs"] if ranked[0] == "Python"
                         else ["REST APIs", "Python"])
        self.assertLessEqual(len(ranked), 18)
        self.assertTrue(set(ranked) <= set(p.skills))

    def test_new_brand_names_generalize_to_accounting_and_healthcare(self):
        accountant = Profile(name="Test", contact="e@test.invalid", skills=["Excel"],
                             roles=[Role(id="r", company="Example", title="Accountant",
                                         dates="2022-2026", bullets=[Bullet(id="b", text="Processed invoices.")])])
        nurses = Profile(name="Test", contact="e@test.invalid", skills=["Clinical documentation"],
                         roles=[Role(id="r", company="Example", title="Nurse",
                                     dates="2022-2026", bullets=[Bullet(id="b", text="Monitored patient vitals.")])])
        accounting = "Reconcile financial statements using NetSuite and maintain audit logs."
        nursing = "Administer medication and maintain clinical documentation in Epic."
        accounting_candidate = Candidate(id="a", role_id="r", slot_id="b", origin="model-example",
                                         text="Reconciled monthly accounts using NetSuite.", evidence_ids=["b"])
        nursing_candidate = Candidate(id="n", role_id="r", slot_id="b", origin="model-example",
                                      text="Used Epic to document inpatient assessments.", evidence_ids=["b"])
        self.assertIn("NetSuite", select_skills(accountant, [], accounting, [accounting_candidate]))
        self.assertIn("Epic", select_skills(nurses, [], nursing, [nursing_candidate]))
        self.assertNotIn("NetSuite", select_skills(accountant, [], accounting))

    def test_no_new_skill_from_proposals_or_unsupported_job_list(self):
        p = security_profile()
        result = select_skills(p, [Keyword(term="Splunk", weight=5, kind="tool"),
                                  Keyword(term="SOAR", weight=5, kind="tool")],
                               job_description="Required: Splunk, SOAR and PowerShell.",
                               selected=[])
        for absent in ("Splunk", "SOAR", "PowerShell"):
            self.assertNotIn(absent, result)

    def test_final_layout_reconciles_selected_technical_example(self):
        p = Profile(name="Example", contact="test@example.test", skills=["Excel", "Python"],
                    roles=[Role(id="r", company="Example", title="Engineer", dates="2023-2026",
                                bullets=[Bullet(id="a", text="Wrote scripts to automate a reporting workflow.")])])
        candidate = Candidate(id="example", role_id="r", slot_id="a",
                              origin="model-example", evidence_ids=["a"], quality=1,
                              text="Developed automation scripts using PowerShell and Jira integrations.")
        plan = Plan(keywords=[Keyword(term="PowerShell", weight=5, kind="tool")],
                    candidates=[candidate])
        request = RunRequest(profile=p, plan=plan,
                             job_description="Develop PowerShell integrations using Jira.")
        base = selected_skills(p, plan, request.settings,
                               job_description=request.job_description)
        selection, final = _fit_reconciled_skills(Typesetter(), p, plan, base,
                                                 frozenset({"a"}), request)
        self.assertTrue(selection.feasible)
        self.assertIn("PowerShell", final)
        self.assertIn("Jira", final)
        self.assertTrue(any(c.id == "example" for c in selection.selected))

    def test_no_stale_interests_section_heading(self):
        p = security_profile()
        p.interests = "Painting"
        blocks = Typesetter().blocks(p.model_copy(update={"interests": ""}), [], ["Python", "REST APIs"])
        headings = [block.text for block in blocks if block.kind == "heading"]
        self.assertIn("SKILLS", " ".join(headings))
        self.assertNotIn("INTERESTS", " ".join(headings))


if __name__ == "__main__":
    unittest.main()
