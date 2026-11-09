from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
from resumeforge import laptop
from resumeforge.engine import run
from resumeforge.models import Candidate, ModelSettings, Profile, RunRequest
from resumeforge.planning import build_plan, _grounding_issues
from resumeforge.wording import verified_material

APP=Path(__file__).resolve().parents[1]


class VerifiedWording(TestCase):
    def setUp(self):
        self.profile=Profile.model_validate_json((APP/'examples/abu.profile.json').read_text())
        self.strict=ModelSettings(wording_policy='verified',strategy='laptop')
        self.plan=build_plan(self.profile,'',[],self.strict)

    def test_supplied_plan_cannot_spoof_source_or_add_inferred_skill(self):
        c=self.plan.candidates[0]
        alien=next(x for x in self.plan.candidates if x.role_id!=c.role_id)
        wrong=c.model_copy(update={'text':alien.text,'id':'original:spoof'})
        self.plan.candidates.insert(0,wrong)
        safe, skills=verified_material(self.profile,self.plan,[self.profile.skills[0],'Spurious new skill'])
        self.assertNotIn(wrong,safe.candidates)
        self.assertEqual(skills,self.profile.skills[:1])
        with TemporaryDirectory() as d:
            r=run(RunRequest(profile=self.profile,settings=self.strict,plan=self.plan),Path(d))
            self.assertEqual((r['status'],r['report']['wording_policy']),('ready','verified'))
            self.assertNotIn(wrong.id,[c['id'] for c in json.loads((Path(d)/'selected.json').read_text())])
            self.assertTrue((Path(d)/'resume.pdf').is_file())

    def test_model_ranks_sources_without_generating_prose(self):
        cfg=self.strict.model_copy(update={'provider':'openai-compatible','model':'fixture'})
        with patch.object(laptop,'ask',return_value=laptop.Focus(ordered=[2],terms=['AWS'],skills=[1])) as model:
            plan=build_plan(self.profile,'AWS',[],cfg)
        self.assertEqual([call.args[1] for call in model.call_args_list],[laptop.Focus])
        self.assertTrue(all(c.text==self.profile.evidence()[c.evidence_ids[0]].text for c in plan.candidates))
        self.assertGreater(plan.candidates[1].quality,plan.candidates[0].quality)

    def test_newly_asserted_tool_purpose_and_completion_are_held(self):
        from resumeforge.claim_relations import issues
        sources=['Reviewed events in Splunk and built a ticket queue for escalations.']
        self.assertTrue(issues(sources,'Reviewed events in Splunk to track escalations.',['Splunk']))
        self.assertFalse(issues(['Reviewed events in Splunk to track escalations.'],
                                'Reviewed the events in Splunk to track escalations.',['Splunk']))
        self.assertTrue(issues(['Validated the database settings.'],
                               'Validated the database settings to complete the project rollout.',[]))

    def test_writer_honors_a_named_target_even_when_ranker_selects_another(self):
        b=self.profile.roles[0].bullets[0]; cfg=self.strict.model_copy(update={'provider':'openai-compatible','model':'fixture','wording_policy':'rewrite'})
        counts=[]
        def fake(settings,schema,system,payload,tokens):
            if schema is laptop.Focus:return laptop.Focus(ordered=[2],terms=[])
            self.assertEqual(payload['evidence'],b.text)
            counts.append(payload['word_limits_for_both_versions']['maximum_words'])
            if len(counts)==1: return laptop.Versions(concise=b.text,detailed=b.text)
            return laptop.Versions(concise='Led the internal audit across all 127 controls.',detailed=b.text)
        with patch.object(laptop,'ask',side_effect=fake):
            plan=laptop.propose(self.profile,'',[],cfg,edit_request=f'Only shorten the bullet {b.id}.')
        self.assertEqual(len(counts),2)
        self.assertTrue(any(c.slot_id==b.id for c in plan.candidates))
