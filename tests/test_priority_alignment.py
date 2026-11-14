"""Priority-to-resume alignment regression tests.

Use synthetic postings and candidate bullets, not the historical job ads.
The patch only changes ordering and skill-label choices, not page geometry.
"""
import unittest

from resumeforge.layout import Typesetter
from resumeforge.models import Bullet, Candidate, Keyword, Plan, Profile, Role
from resumeforge.planning import bullet_order_priority
from resumeforge.skills import _identity, _named_technologies, choices


class PriorityAlignmentTests(unittest.TestCase):
    def test_named_platforms_follow_ranked_job_priorities(self):
        keys = [
            Keyword(term="Design Google Cloud Platform (GCP) infrastructure", weight=5),
            Keyword(term="Deploy and manage Kubernetes (GKE) clusters", weight=5),
            Keyword(term="Implement Infrastructure as Code with Terraform", weight=5),
            Keyword(term="Build CI/CD pipelines using Jenkins", weight=4),
        ]
        self.assertEqual(bullet_order_priority(
            "Designed GCP cloud topology and routing.", keys), 0)
        self.assertEqual(bullet_order_priority(
            "Implemented GKE clusters with monitoring.", keys), 1)
        self.assertEqual(bullet_order_priority(
            "Built Terraform modules and Jenkins automation.", keys), 2)
        self.assertEqual(bullet_order_priority(
            "Reviewed ISO 27001 governance reports.", keys), len(keys))

    def test_layout_reorders_existing_winners_without_changing_selected_set(self):
        descriptions = [
            "Reviewed governance reports and prepared management dashboards.",
            "Built Terraform modules and Jenkins deployment pipelines.",
            "Implemented GKE clusters with policy monitoring.",
            "Designed scalable GCP networks and load balancers.",
        ]
        profile = Profile(name="Example Applicant", contact="applicant@example.test",
                          roles=[Role(id="r", company="Example Co", title="Engineer",
                                      dates="2022 - 2025",
                                      bullets=[Bullet(id=str(i), text=t)
                                               for i, t in enumerate(descriptions)])])
        keys = [
            Keyword(term="Design scalable Google Cloud Platform (GCP) infrastructure", weight=5),
            Keyword(term="Deploy and manage Kubernetes (GKE) clusters", weight=5),
            Keyword(term="Build Terraform automation", weight=5),
        ]
        plan = Plan(keywords=keys, candidates=[
            Candidate(id=f"source:{i}", slot_id=str(i), role_id="r",
                      evidence_ids=[str(i)], text=t, quality=.8)
            for i, t in enumerate(descriptions)
        ])
        fit = Typesetter().fit(profile, plan, [])
        self.assertTrue(fit.feasible)
        self.assertEqual({c.slot_id for c in fit.selected}, {"0", "1", "2", "3"})
        self.assertEqual([c.slot_id for c in fit.selected][:3], ["3", "2", "1"])

    def test_only_real_skill_names_are_extracted(self):
        names = _named_technologies(
            "Required Linux and Windows administration. "
            "Deploy Kubernetes (GKE) for 670 divisions.")
        self.assertNotIn("670", names)
        self.assertNotIn("Linux and Windows", names)
        self.assertIn("Windows", names)
        self.assertEqual(_identity("Linux/Unix"), _identity("Linux"))

    def test_printed_work_promotes_kubernetes_and_windows_without_duplicates(self):
        profile = Profile(name="Example Applicant", contact="applicant@example.test",
                          roles=[Role(id="r", company="Example Co", title="Engineer",
                                      dates="2022 - 2025",
                                      bullets=[Bullet(id="b", text="Maintained server infrastructure.")])],
                          skills=["Linux/Unix", "Drata"])
        selected = [Candidate(id="c", slot_id="b", role_id="r", evidence_ids=["b"],
                              text=("Deployed hardened Linux and Windows servers; "
                                    "implemented GKE clusters with Istio."))]
        job = ("Required\nLinux and Windows operating systems. "
               "Deploy Kubernetes (GKE) environments for enterprise workloads.")
        names = [c.label for c in choices(profile, [
            Keyword(term="Linux and Windows operating systems", weight=5),
            Keyword(term="Kubernetes (GKE) deployment", weight=5)
        ], job_description=job, selected=selected)]
        self.assertIn("Kubernetes", names)
        self.assertIn("Windows", names)
        self.assertNotIn("Linux and Windows", names)
        self.assertNotIn("670", names)
        self.assertEqual(sum(_identity(n) == "linux" for n in names), 1)


if __name__ == "__main__":
    unittest.main()
