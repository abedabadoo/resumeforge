"""Portable scanner tests; original personal documents are optional fixtures."""
from io import BytesIO
from pathlib import Path
import unittest
import warnings
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from resumeforge.importing import inspect_document, import_document
from resumeforge.models import ModelSettings, Profile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path.home() / 'Downloads' / 'Abdelraheem_Al-najjar_resume.pdf'


def docx(text='Test Person', extras=None, xml=None, types='<Types/>'):
    result = BytesIO()
    with ZipFile(result, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', types)
        archive.writestr('word/document.xml', xml or (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + ''.join('<w:p><w:r><w:t>' + escape(line) + '</w:t></w:r></w:p>' for line in text.split('\n'))
            + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="800" w:bottom="800" w:left="800" w:right="800"/></w:sectPr>'
            + '</w:body></w:document>'))
        for name, content in (extras or {}).items():
            archive.writestr(name, content)
    return result.getvalue()


def pdf(text='Test Person', pages=1):
    output = BytesIO()
    painter = canvas.Canvas(output, pagesize=(612, 792))
    for _ in range(pages):
        painter.setFont('Helvetica', 12)
        painter.drawString(40, 740, text)
        painter.showPage()
    painter.save()
    return output.getvalue()


def mapped_profile():
    return Profile(name='Test Person', contact='test@example.test', roles=[{
        'id':'role', 'company':'Example Company', 'title':'Engineer', 'dates':'2020 - 2024',
        'location':'Remote', 'bullets':[{'id':'b1', 'text':'Operated AWS systems.'}]}], skills=['AWS'])


class ImportTests(unittest.TestCase):
    def test_pdf_geometry_and_font_report(self):
        result = inspect_document('sample.pdf', pdf())
        self.assertEqual(result['page_count'], 1)
        self.assertEqual(result['pages'][0]['width_pt'], 612)
        self.assertEqual(result['pages'][0]['fonts'][0]['size_pt'], 12)
        self.assertEqual(result['pages'][0]['text_bbox_pt'][0], 40)
        self.assertIn('Test Person', result['text'])

    def test_docx_sections_are_requested_geometry(self):
        result = inspect_document('sample.docx', docx())
        self.assertEqual(result['sections'][0]['width_pt'], 612)
        self.assertEqual(result['sections'][0]['margins_pt']['left'], 40)
        self.assertIsNone(result['page_count'])

    def test_generic_no_model_returns_text_without_guessing(self):
        for filename, content in [('sample.pdf', pdf()), ('sample.docx', docx())]:
            result = import_document(filename, content, ModelSettings())
            self.assertIsNone(result['profile'])
            self.assertIn('Test Person', result['text'])
            self.assertTrue(any('structured' in warning.lower() for warning in result['warnings']))

    @unittest.skipUnless(ORIGINAL.is_file(), 'Original personal PDF is not required for the portable suite')
    def test_known_baseline_hash_returns_checked_profile(self):
        result = import_document(ORIGINAL.name, ORIGINAL.read_bytes(), ModelSettings())
        expected = Profile.model_validate_json((ROOT / 'examples' / 'abu.profile.json').read_text())
        self.assertEqual(result['profile'], expected.model_dump())
        self.assertEqual(sum(len(role['bullets']) for role in result['profile']['roles']), 11)
        self.assertNotIn('(cid:', str(result['profile']))

    @patch('resumeforge.planning.call_json')
    def test_template_instructions_are_never_candidate_facts(self, call):
        result = import_document('template.docx', docx('Jobby McJobface\nCompany Name #2\nPlug in your own information'),
                                 ModelSettings(provider='ollama', model='test'))
        self.assertTrue(result['inspection']['looks_like_template'])
        self.assertIsNone(result['profile'])
        call.assert_not_called()

    @patch('resumeforge.planning.call_json')
    def test_ai_mapping_accepts_only_verbatim_fields(self, call):
        profile = mapped_profile()
        call.return_value = profile.model_dump()
        source = 'Test Person\ntest@example.test\nExample Company\nEngineer\n2020 - 2024\nRemote\nOperated AWS systems.\nAWS'
        result = import_document('resume.docx', docx(source), ModelSettings(provider='ollama', model='test'))
        self.assertIsNotNone(result['profile'])
        self.assertEqual(result['profile']['roles'][0]['bullets'][0]['text'], 'Operated AWS systems.')
        self.assertTrue(result['profile']['source_sha256'])
        self.assertIn('untrusted DATA', call.call_args.args[1])
        self.assertTrue(any('Review the AI mapping' in text for text in result['warnings']))

    @patch('resumeforge.planning.call_json')
    def test_ai_mapping_rejects_invented_claim(self, call):
        profile = mapped_profile()
        profile.roles[0].bullets[0].text = 'Reduced costs by 78% using Terraform.'
        call.return_value = profile.model_dump()
        result = import_document('resume.docx', docx('Test Person\ntest@example.test\nExample Company\nEngineer\n2020 - 2024\nRemote\nOperated AWS systems.\nAWS'),
                                 ModelSettings(provider='ollama', model='test'))
        self.assertIsNone(result['profile'])
        self.assertTrue(any('changed or invented' in text for text in result['warnings']))

    @patch('resumeforge.planning.call_json', side_effect=RuntimeError('provider failure'))
    def test_ai_failure_retains_text_without_claiming_success(self, call):
        result = import_document('resume.docx', docx(), ModelSettings(provider='ollama', model='test'))
        self.assertIsNone(result['profile'])
        self.assertEqual(result['text'], 'Test Person')

    def test_external_relationships_are_not_fetched(self):
        data = docx(extras={'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="file:///private/secret"/></Relationships>'})
        result = inspect_document('a.docx', data)
        self.assertEqual(result['text'], 'Test Person')
        self.assertTrue(any('no remote resources were fetched' in text for text in result['warnings']))

    def test_rejects_unsupported_empty_and_oversize_input(self):
        for name, data in [('a.docm', b'x'), ('a.pdf', b''), ('a.pdf', b'x' * (10 * 1024 * 1024 + 1))]:
            with self.subTest(name=name, length=len(data)), self.assertRaises(ValueError):
                inspect_document(name, data)

    def test_rejects_invalid_documents_and_page_limit(self):
        for name, data in [('a.pdf', b'not a pdf'), ('a.docx', b'not zip'), ('a.pdf', pdf(pages=11))]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_document(name, data)

    def test_encrypted_pdf_rejected(self):
        writer = PdfWriter(); writer.add_blank_page(612,792); writer.encrypt('secret')
        output = BytesIO(); writer.write(output)
        with self.assertRaisesRegex(ValueError, 'Encrypted'):
            inspect_document('a.pdf', output.getvalue())

    def test_image_only_or_blank_pdf_requires_text(self):
        writer = PdfWriter(); writer.add_blank_page(612,792)
        output = BytesIO(); writer.write(output)
        result = import_document('a.pdf', output.getvalue(), ModelSettings())
        self.assertIsNone(result['profile'])
        self.assertTrue(any('OCR' in warning for warning in result['warnings']))

    def test_archive_path_traversal_and_duplicate_entries_rejected(self):
        for name in ['../bad', '/tmp/bad', 'C:\\bad', 'word/../../bad']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_document('a.docx', docx(extras={name:'x'}))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            duplicate = docx(extras={'word/document.xml':'<document/>'})
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect_document('a.docx', duplicate)

    def test_macros_activex_entities_and_archive_bomb_rejected(self):
        samples = [docx(extras={'word/vbaProject.bin':'x'}),
                   docx(extras={'word/activeX/item.xml':'x'}),
                   docx(types='<Types>macroEnabled</Types>'),
                   docx(xml='<!DOCTYPE foo [<!ENTITY x "data">]><foo>&x;</foo>'),
                   docx(extras={'word/large.xml':'x' * (16 * 1024 * 1024 + 1)})]
        for index, data in enumerate(samples):
            with self.subTest(index=index), self.assertRaises(ValueError):
                inspect_document('a.docx', data)


if __name__ == '__main__':
    unittest.main()
