"""Exercise the actual native PDF workflow with the interpreter under test.

Use the packaged runtime/python.exe on Windows. For a source checkout,
install the project and its desktop dependencies into the active environment.
No model server or real applicant data entry is required.
"""
import argparse
import hashlib
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QPlainTextEdit, QPushButton
from pypdf import PdfReader

from resumeforge import desktop_window
from resumeforge.desktop_dialogs import edit_settings
from resumeforge.models import Bullet, ModelSettings, Profile, Role


def assert_bundled(root):
    for path in (Path(sys.executable), Path(desktop_window.__file__)):
        if not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"Loaded a dependency outside the extracted app: {path}")


def wait_for(app, condition, message, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.025)
    raise RuntimeError(message)


def widget(window, cls, name):
    obj = window.findChild(cls, name)
    if obj is None:
        raise RuntimeError(f"Missing native control {name!r}")
    return obj


def check_builds(app, data_dir):
    window = desktop_window.MainWindow(data_dir)
    window.settings = ModelSettings(provider="none")
    window.show()
    try:
        # This modal imports QtNetwork for local model discovery. Exercise it
        # in the frozen runtime as well as on a developer machine.
        observed = []
        def close_model_settings():
            dialog = app.activeModalWidget()
            if isinstance(dialog, QDialog):
                observed.append(dialog.windowTitle())
                dialog.reject()
        QTimer.singleShot(0, close_model_settings)
        assert edit_settings(window, window.settings) is None
        assert observed == ["Model settings"]
        build = widget(window, QPushButton, "buildButton")
        save = widget(window, QPushButton, "exportButton")
        preview = widget(window, QLabel, "pdfPreview")
        assert not build.isVisible() and not save.isEnabled()
        window.job.setPlainText("DevOps Engineer with Claude Code CLI. Build agentic engineering harnesses, automate CI/CD pipelines, and provision infrastructure as code. Python is required.")
        analyze = widget(window, QPushButton, "analyzeButton")
        analyze.click()
        wait_for(app, lambda: window.worker is None and build.isVisible(), "Job analysis did not pause for review")
        assert window.result is None and not save.isEnabled()
        priorities = window._keywords()
        assert priorities and window.analysis_notes.toPlainText() and window.brief.toPlainText()
        assert window.policy.currentData() == "inspiration"
        window.keywords.setPlainText("\n".join(["CI/CD pipelines", *[k for k in priorities if k != "CI/CD pipelines"]]))
        build.click()
        wait_for(app, lambda: window.result is not None and save.isEnabled(),
                 "Default profile did not produce an export-ready page")
        assert window.result["status"] == "ready"
        assert window.result["report"]["model_used"] is None
        assert preview.pixmap() is not None and not preview.pixmap().isNull()
        assert preview.pixmap().width() >= 100
        target = data_dir / "checked resume.pdf"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "PDF (*.pdf)")):
            save.click()
        wait_for(app, target.is_file, "The checked PDF was not saved")
        assert hashlib.sha256(target.read_bytes()).hexdigest() == window.result["report"]["pdf_sha256"]
        reader = PdfReader(target)
        assert len(reader.pages) == 1 and reader.pages[0].extract_text().strip()
        bullets = window.result["report"].get("inspiration_bullets", [])
        assert bullets and window.edit_bullets_button.isVisible()
        assert window.profile == Profile.model_validate(window.result["profile"])
        pdf_text = " ".join(reader.pages[0].extract_text().split())
        assert " ".join(bullets[0]["text"].split()) in pdf_text
        assert "fictional" not in pdf_text.lower() and "example achievement" not in pdf_text.lower()
        print("Reviewing the priorities produced new bullets, a native PDF preview and a matching one-page export.")

        previous = window.run_dir
        def revise_generated():
            dialog = app.activeModalWidget()
            editor = dialog.findChild(QPlainTextEdit, "generatedBulletText")
            # Change one word to verify the generated text can be edited without a model.
            words = editor.toPlainText().split(" ", 1)
            editor.setPlainText(("Delivered" if words[0] != "Delivered" else "Built") + " " + words[1])
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        QTimer.singleShot(0, revise_generated)
        window.edit_bullets_button.click()
        wait_for(app, lambda: bool(window.result) and window.run_dir != previous and save.isEnabled(),
                 "Edited examples were not refit and approved for export")
        revised = window.result["report"]["inspiration_bullets"]
        assert any(b["id"] == bullets[0]["id"] and b["text"] != bullets[0]["text"] for b in revised)
        assert not any(f.text == revised[0]["text"] for f in window.profile.facts)
        assert window.save_workspace()
        restored = desktop_window.MainWindow(data_dir)
        assert restored.result and restored._can_export()
        assert restored.result["report"]["inspiration_bullets"] == revised
        restored.close()
        print("Generated bullets were edited and refit, then restored from the saved workspace.")

        sparse = Profile(
            name="Test Candidate",
            contact="test@example.invalid",
            roles=[Role(id="one", company="Example", title="Analyst", dates="2022–2024",
                        bullets=[Bullet(id="b1", text="Reviewed the weekly incident report.")])],
        )
        window.set_profile(sparse)
        assert not save.isEnabled(), "Changing the source left an earlier export enabled"
        previous = window.run_dir
        window.job.setPlainText("")
        analyze.click()
        wait_for(app, lambda: window.worker is None and build.isVisible(), "Unable to review new source")
        window.policy.setCurrentIndex(window.policy.findData("verified"))
        build.click()
        wait_for(app, lambda: bool(window.result) and window.run_dir != previous and
                 window.result.get("status") == "ready" and save.isEnabled(),
                 "The sparse but safe one-page resume did not become export-ready")
        assert window.result["report"]["geometry_passed"] is True
        assert window.result["report"]["full_page_passed"] is False
        assert (Path(window.run_dir) / "resume.pdf").exists()
        print("Safe underfilled draft exported; the earlier selection was invalidated.")
    finally:
        window.close()
        app.processEvents()


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--package-root", type=Path, help="Assert that the extracted runtime and application were loaded")
    parsed = args.parse_args()
    if parsed.package_root:
        assert_bundled(parsed.package_root)
    app = QApplication.instance() or QApplication(["ResumeForge GUI smoke"])
    if sys.platform == "win32" and app.platformName().lower() != "windows":
        raise RuntimeError(f"Expected native Windows QPA, got {app.platformName()!r}")
    print(f"Testing Qt platform {app.platformName()} with Python {sys.version.split()[0]}", flush=True)
    with tempfile.TemporaryDirectory(prefix="ResumeForge test ") as folder:
        check_builds(app, Path(folder))


if __name__ == "__main__":
    main()
