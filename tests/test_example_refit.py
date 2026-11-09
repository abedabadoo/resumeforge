import unittest
from types import SimpleNamespace
from unittest.mock import patch

from resumeforge.example_refit import refit_examples
from resumeforge.inspiration import Story, Stories
from resumeforge.models import Bullet, Candidate, Keyword, Plan, Profile, Review, Role, RunRequest


class ExampleRefitTests(unittest.TestCase):
    def test_refit_keeps_user_wording_and_checks_new_numbers(self):
        text = "Built CI/CD pipelines for 5 services and documented deployment failures."
        user_text = "Introduced deployment testing for the team that maintains the ordering service."
        role = Role(id="r", title="Engineer", company="Example", dates="", bullets=[
            Bullet(id="a", text="First source"), Bullet(id="b", text="Second source")])
        plan = Plan(keywords=[Keyword(term="CI/CD")], candidates=[
            Candidate(id="idea:1", role_id="r", slot_id="a", origin="model-example", text=text, keywords=["CI/CD"]),
            Candidate(id="idea:2", role_id="r", slot_id="b", origin="edited-example", text=user_text)])
        req = RunRequest(profile=Profile(name="Sample", contact="", roles=[role]))
        valid = "Built CI/CD pipelines for 5 services and recorded the stage and exit code for every deployment failure."
        invalid = "Built CI/CD pipelines for 90 services and reduced failed deployments."
        response = Stories(bullets=[Story(slot=1, concise=invalid, detailed=valid)])
        with patch("resumeforge.example_refit.ask", return_value=response) as ask:
            added = refit_examples(req, plan, SimpleNamespace(selected=plan.candidates[:], feasible=True),
                {"template":{"leading":13.2}, "bottom_gap_pt":37}, Review(passed=True))
        self.assertTrue(added)
        self.assertEqual([c.text for c in plan.candidates], [text, user_text, valid])
        payload = ask.call_args.args[3]
        self.assertEqual(payload["unused_points"], 37)
        self.assertEqual([s["current_bullet"] for s in payload["slots"]], [text])
