"""Grounding and measurable editorial requirements. No model server required."""
import unittest
from unittest.mock import patch
from pathlib import Path
from resumeforge.edit_constraints import comparative_issue,unsupported_brief,length_spec,selected_length_issue
from resumeforge.models import Bullet,Profile,Role,ModelSettings,RunRequest
from resumeforge.planning import build_plan
from resumeforge.laptop import check_request
from resumeforge.layout import Typesetter

class EditConstraintTests(unittest.TestCase):
    def setUp(self):
        self.p=Profile(name='Sample',contact='sample.invalid',skills=['Git','RStudio'],roles=[Role(id='r',title='Technician',company='Fictional Workshop',dates='2020',bullets=[Bullet(id='a1',text='Validated thermal sensor readings before forwarding each report to the site coordinator.'),Bullet(id='b2',text='Maintained supply inventory records for the purchasing department.')])])
    def test_endpoint_not_a_delta(self):
        s=['Lowered delay from 90 seconds to 60 seconds.']
        self.assertTrue(comparative_issue(s,'Lowered delay by 60 seconds.'))
        self.assertTrue(comparative_issue(s,'Reduced delay from 60 seconds to 90 seconds.'))
        self.assertIsNone(comparative_issue(s,'Lowered delay by 30 seconds.'))
        self.assertIsNone(comparative_issue(s,'Delay fell from 90 seconds to 60 seconds.'))
    def test_inclusive_result_is_not_a_strict_bound(self):
        for original in ("Turnaround fell to <= 1 week.", "Turnaround fell to one week or less."):
            self.assertTrue(comparative_issue([original], "Reduced turnaround to under one week."))
            self.assertIsNone(comparative_issue([original], "Reduced turnaround to at most one week."))
        self.assertIsNone(comparative_issue(["Turnaround was under 1 week."], "Reduced turnaround to under one week."))

    def test_separate_explicit_delta_not_overruled(self):
        s=['Lowered delay from 90 seconds to 60 seconds. Reduced setup time by 60 seconds.']
        self.assertIsNone(comparative_issue(s,'Reduced setup time by 60 seconds.'))
    def test_immutable_layout_before_semantic_judge(self):
        req=RunRequest(profile=self.p,settings=ModelSettings(strategy='laptop',provider='openai-compatible',model='test'),edit_request='Increase the font size to 18 points.')
        with patch('resumeforge.laptop.ask',side_effect=AssertionError('unexpected inference')):
            self.assertFalse(check_request(req,[],[]).passed)
        self.assertIsNone(unsupported_brief(self.p,'Keep the original margins unchanged and emphasize reporting.'))
    def test_contradiction_in_same_not_different_section(self):
        self.assertTrue(unsupported_brief(self.p,'Add RStudio to skills, then remove RStudio from the skills list.'))
        self.assertIsNone(unsupported_brief(self.p,'Remove Git from experience and include Git in the skills list.'))
    def test_named_target_and_length(self):
        s,e=length_spec(self.p,'Shorten the thermal sensor bullet to at most 7 words.')
        self.assertIsNone(e);self.assertEqual(s.slot,'a1');self.assertFalse(s.allows(self.p.roles[0].bullets[0].text))
        self.assertTrue(s.allows('Validated thermal sensor readings before reporting.'));self.assertTrue(selected_length_issue(s,[]))
    def test_ambiguous_target_holds(self):
        s,e=length_spec(self.p,'Shorten the responsibility bullet.')
        self.assertIsNone(s);self.assertTrue(e)
    def test_real_fitter_includes_required_lower_utility_variant(self):
        p=Profile.model_validate_json((Path(__file__).resolve().parents[1]/'examples/abu.profile.json').read_text())
        plan=build_plan(p,'',[],ModelSettings());orig=plan.candidates[0]
        alt=orig.model_copy(update={'id':'alt','text':'Led audits of 127 controls.','quality':.1})
        plan.candidates=[c for c in plan.candidates if c.slot_id!=orig.slot_id]+[alt]
        result=Typesetter().fit(p,plan,p.skills,required_slots={orig.slot_id})
        self.assertTrue(result.feasible);self.assertIn('alt',[c.id for c in result.selected])
