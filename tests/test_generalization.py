"""Hold-out occupations: assert ranking without adding job-specific catalog entries.

These samples deliberately cover roles the app did not previously special-case.
We check source-grounded meaning and importance, not exact vendor keywords.
"""
import unittest
from unittest.mock import patch

from resumeforge.job_analysis import Requirement, Reading, analyze_posting
from resumeforge.models import Profile, Role, Bullet, ModelSettings
from resumeforge.planning import analyze_job
from resumeforge.priorities import passages
from resumeforge.requirement_extraction import extract, grounded_label


POSTINGS = {
    "registered nurse": """Registered Nurse
Responsibilities
Conduct comprehensive patient assessments and document clinical observations.
Coordinate safe medication administration across inpatient wards.
Educate patients and families about discharge plans.
Required qualifications
Experience with patient care coordination and clinical documentation.
Preferred qualifications
Experience with Epic is a plus.
Salary Range
$70,000 - $99,000""",
    "accountant": """Financial Accountant
Responsibilities
Reconcile monthly general ledger accounts and prepare consolidated financial statements.
Investigate material reporting discrepancies across subsidiaries.
Required qualifications
Experience with audit preparation and internal controls.
Preferred qualifications
Familiarity with NetSuite.""",
    "logistics": """Logistics Coordinator
Responsibilities
Coordinate international freight shipments across ocean and rail carriers.
Track customs documentation and investigate delivery exceptions.
Required qualifications
Experience with shipment tracking and carrier coordination.
Preferred qualifications
Experience with CargoWise.""",
    "teacher": """Elementary School Teacher
Responsibilities
Develop individualized lesson plans and assess student learning outcomes.
Communicate student progress with families.
Required qualifications
Experience with classroom management and differentiated instruction.
Preferred qualifications
Experience with Google Classroom.""",
    "facilities": """Facilities Maintenance Technician
Responsibilities
Inspect electrical systems and troubleshoot equipment faults.
Perform preventive maintenance across commercial buildings.
Required qualifications
Experience with mechanical repairs and safety inspections.
Preferred qualifications
Familiarity with CMMS software.""",
    "retail": """Retail Store Manager
Responsibilities
Manage store inventory and train associates on point-of-sale workflows.
Coordinate seasonal staffing and resolve customer escalations.
Required qualifications
Experience with retail operations and inventory control.
Preferred qualifications
Familiarity with Shopify POS.""",
}


def empty_profile():
    return Profile(name="Example", contact="test@example.com", skills=[],
                   roles=[Role(id="r", company="Example", title="Generalist", dates="2023-2026",
                               bullets=[Bullet(id="b", text="Coordinated a recurring process for colleagues.")])])


class GeneralizationTests(unittest.TestCase):
    def test_industry_neutral_extraction_captures_primary_tasks(self):
        for title, posting in POSTINGS.items():
            with self.subTest(title=title):
                extracted = extract(passages(posting))
                self.assertGreaterEqual(len(extracted), 2, extracted)
                self.assertTrue(all(task.section in ("duties", "required") for task in extracted))
                self.assertFalse(any("Salary" in task.source for task in extracted))
                results = analyze_job(empty_profile(), posting)
                labels = [r["term"].casefold() for r in results]
                self.assertTrue(any(task.label.casefold() in labels for task in extracted), labels)

    def test_unseen_occupations_have_work_before_optional_product(self):
        jobs = [
            ("accountant", "netsuite"),
            ("logistics", "cargowise"),
            ("teacher", "google classroom"),
            ("facilities", "cmms"),
            ("retail", "shopify pos"),
        ]
        for title, optional in jobs:
            with self.subTest(title=title):
                found = analyze_job(empty_profile(), POSTINGS[title])
                core = [r for r in found[:7] if r["kind"] != "credential"]
                self.assertTrue(any(not r["rationale"].startswith("Preferred qualification")
                                    for r in core))
                self.assertFalse(any(r["term"].casefold() == optional and r["required"] for r in found))

    def test_unrecognized_paraphrased_duty_may_be_model_ranked(self):
        posting = """Customer Support Lead
Responsibilities
Resolve escalated customer complaints and investigate recurring service failures.
Required qualifications
Experience managing service-quality escalations."""
        reading = Reading(requirements=[Requirement(
            capability="Customer complaint resolution",
            quote="Resolve escalated customer complaints and investigate recurring service failures.")])
        settings = ModelSettings(provider="ollama", model="test")
        with patch("resumeforge.job_analysis.ask", return_value=reading) as ask:
            findings = analyze_posting(empty_profile(), posting, [], settings)
        self.assertIn("Customer complaint resolution", [r["term"] for r in findings])
        self.assertEqual(ask.call_args.args[3], {"posting": "\n".join(row.text for row in passages(posting))[:12000]})

    def test_unsourced_model_priority_is_rejected(self):
        posting = "Responsibilities\nPrepare quarterly tax filings and reconcile cash accounts."
        reading = Reading(requirements=[Requirement(
            capability="Network penetration testing",
            quote="Prepare quarterly tax filings and reconcile cash accounts.")])
        with patch("resumeforge.job_analysis.ask", return_value=reading):
            found = analyze_posting(empty_profile(), posting, [],
                                    ModelSettings(provider="ollama", model="test"))
        self.assertNotIn("Network penetration testing", [r["term"] for r in found])

    def test_generic_rephrasing_guard_requires_overlap(self):
        self.assertTrue(grounded_label("Inventory forecast analysis",
                                       "Forecast inventory demand across fifteen retail outlets"))
        self.assertFalse(grounded_label("Network penetration testing",
                                        "Prepare quarterly tax filings and reconcile cash accounts"))

    def test_job_content_cannot_prioritize_compensation(self):
        posting = """Office Administrator
Responsibilities
Coordinate office calendars and maintain supplier records.
Required qualifications
Experience with office administration and supplier communication.
Benefits
Dental insurance, gym membership, flexible PTO.
Salary
$67,000-$82,000"""
        found = analyze_job(empty_profile(), posting)
        names = [r["term"].casefold() for r in found[:10]]
        self.assertFalse(any("insurance" in t or "salary" in t or "gym" in t for t in names))


if __name__ == "__main__":
    unittest.main()
