"""Full-page composition and occupation-neutral coverage regressions.

The live model can vary wording, so these tests assert measurable contracts:
  * all fixed template values remain constant,
  * previously empty layout space triggers selected-source rewrites,
  * partial pages cannot claim to be final in a powered job-targeted run,
  * the page optimizer gives novel requirements credit, not just repeated tools.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from resumeforge.engine import run
from resumeforge.example_refit import refit_examples
from resumeforge.inspiration import Stories, Story
from resumeforge.job_analysis import Reading, Requirement, analyze_posting, _concise_capability
from resumeforge.layout import Typesetter
from resumeforge.models import Bullet, Candidate, Keyword, ModelSettings, Plan, Profile, Review, Role, RunRequest, Template
from resumeforge.planning import bullet_relevance
from resumeforge.requirement_extraction import extract, without_experience_duration
from resumeforge.priorities import passages


def small_profile():
    return Profile(
        name="Test Applicant", contact="test@example.invalid",
        roles=[Role(id="r", company="Example", title="Engineering Specialist",
                    dates="2022 - 2025", bullets=[
            Bullet(id="a", text="Evaluated AI code review tools and documented model limitations."),
            Bullet(id="b", text="Investigated alert anomalies and documented remediation."),
        ])], skills=["Python", "Git"])


def source_plan(profile):
    return Plan(candidates=[
        Candidate(id="original:" + b.id, role_id=r.id, slot_id=b.id,
                  text=b.text, evidence_ids=[b.id], quality=.85)
        for r in profile.roles for b in r.bullets])


class PageRefinementTests(unittest.TestCase):
    @patch("resumeforge.example_refit.ask")
    def test_refit_includes_selected_originals_and_preserves_existing_metrics(self, ask):
        p = small_profile()
        p.roles[0].bullets[0].text = "Evaluated 11 AI code-review tools and documented model limitations."
        plan = source_plan(p)
        long_text = ("Evaluated 11 AI code-review tools, compared their reasoning against production "
                     "security review scenarios, documented misleading findings, and described how "
                     "an engineer could verify the recommended mitigations.")
        ask.return_value = Stories(bullets=[
            Story(slot=1, concise="Evaluated 99 tools and improved security.",
                  detailed=long_text)])
        selection = SimpleNamespace(selected=plan.candidates, feasible=True)
        request = RunRequest(profile=p, job_description="Evaluate AI model responses.")
        report = {"bottom_gap_pt":57, "ink_bottom_gap_pt":57,
                  "target_bottom_gap_pt":13.2, "template":{"leading":13.2}}
        self.assertTrue(refit_examples(request, plan, selection, report, Review(passed=True)))
        self.assertEqual(len(plan.candidates), 3)
        self.assertEqual(plan.candidates[2].text, long_text)
        self.assertFalse(plan.candidates[2].evidence_ids)
        self.assertEqual(plan.candidates[2].origin, "model-example")
        self.assertEqual(ask.call_args.args[3]["needed_lines"], 3)

    def test_fixed_page_uses_longer_content_without_changing_typography(self):
        p = small_profile()
        plan = source_plan(p)
        base = Typesetter()
        concise = base.fit(p, plan, p.skills)
        for c in list(plan.candidates):
            plan.candidates.append(c.model_copy(update={
                "id": "long:" + c.id,
                "text": c.text + " This work included specific technical validation steps, "
                                "documented investigation decisions, and clear guidance for "
                                "another engineer to inspect the evidence and remediation.",
                "quality": .95,
            }))
        longer = base.fit(p, plan, p.skills)
        self.assertGreaterEqual(longer.used_height, concise.used_height)
        self.assertLessEqual(longer.bottom_gap, concise.bottom_gap)
        with tempfile.TemporaryDirectory() as folder:
            before = base.render(concise, Path(folder) / "before.pdf")
            after = base.render(longer, Path(folder) / "after.pdf")
        self.assertEqual(before["template"], after["template"])
        self.assertEqual(before["template"], Template().model_dump())
        self.assertEqual(before["font_sizes"], after["font_sizes"])
        self.assertEqual(before["fonts"], after["fonts"])
        self.assertTrue(after["bounds_passed"])

    @patch("resumeforge.example_refit.ask", return_value=Stories(bullets=[
        Story(slot=1, concise="Too few words for a resume", detailed="Still not enough words for a bullet")]))
    def test_job_targeted_model_cannot_export_four_line_underfill_as_final(self, ask):
        p = small_profile()
        plan = source_plan(p)
        request = RunRequest(
            profile=p, plan=plan,
            job_description="Analyze cyber threats and evaluate AI models.",
            settings=ModelSettings(provider="ollama", model="mock", max_rounds=2))
        with tempfile.TemporaryDirectory() as folder:
            result = run(request, Path(folder))
            self.assertTrue(result["report"]["geometry_passed"])
            self.assertFalse(result["report"]["full_page_passed"])
            self.assertTrue(result["report"]["full_page_required"])
            self.assertEqual(result["status"], "needs_content")
            self.assertFalse((Path(folder) / "resume.pdf").exists())
            self.assertTrue((Path(folder) / "preview.pdf").exists())
        self.assertTrue(ask.called)

    def test_relevance_recognizes_independent_work_concepts(self):
        priorities = [
            Keyword(term="Evaluate AI model responses and identify failure modes", weight=5),
            Keyword(term="Incident investigation and response", weight=5),
            Keyword(term="Document auditable reasoning about security scenarios", weight=4),
        ]
        relevant = ("Evaluated 11 AI code-review tools and documented recurring weaknesses "
                    "in their security findings.")
        unrelated = "Validated AWS KMS and RDS configuration for audit certification."
        self.assertGreater(bullet_relevance(relevant, priorities),
                           bullet_relevance(unrelated, priorities))


class ExperienceRequirementTests(unittest.TestCase):
    def test_tenure_number_removed_but_every_expertise_domain_remains(self):
        posting = """Role
