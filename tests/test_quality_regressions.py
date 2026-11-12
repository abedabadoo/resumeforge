"""End-to-end regressions from DevOps, WAF, and Flexport tailoring reviews."""
import unittest
from unittest.mock import patch

from resumeforge.inspiration import _fallback, _story_choices, _awkward_label_paste
from resumeforge.job_analysis import Reading, analyze_posting
from resumeforge.models import Bullet, Keyword, ModelSettings, Plan, Profile, Role
from resumeforge.planning import analyze_job, bullet_relevance, rank_skills
from resumeforge.priorities import passages
from resumeforge.layout import Typesetter


FLEXPORT = """Product Security Engineer
What You'll Do
Define security architecture for products and services and set secure-by-default reference implementations.
Lead security engineering reviews for highest-risk product features.
Lead domain-specific threat modeling and attack surface analysis across the product surface.
Set the bar for triaging and prioritizing bug bounty submissions and drive remediation of systemic classes of vulnerability.
Build and scale the security champions program and product security training.
You Should Have
Strong grasp of web application security principles including OWASP Top 10.
Proficiency with application testing tools such as Burp Suite, OWASP ZAP or browser developer tools.
Working knowledge of at least one modern programming language (Python, Ruby or JavaScript) and one major cloud provider (AWS, GCP, Azure).
Nice to Have
Hands-on experience with SAST tools such as Semgrep or Snyk.
How We Work
We collaborate via Slack and async docs.
Why This Role Is Special
Engineering conventions are multiplied across hundreds of engineers.
California Pay Range
$130,950 - $202,125 USD
Global Data Privacy Notice
Applicants agree to GDPR and CCPA.
#LI-VA1"""


def profile():
    return Profile(
        name="Sample", contact="test@example.test",
        skills=["AWS", "Python", "OWASP ZAP", "Docker", "GitHub Actions",
                "Infrastructure as Code", "Salesforce", "Datadog"],
        interests="Cars, sewing, hockey",
        roles=[Role(id="r", company="Sample", title="Security Engineer", dates="2024-2026",
                    bullets=[
                        Bullet(id="a", text="Managed bug bounty program and triaged 200 submissions, reducing turnaround from four weeks to one."),
                        Bullet(id="b", text="Deployed recurring OWASP ZAP web application scans and routed vulnerabilities into remediation tracking."),
                        Bullet(id="c", text="Hardened AWS infrastructure as code and fixed production security findings."),
                        Bullet(id="d", text="Migrated a team Slack assistant to Claude."),
                    ])])


class EndToEndQualityRegressions(unittest.TestCase):
    def test_hiring_sections_exclude_compensation_legal_and_markers(self):
        rows = passages(FLEXPORT)
        cleaned = " ".join(row.text for row in rows).casefold()
        for unwanted in ("california pay range", "gdpr", "ccpa", "applicants",
                         "are multiplied", "li-va1", "$130,950"):
            self.assertNotIn(unwanted, cleaned)
        for needed in ("threat modeling", "security champions", "bug bounty"):
            self.assertIn(needed, cleaned)

    def test_security_capabilities_are_ranked_and_not_ddos(self):
        rows = analyze_job(profile(), FLEXPORT)
        terms = [row["term"] for row in rows]
        for expected in ("Product security architecture", "Security design reviews",
                         "Threat modeling and attack surface analysis",
                         "Vulnerability management and remediation", "Bug bounty triage",
                         "Web application security"):
            self.assertIn(expected, terms)
        self.assertNotIn("DDoS and bot mitigation", terms)
        self.assertNotIn("GDPR", terms)
        self.assertNotIn("CCPA", terms)
        self.assertNotIn("LI-VA1", terms)
        self.assertNotIn("Applicants", terms)
        self.assertTrue(all(t in terms[:20] for t in (
            "Product security architecture", "Threat modeling and attack surface analysis",
            "Vulnerability management and remediation")))

    def test_semantic_evidence_and_alternative_languages(self):
        rows = {r["term"]: r for r in analyze_job(profile(), FLEXPORT)}
        self.assertIn(rows["Vulnerability management and remediation"]["evidence"], ("exact", "related"))
        self.assertIn(rows["Bug bounty triage"]["evidence"], ("exact", "related"))
        self.assertIn(rows["Cloud infrastructure security"]["evidence"], ("exact", "related"))
        self.assertNotIn("Ruby", rows)
        self.assertNotIn("JavaScript", rows)

    def test_owasp_does_not_count_as_ddos(self):
        rows = analyze_job(profile(),
            "Web security engineer\nRequired qualifications\nExperience with OWASP Top 10 and OWASP ZAP.")
        self.assertNotIn("DDoS and bot mitigation", [r["term"] for r in rows])

    @patch("resumeforge.job_analysis.ask")
    def test_model_only_receives_hiring_sections(self, ask):
        ask.return_value = Reading(requirements=[])
        analyze_posting(profile(), FLEXPORT, [], ModelSettings(provider="ollama", model="fixture"))
        posting = ask.call_args.args[3]["posting"]
        self.assertNotIn("California Pay Range", posting)
        self.assertNotIn("GDPR", posting)
        self.assertIn("threat modeling", posting)

    def test_generic_keyword_insertion_fallback_is_disabled(self):
        self.assertFalse(_fallback("custom unknown domain capability", 0).concise)
        self.assertTrue(_awkward_label_paste(
            "Tracked outcomes for Threat Modeling & Attack Surface Analysis across 14 assignments.",
            "Threat Modeling & Attack Surface Analysis"))
        self.assertFalse(_awkward_label_paste(
            "Led threat modeling across six services and resolved architectural risks.",
            "Threat Modeling & Attack Surface Analysis"))
        examples = _story_choices([Keyword(term="Threat modeling and attack surface analysis")], 1)
        self.assertTrue(examples)
        self.assertIn("attack", examples[0][1].concise.casefold())

    def test_relevance_ranking_and_skills_core(self):
        priorities = [Keyword(term="Bug bounty triage", weight=5),
                      Keyword(term="Application security testing", weight=5),
                      Keyword(term="Cloud infrastructure security", weight=4)]
        p = profile()
        self.assertGreater(bullet_relevance(p.roles[0].bullets[0].text, priorities),
                           bullet_relevance(p.roles[0].bullets[3].text, priorities))
        selected = rank_skills(p, priorities)
        self.assertIn("OWASP ZAP", selected)
        self.assertIn("AWS", selected)
        self.assertIn("Docker", selected)

    def test_layout_leads_with_relevant_accomplishments_without_mutating_profile(self):
        p = profile()
        plan = Plan(keywords=[Keyword(term="Bug bounty triage", weight=5)],
                    candidates=[])
        from resumeforge.models import Candidate
        plan.candidates = [Candidate(id="source:" + b.id, role_id="r",
                            slot_id=b.id, text=b.text, evidence_ids=[b.id])
                           for b in p.roles[0].bullets]
        result = Typesetter().fit(p, plan, p.skills)
        self.assertTrue(result.selected)
        self.assertEqual(result.selected[0].slot_id, "a")
        self.assertEqual(p.interests, "Cars, sewing, hockey")
        self.assertFalse(any("Cars, sewing, hockey" in b.text for b in result.blocks))


if __name__ == "__main__":
    unittest.main()
