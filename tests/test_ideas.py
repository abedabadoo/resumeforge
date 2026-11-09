import json
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from resumeforge.ideas import Idea, IdeaBatch, IdeaRequest, brainstorm
from resumeforge.models import Bullet, ModelSettings, Profile, Role, RunRequest


class FictionalIdeas(TestCase):
    def setUp(self):
        self.profile = Profile(name="Private Name", contact="private@example.invalid", roles=[
            Role(id="one", title="Developer", company="Private Employer", dates="2023",
                 bullets=[Bullet(id="b1", text="Created test fixtures.")]),
            Role(id="two", title="Assistant", company="Other Employer", dates="2022",
                 bullets=[Bullet(id="b2", text="Only this employer calibrated vacuum gauges.")]),
        ])
        self.request = IdeaRequest(profile=self.profile, role_id="one", focus="cloud", keywords=["Terraform"])
        self.model = ModelSettings(provider="ollama", model="local")

    def test_repeated_offline_brainstorm_returns_fresh_examples_outside_draft(self):
        before = self.profile.model_dump()
        first = brainstorm(self.request)
        examples = [idea['text'] for idea in first['ideas']]
        self.assertEqual(first['mode'], 'templates')
        self.assertTrue(first['fictional'])
        self.assertEqual(len(set(examples)), 3)
        self.assertIn('Terraform', ' '.join(examples))
        self.assertTrue(all(any(c.isdigit() for c in text) for text in examples))
        following = brainstorm(self.request.model_copy(update={'previous':examples}))
        self.assertTrue(set(examples).isdisjoint(i['text'] for i in following['ideas']))
        self.assertEqual(len(following['ideas']), 3)
        self.assertEqual(self.profile.model_dump(), before)
        with self.assertRaises(ValidationError):
            RunRequest.model_validate({'profile':self.profile.model_dump(), **first})

    def test_invalid_role_rejects_before_inference(self):
        with patch('resumeforge.ideas.ask') as ask:
            with self.assertRaisesRegex(ValueError, 'Choose a role'):
                brainstorm(self.request.model_copy(update={'role_id':'missing','settings':self.model}))
            ask.assert_not_called()

    def test_duplicate_and_unquantified_model_ideas_get_distinct_replacements(self):
        example = Idea(text="Wrote 12 connection tests for slow payment gateways and prevented failed orders.",verify=["Actual tests and impact?"])
        unquantified = Idea(text="Organized a rollout across several reporting teams.",verify=["Actual scope?"])
        request = self.request.model_copy(update={'settings':self.model})
        with patch('resumeforge.ideas.ask', return_value=IdeaBatch(ideas=[example,example,unquantified])) as ask:
            result = brainstorm(request)
        context = json.dumps(ask.call_args.args[3])
        self.assertIn('Created test fixtures', context)
        for private in ('Private Name','Private Employer','private@example.invalid','vacuum gauges'):
            self.assertNotIn(private, context)
        self.assertEqual(result['mode'], 'mixed')
        bullets = [idea['text'] for idea in result['ideas']]
        self.assertEqual(len(set(bullets)), 3)
        self.assertEqual(bullets[0], example.text)
        self.assertNotIn(unquantified.text, bullets)

    def test_unavailable_model_keeps_examples_available_with_correct_provenance(self):
        with patch('resumeforge.ideas.ask', side_effect=RuntimeError("model offline")):
            result = brainstorm(self.request.model_copy(update={'settings':self.model}))
        self.assertEqual(result['mode'], 'templates')
        self.assertEqual(len(result['ideas']), 3)
        self.assertTrue(all(item['verify'] for item in result['ideas']))
