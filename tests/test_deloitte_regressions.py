"""Deloitte cloud-defense regression: qualified capabilities, not raw word fragments."""
import unittest

from resumeforge.models import Bullet, Profile, Role, Keyword
from resumeforge.planning import analyze_job, bullet_relevance, rank_skills
from resumeforge.priorities import passages


DELOITTE = """Cloud Defense Security Engineer
Work you'll do
Design the telemetry, data, and infrastructure across a multi-cloud environment.
Our mix includes cloud-native platforms, CNAPP tooling, and classic SIEM.
Build and directly manage cloud security telemetry, monitoring, and alerting infrastructure.
Where you'll make an impact:
Cloud detection and response platform. Build the cloud investigation and triage infrastructure.
Unified threat visibility. Bring cloud-native alerts and CNAPP into a unified view.
AI-infused security engineering. Explore AI-assisted engineering and AI-driven correlation across data sources.
Responsibilities:
Design, build, and directly manage cloud security telemetry, logging, and alerting infrastructure.
Apply modern software and cloud engineering practices: IaC, automation, CI/CD.
Spot gaps in visibility or coverage and improve configuration guardrails.
Support post-incident reviews and document your work.
The role has no SOC or on-call rotation.
Qualifications:
Required:
Bachelor's degree or equivalent, plus 5+ years in software engineering, cloud engineering, or data engineering
Hands-on multi-cloud experience (AWS, Azure, and/or GCP), including directly managing cloud security infrastructure such as logging and alerting
Programming and Infrastructure as Code experience (e.g., Python, Terraform, or similar)
Some experience with data modeling or correlating data across systems.
Desired Skills / Certifications:
Cloud-native telemetry & automation: Bicep, Pulumi, or Power BI
Detection & SIEM platforms: Splunk, Microsoft Sentinel, or Google SecOps/Chronicle, query authoring in KQL, SPL, or similar
CNAPP & posture tooling: Wiz, Prisma Cloud, Microsoft Defender for Cloud, or Orca Security
Container & workload security: Kubernetes/Docker security, awareness of MITRE ATT&CK for Cloud
Relevant certifications: AWS Security Specialty, Azure Security Engineer AZ-500, CCSP, GIAC GCSA/GCDA, or CKS
Adjacent exposure: Security Operations or Incident Response.
"""


def source():
    return Profile(
        name="Test", contact="test@example.com",
        skills=["AWS", "Python", "Docker", "Linux/Unix", "Datadog",
                "Infrastructure as Code (IaC)", "GitHub Actions", "Google Cloud Platform",
                "Microsoft Azure", "SQL", "Tableau", "OWASP ZAP", "Gitlab", "REST APIs"],
        roles=[Role(id="r", company="Example", title="Security Engineer", dates="2024 - 2026",
                    bullets=[
                        Bullet(id="aws", text="Hardened AWS through infrastructure as code: IAM and IMDSv2 safeguards."),
                        Bullet(id="inc", text="Built incident response processes, alert ingestion, runbooks, and SLO alerts."),
                        Bullet(id="ai", text="Built an AI-powered Slack security assistant using read-only OneTrust."),
                        Bullet(id="soc", text="Ran SOC 2 Type II and ISO 27001 evidence operations."),
                    ])])


class DeloitteRegressions(unittest.TestCase):
    def test_optional_section_is_not_mislabeled_required(self):
        rows = passages(DELOITTE)
        optional = next(row for row in rows if "Splunk" in row.text)
        self.assertEqual(optional.section, "preferred")
        self.assertIn("telemetry", " ".join(x.text for x in rows).casefold())

    def test_core_cloud_defense_capabilities_are_identified(self):
        analysis = analyze_job(source(), DELOITTE)
        names = [row["term"] for row in analysis]
        for label in ("Cloud security telemetry and alerting infrastructure",
                      "Multi-cloud security engineering",
                      "Unified SIEM and CNAPP threat visibility",
                      "Security data engineering and correlation",
                      "AI-assisted detection engineering",
                      "Cloud security guardrails and detection coverage",
                      "Infrastructure as Code"):
            self.assertIn(label, names)
        self.assertIn("Cloud security telemetry and alerting infrastructure", names[:15])
        self.assertNotIn("WAF monitoring and incident response", names)
        for fragment in ("not", "tools", "ATT", "CK", "AZ", "GCS"):
            self.assertNotIn(fragment, names)

    def test_optional_products_not_hard_requirements(self):
        rows = {entry["term"]: entry for entry in analyze_job(source(), DELOITTE)}
        for tool in ("Splunk", "Kubernetes", "Docker", "Power BI"):
            if tool in rows:
                self.assertFalse(rows[tool]["required"], tool)

    def test_cloud_engineering_and_telemetry_evidence(self):
        rows = {entry["term"]: entry for entry in analyze_job(source(), DELOITTE)}
        self.assertIn(rows["Multi-cloud security engineering"]["evidence"], ("exact", "related"))
        self.assertIn(rows["Cloud security telemetry and alerting infrastructure"]["evidence"], ("exact", "related"))
        self.assertIn(rows["Infrastructure as Code"]["evidence"], ("exact", "related"))

    def test_technical_skills_are_not_ejected_by_unrelated_optional_terms(self):
        analysis = analyze_job(source(), DELOITTE)
        priorities = [Keyword(term=x["term"], weight=x["weight"], kind=x["kind"]) for x in analysis]
        selected = rank_skills(source(), priorities)
        for important in ("Python", "AWS", "Datadog", "Infrastructure as Code (IaC)",
                          "GitHub Actions"):
            self.assertIn(important, selected)

    def test_duties_outweigh_generic_compliance(self):
        priorities = [
            Keyword(term="Cloud security telemetry and alerting infrastructure", weight=5),
            Keyword(term="Multi-cloud security engineering", weight=5),
            Keyword(term="Infrastructure as Code", weight=5),
            Keyword(term="Security data engineering and correlation", weight=5),
        ]
        self.assertGreater(
            bullet_relevance("Built multi-cloud security telemetry with alert ingestion and Azure SIEM correlation", priorities),
            bullet_relevance("Ran SOC 2 Type II evidence operations for certification", priorities))


if __name__ == "__main__":
    unittest.main()
