import json
from pathlib import Path

from resumeforge.cover_letter import draft_text, export_pdf, role_folder
from resumeforge.models import Profile


def test_cover_letter_is_optional_editable_and_pdf_only(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    profile = Profile.model_validate(
        json.loads((Path(__file__).parents[1] / "examples/abu.profile.json").read_text())
    )
    folder = role_folder("Example Co", "Platform Engineer")
    destination = folder / "Alnajjar_CoverLetter.pdf"
    assert not destination.exists()
    text = draft_text(profile, "Example Co", "Platform Engineer", "AWS, Python")
    assert "Example Co" in text and "AWS" in text
    export_pdf(text + "\n\nI can discuss this in more detail.", profile, destination)
    assert destination.read_bytes().startswith(b"%PDF-")
