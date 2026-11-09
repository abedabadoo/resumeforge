import unittest
from resumeforge.skill_evidence import personally_attributed as attributed

class SkillEvidenceTests(unittest.TestCase):
    def test_vendor_subject_cannot_be_borrowed(self):
        for s in ["The hosting vendor configured Terraform; I transcribed its weekly status notes.",
                  "Our engineers deployed Terraform while I documented release notes.",
                  "I supported the vendor that operated Terraform.",
                  "They were already using Terraform.", "My team deployed Terraform."]:
            with self.subTest(s=s):self.assertFalse(attributed(s,"Terraform"))
    def test_possession_and_proposals_cannot_establish_use(self):
        for s in ["Reviewed the vendor's Terraform deployment.","I analyzed their existing Terraform dashboards.",
                  "Proposed using Terraform to provision development instances.",
                  "I planned to implement Terraform.", "I never deployed Terraform.",
                  "The Terraform stack was operated by our hosting provider."]:
            with self.subTest(s=s):self.assertFalse(attributed(s,"Terraform"))
    def test_same_sentence_different_subjects(self):
        s="The vendor configured Terraform while I operated Python ingestion jobs."
        self.assertFalse(attributed(s,"Terraform")); self.assertTrue(attributed(s,"Python"))
    def test_personal_and_implied_use_remains_eligible(self):
        for s in ["Configured Terraform modules for an external vendor.",
                  "I deployed Terraform modules to staging.","Hardened AWS access using Terraform.",
                  "We tested Terraform in a staging environment."]:
            with self.subTest(s=s):self.assertTrue(attributed(s,"Terraform"))
        self.assertTrue(attributed("Configured Amazon Web Services access policies.","AWS",["Amazon Web Services"]))