Required Qualifications
5+ years experience in Backend Development, IaC, Cybersecurity Consulting, and SaaS.
2+ years of professional experience in security engineering, red team, or SOC work."""
        rows = extract(passages(posting))
        full = " ".join(row.label for row in rows).casefold()
        for skill in ("backend development", "iac", "cybersecurity consulting", "saas",
                      "security engineering", "red team", "soc work"):
            self.assertIn(skill, full)
        self.assertNotIn("years", full)
        self.assertEqual(without_experience_duration(
            "5+ years experience in Backend Development, IaC, Cybersecurity Consulting, and SaaS"),
            "Backend Development, IaC, Cybersecurity Consulting, and SaaS")

    def test_llm_tenure_requirement_is_normalized_to_expertise(self):
        self.assertEqual(
            _concise_capability("2+ years of professional experience in security engineering, red team, or SOC work"),
            "security engineering, red team, or SOC work")

    @patch("resumeforge.job_analysis.ask")
    def test_model_years_never_take_top_keyword_slot(self, ask):
        profile = small_profile()
        job = """Security Engineer
Required Qualifications
2+ years of professional experience in security engineering, red team, or SOC work.
Responsibilities
Evaluate AI model responses for correctness and subtle failure modes."""
        ask.return_value = Reading(requirements=[
            Requirement(capability="2+ years of professional experience in security engineering, red team, or SOC work",
                        quote="2+ years of professional experience in security engineering, red team, or SOC work"),
            Requirement(capability="AI model response evaluation",
                        quote="Evaluate AI model responses for correctness and subtle failure modes")])
        result = analyze_posting(profile, job, [], ModelSettings(provider="ollama", model="mock"))
        terms = [entry["term"].casefold() for entry in result[:10]]
        self.assertFalse(any("years" in term for term in terms))
        self.assertTrue(any("security engineering" in term for term in terms))


if __name__ == "__main__":
    unittest.main()
