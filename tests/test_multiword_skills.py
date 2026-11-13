"""Multiword Skills, source provenance, and noisy posting regression tests.

Product names are *not* maintained as a per-job whitelist. They are extracted
as complete noun spans and must be literally present in a selected, positively
attributed accomplishment as well as the employer's posting.
"""
import unittest

from resumeforge.models import Bullet, Candidate, Keyword, Profile, Role
from resumeforge.planning import analyze_job
from resumeforge.priorities import passages
from resumeforge.skills import select_skills


DINSMORE = """Systems Engineer
Responsibilities
Administer Microsoft 365 and Microsoft Entra ID services, including Exchange Online, SharePoint Online, Microsoft Teams, and related cloud systems.
Administer Microsoft Intune and Microsoft Defender for Endpoint.
Create and maintain PowerShell and VB scripts to automate administration.
Configure Conditional Access policies to secure enterprise identities.
Requirements
Experience administering Microsoft 365, Microsoft Entra ID, Exchange Online, SharePoint Online, Intune, and Microsoft Defender technologies.
Advanced troubleshooting knowledge of DNS, DHCP, static IP addressing and subnetting.
Microsoft 365, Azure, Microsoft security, CompTIA, or Cisco certifications preferred.
Equal Opportunity Employer
"""

WORK = [
    "Developed PowerShell scripts to automate monthly Exchange Online health checks, resolving 150 configuration issues.",
    "Designed and deployed Conditional Access policies in Microsoft Entra ID to secure 200 identities.",
    "Standardized SharePoint Online permissions and governance policies, eliminating redundant sites.",
]


def profile(skills=None, certifications="CompTIA Security+"):
    return Profile(
        name="Example", contact="example@invalid.example", skills=skills or
        ["Microsoft Azure", "AWS", "Linux/Unix", "REST APIs", "Drata",
         "OWASP ZAP", "OneTrust", "Datadog", "Python"],
        certifications=certifications,
        roles=[Role(id="r", company="Example", title="Systems Engineer", dates="2023-2026",
                    bullets=[Bullet(id="b", text="Configured a monitored infrastructure environment.")])])


def selected(texts=WORK):
    return [Candidate(id=f"idea:{i}", role_id="r", slot_id="b", origin="model-example",
                      text=text) for i, text in enumerate(texts)]


class MultiwordSkillsTests(unittest.TestCase):
    def test_selected_microsoft_platforms_appear_as_complete_names(self):
        ranked = select_skills(profile(), [Keyword(term="Microsoft 365 administration", weight=5)],
                               DINSMORE, selected())
        for name in ("Exchange Online", "Microsoft Entra ID", "Conditional Access",
                     "SharePoint Online", "PowerShell"):
            self.assertIn(name, ranked, (name, ranked))
        for not_demonstrated in ("Microsoft Teams", "Microsoft Defender for Endpoint",
                                 "Microsoft Intune", "Hyper-V"):
            self.assertNotIn(not_demonstrated, ranked, ranked)
        self.assertLess(ranked.index("Microsoft Entra ID"), ranked.index("OneTrust")
                        if "OneTrust" in ranked else 99)
        self.assertNotIn("Standardized", ranked)

    def test_no_promotion_of_unselected_examples(self):
        without_id = select_skills(profile(), [], DINSMORE, selected([WORK[0]]))
        self.assertIn("Exchange Online", without_id)
        self.assertNotIn("Microsoft Entra ID", without_id)
        self.assertNotIn("Conditional Access", without_id)
        self.assertNotIn("SharePoint Online", without_id)

    def test_no_promotion_from_job_only_or_other_persons_actions(self):
        candidates = selected([
            "Contractors administered Exchange Online for customers; I documented the rollout.",
            "We evaluated whether to migrate to Microsoft Entra ID."
        ])
        ranked = select_skills(profile(), [], DINSMORE, candidates)
        self.assertNotIn("Exchange Online", ranked)
        self.assertNotIn("Microsoft Entra ID", ranked)

    def test_unknown_multiword_products_work_in_other_professions(self):
        examples = [
            ("Use Oracle NetSuite for financial consolidation.",
             "Reconciled 30 accounts using Oracle NetSuite.", "Oracle NetSuite"),
            ("Administer Epic Hyperspace for clinical documentation.",
             "Configured Epic Hyperspace to improve chart access.", "Epic Hyperspace"),
            ("Configure SAP Transportation Management for shipments.",
             "Integrated SAP Transportation Management into freight routing.",
             "SAP Transportation Management"),
            ("Use Google Classroom to manage student assignments.",
             "Used Google Classroom to organize student feedback.", "Google Classroom"),
        ]
        for jd, accomplishment, target in examples:
            with self.subTest(target=target):
                ranked = select_skills(profile(["Python"]), [], jd, selected([accomplishment]))
                self.assertIn(target, ranked, ranked)

    def test_certification_provider_is_found_in_certifications_not_skills(self):
        rows = analyze_job(profile(), DINSMORE)
        term = next(x for x in rows if x["term"].casefold() == "comptia")
        self.assertEqual(term["evidence"], "exact", term)
        self.assertIn("CompTIA Security+", term["exact_certifications"])

    def test_job_parser_does_not_extract_boilerplate_or_ordinary_verbs(self):
        long_job = DINSMORE + """
Create and maintain technical runbooks for incident response.
Five or more years supporting enterprise infrastructure.
Ability to supervise and manage multiple ongoing projects.
Reliable attendance and flexibility are expected.
"""
        rows = analyze_job(profile(), long_job)
        names = [x["term"].casefold() for x in rows]
        for noise in ("five", "create", "equal opportunity employer",
                      "alternatively", "supervisors", "reliable attendance"):
            self.assertNotIn(noise, names, names)
        self.assertFalse(any(row.text.casefold() == "equal opportunity employer"
                             for row in passages(long_job)))


if __name__ == "__main__":
    unittest.main()
