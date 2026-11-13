"""Measured layout and export-gate invariants, independent of model behavior."""
from pathlib import Path
import tempfile
import unittest

from resumeforge.engine import run, validate_plan
from resumeforge.layout import Typesetter
from resumeforge.models import Bullet, Candidate, Evidence, Plan, Profile, Role, RunRequest, Template

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return Profile.model_validate_json((ROOT / 'examples' / 'abu.profile.json').read_text())


def original_plan(profile):
    return Plan(candidates=[Candidate(id='original:' + b.id, role_id=r.id, slot_id=b.id,
                                     text=b.text, evidence_ids=[b.id], quality=.85)
                            for r in profile.roles for b in r.bullets])


def small_profile():
    return Profile(name='Test Person', contact='test@example.test', roles=[
        Role(id='role', company='Example', title='Engineer', dates='2020 - 2024', bullets=[
            Bullet(id='one', text='Operated AWS systems.'),
            Bullet(id='two', text='Reviewed production logs.')])])


class LayoutTests(unittest.TestCase):
    def test_descenders_change_which_alternative_is_feasible(self):
        profile = fixture()
        plan = original_plan(profile)
        nominal_gap = Typesetter().fit(profile, plan, profile.skills).bottom_gap
        # The original fills this synthetic line box exactly, but italic text
        # at the foot of the page has descenders extending below the box.
        renderer = Typesetter(Template(margin_bottom=40 + nominal_gap))
        plan.candidates.append(plan.candidates[0].model_copy(update={
            'id': 'short-audit', 'text': 'Led the annual ISO/IEC 27001 audit across 127 controls.', 'quality': .5}))
        selection = renderer.fit(profile, plan, profile.skills)
        self.assertIn('short-audit', [c.id for c in selection.selected])
        with tempfile.TemporaryDirectory() as folder:
            report = renderer.render(selection, Path(folder) / 'descenders.pdf')
        self.assertTrue(report['geometry_passed'], report['issues'])
        self.assertGreaterEqual(report['ink_bottom_gap_pt'], 0)

    def test_each_role_retains_minimum_and_each_slot_only_one_variant(self):
        profile = fixture()
        plan = original_plan(profile)
        for candidate in list(plan.candidates):
            plan.candidates.append(candidate.model_copy(update={'id':'alternate:' + candidate.id, 'quality':.9}))
        selection = Typesetter().fit(profile, plan, profile.skills)
        self.assertTrue(selection.feasible)
        slots = [c.slot_id for c in selection.selected]
        self.assertEqual(len(slots), len(set(slots)))
        for role in profile.roles:
            self.assertGreaterEqual(sum(c.role_id == role.id for c in selection.selected), 2)
        self.assertGreaterEqual(selection.bottom_gap, -.1)

    def test_render_has_one_page_no_overflow_or_block_overlap(self):
        profile = fixture()
        renderer = Typesetter()
        selection = renderer.fit(profile, original_plan(profile), profile.skills)
        with tempfile.TemporaryDirectory() as work:
            report = renderer.render(selection, Path(work) / 'test.pdf')
        self.assertEqual(report['pages'], 1)
        self.assertTrue(report['bounds_passed'], report['issues'])
        boxes = report['boxes']
        for previous, current in zip(boxes, boxes[1:]):
            self.assertLessEqual(previous['bottom'], current['top'] + .02)
        self.assertGreaterEqual(report['content_bottom'], renderer.t.margin_top)
        self.assertLessEqual(report['content_bottom'], renderer.t.page_height - renderer.t.margin_bottom + .1)

    def test_alternative_words_cannot_change_template_or_fonts(self):
        profile = fixture()
        plan = original_plan(profile)
        alternate = plan.model_copy(deep=True)
        for candidate in list(plan.candidates):
            alternate.candidates.append(candidate.model_copy(update={
                'id':'short:' + candidate.id, 'text':candidate.text.split(';')[0], 'quality':1}))
        renderer = Typesetter()
        with tempfile.TemporaryDirectory() as work:
            first = renderer.render(renderer.fit(profile, plan, profile.skills), Path(work) / 'first.pdf')
            second = renderer.render(renderer.fit(profile, alternate, profile.skills), Path(work) / 'second.pdf')
        self.assertEqual(first['template_fingerprint'], second['template_fingerprint'])
        self.assertEqual(first['template'], Template().model_dump())
        self.assertEqual(first['font_sizes'], second['font_sizes'])
        self.assertEqual(first['fonts'], second['fonts'])

    def test_underfill_remains_safe_to_export(self):
        profile = small_profile()
        renderer = Typesetter()
        selection = renderer.fit(profile, original_plan(profile), [])
        with tempfile.TemporaryDirectory() as work:
            report = renderer.render(selection, Path(work) / 'test.pdf')
        self.assertTrue(selection.feasible)
        self.assertTrue(report['bounds_passed'])
        self.assertFalse(report['full_page_passed'])
        self.assertTrue(report['geometry_passed'])
        self.assertGreater(report['bottom_gap_pt'], report['target_bottom_gap_pt'])

    def test_underfill_exports_safe_single_page_without_manual_padding(self):
        profile = small_profile()
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            result = run(RunRequest(profile=profile, plan=original_plan(profile)), directory)
            self.assertEqual(result['status'], 'ready')
            self.assertTrue(result['report']['bounds_passed'])
            self.assertFalse(result['report']['full_page_passed'])
            self.assertTrue((directory / 'preview.pdf').exists())
            self.assertTrue((directory / 'resume.pdf').exists())

    def test_fixed_sections_overflow_never_produces_final_export(self):
        profile = small_profile()
        profile.certifications = 'Verified course completion. ' * 350
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            result = run(RunRequest(profile=profile, plan=original_plan(profile)), directory)
            self.assertNotEqual(result['status'], 'ready')
            self.assertFalse(result['report']['geometry_passed'])
            self.assertFalse((directory / 'resume.pdf').exists())

    def test_unconfirmed_evidence_is_excluded_even_with_high_quality(self):
        profile = fixture()
        fact = Evidence(id='unverified', role_id=profile.roles[0].id,
                        text='Reduced deployment time by 78% using Terraform.', confirmed=False)
        profile.facts.append(fact)
        plan = original_plan(profile)
        plan.candidates.append(Candidate(id='not-approved', role_id=fact.role_id,
                                         slot_id='fact:' + fact.id, text=fact.text,
                                         evidence_ids=[fact.id], quality=1))
        validate_plan(profile, plan)
        self.assertTrue(plan.candidates[-1].needs_confirmation)
        selection = Typesetter().fit(profile, plan, profile.skills)
        self.assertNotIn('not-approved', [c.id for c in selection.selected])

    def test_infeasible_role_minimum_is_explicit(self):
        profile = fixture()
        plan = original_plan(profile)
        plan.candidates = [c for c in plan.candidates if c.role_id == profile.roles[0].id]
        selection = Typesetter().fit(profile, plan, profile.skills)
        self.assertFalse(selection.feasible)
        self.assertTrue(any('minimum bullets' in warning for warning in selection.warnings))

    def test_unsupported_glyph_and_unbreakable_token_are_rejected(self):
        renderer = Typesetter()
        with self.assertRaisesRegex(ValueError, 'does not support'):
            renderer.para('Unicorn \U0001f984')
        with self.assertRaisesRegex(ValueError, 'Unbreakable'):
            renderer.para('a' * 300)

    def test_literal_markup_is_printed_as_text(self):
        profile = small_profile()
        profile.roles[0].bullets[0].text = 'Checked A < B & C > D and printed <b>literal</b>.'
        renderer = Typesetter()
        selection = renderer.fit(profile, original_plan(profile), [])
        with tempfile.TemporaryDirectory() as work:
            report = renderer.render(selection, Path(work) / 'literal.pdf')
        self.assertTrue(report['bounds_passed'], report['issues'])
        self.assertFalse(any('round-trip' in issue for issue in report['issues']))

    def test_wrapped_company_and_location_stay_inside_columns(self):
        profile = small_profile()
        profile.roles[0].company = 'Example International Infrastructure and Platform Services Company'
        profile.roles[0].location = 'Cincinnati metropolitan area, Ohio, United States of America'
        renderer = Typesetter()
        selection = renderer.fit(profile, original_plan(profile), [])
        with tempfile.TemporaryDirectory() as work:
            report = renderer.render(selection, Path(work) / 'wrapped.pdf')
        self.assertTrue(report['bounds_passed'], report['issues'])
        for previous, current in zip(report['boxes'], report['boxes'][1:]):
            self.assertLessEqual(previous['bottom'], current['top'] + .02)


if __name__ == '__main__':
    unittest.main()
