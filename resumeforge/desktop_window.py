"""Native desktop editor for the same engine used by the command-line interface."""
from __future__ import annotations

from pathlib import Path
import re
import threading
from uuid import uuid4

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QFileDialog, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from .desktop_preview import PagePreview, plain_label
from .desktop_support import export_checked, load_draft, save_draft
from .engine import run
from .ideas import IdeaRequest, brainstorm
from .importing import MAX_BYTES, import_document
from .local_runtime import default_settings
from .models import ModelSettings, Plan, Profile, RunRequest


class TaskSignals(QObject):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)


def button(text, name, callback):
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def tab_page(layout):
    page = QWidget()
    page.setLayout(layout)
    return page


def field(layout, caption, widget):
    label = plain_label(caption, "fieldLabel")
    label.setBuddy(widget)
    layout.addWidget(label)
    layout.addWidget(widget)


def paragraph(name, placeholder, height):
    widget = QPlainTextEdit()
    widget.setObjectName(name)
    widget.setPlaceholderText(placeholder)
    widget.setMinimumHeight(height)
    widget.setTabChangesFocus(True)
    return widget


def role_text(role):
    return f"{role.title} · {role.company}"


STYLE = """
QMainWindow, QWidget#workspace { background: #f3f5f4; color: #192c2a; }
QWidget#banner { background: #174b46; }
QLabel#brand { font-size: 24px; font-weight: bold; color: white; }
QLabel#account { color: #e7f3ee; font-size: 13px; }
QWidget#banner QPushButton { color: #f5fbf7; background: #23615a; border: 1px solid #50847c; }
QTabWidget::pane { border: 1px solid #c6d3cf; border-radius: 5px; background: white; }
QTabBar::tab { padding: 9px 12px; background: #e7eeeb; color: #38544e; }
QTabBar::tab:selected { background: white; color: #174b46; border-bottom: 2px solid #237365; }
QLabel { color: #243b34; }
QLabel#fieldLabel, QLabel#paperEmployer { font-weight: bold; }
QLabel#sectionTitle { font-size: 18px; font-weight: bold; padding-bottom: 3px; }
QLabel#hint, QLabel#modelStatus { color: #50665d; }
QPushButton { padding: 7px 10px; border-radius: 4px; border: 1px solid #afc0b9; background: #ffffff; color: #21483c; }
QPushButton:hover { border-color: #29705b; background: #edf5ef; }
QPushButton:disabled { background: #eef1ef; border-color: #d6ddd9; color: #6e7974; }
QPushButton#buildButton, QPushButton#exportButton:enabled { background: #196356; color: white; border: 1px solid #185d51; font-weight: bold; }
QPushButton#buildButton:disabled { background: #dce6e2; color: #61736a; border-color: #cbd8d1; }
QPlainTextEdit, QLineEdit, QListWidget, QComboBox { padding: 5px; border: 1px solid #b7c5be; border-radius: 4px; background: #ffffff; color: #152d23; selection-background-color: #236a57; selection-color: white; }
QListWidget::item { padding: 4px; }
QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus { border-color: #176353; }
QWidget#sourcePage { background: white; }
QLabel#paperName { font-size: 22px; font-weight: bold; }
QLabel#paperHeading { font-size: 15px; font-weight: bold; }
QLabel#paperContact { color: #53635c; }
QScrollArea { border: none; background: #dde5e0; }
QProgressBar { max-height: 5px; background: #d2e3dd; border: none; }
QProgressBar::chunk { background: #24785f; }
"""


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.profile = Profile.model_validate_json((Path(__file__).with_name("data") /
                                                    "abu.profile.json").read_text(encoding="utf-8"))
        self.settings = default_settings()
        self.ideas = {}
        self.result = None
        self.run_dir = None
        self._reviewed_plan = False
        self.worker = None
        self._on_success = None
        self._dirty = False
        self.signals = TaskSignals(self)
        self.signals.progress.connect(self._progress)
        self.signals.done.connect(self._done)
        self.signals.failed.connect(self._failed)
        self.setWindowTitle("ResumeForge")
        self.resize(1220, 835)
        self.setMinimumSize(790, 590)
        self.setStyleSheet(STYLE)
        self._create_interface()
        self._show_profile()
        self._restore()
        self._show_settings()
        for item in (self.job, self.brief, self.keywords):
            item.textChanged.connect(self._input_changed)
        self.policy.currentIndexChanged.connect(self._input_changed)
        self.idea_topic.textChanged.connect(self._scratch_changed)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save_workspace)

    def _create_interface(self):
        background = QWidget()
        background.setObjectName("workspace")
        self.setCentralWidget(background)
        outer = QVBoxLayout(background)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QWidget()
        header.setObjectName("banner")
        top = QHBoxLayout(header)
        top.setContentsMargins(20, 12, 20, 12)
        top.addWidget(plain_label("ResumeForge", "brand"))
        top.addStretch()
        self.account = plain_label("", "account")
        top.addWidget(self.account)
        self.import_button = button("Import resume…", "importButton", self.import_resume)
        self.save_button = button("Save workspace", "saveButton", self.save_workspace)
        self.settings_button = button("Model settings…", "settingsButton", self.configure_model)
        for widget in (self.import_button, self.save_button, self.settings_button):
            top.addWidget(widget)
        outer.addWidget(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        content = QVBoxLayout()
        content.setContentsMargins(16, 14, 16, 10)
        content.addWidget(self.splitter, 1)
        self.left = QTabWidget()
        self.left.setMinimumWidth(310)
        self.left.addTab(self._tailor_tab(), "Tailor")
        self.left.addTab(self._experience_tab(), "Experience")
        self.left.addTab(self._ideas_tab(), "Bullet ideas")
        self.splitter.addWidget(self.left)
        self.right = QTabWidget()
        self.preview = PagePreview()
        self.right.addTab(self.preview, "Source resume")
        self.review_notes = QPlainTextEdit()
        self.review_notes.setReadOnly(True)
        self.review_notes.setObjectName("reviewNotes")
        self.review_notes.setPlaceholderText("Build a resume to see the changes, keyword coverage, and review notes.")
        self.right.addTab(self.review_notes, "Changes and checks")
        self.splitter.addWidget(self.right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setSizes([420, 700])
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        content.addWidget(self.progress)
        footer = QHBoxLayout()
        self.status = plain_label("Ready to build.", "runStatus")
        footer.addWidget(self.status, 1)
        self.review_button = button("Review proposed claims…", "reviewButton", self.review_claims)
        self.review_button.hide()
        footer.addWidget(self.review_button)
        self.export_button = button("Save checked PDF…", "exportButton", self.export_pdf)
        self.export_button.setEnabled(False)
        footer.addWidget(self.export_button)
        content.addLayout(footer)
        outer.addLayout(content, 1)

    def _tailor_tab(self):
        box = QVBoxLayout()
        box.setContentsMargins(16, 14, 16, 14)
        box.addWidget(plain_label("Tailor your resume", "sectionTitle"))
        self.job = paragraph("jobDescription", "Paste the responsibilities and qualifications for this job.", 100)
        field(box, "Job description", self.job)
        box.setStretch(box.indexOf(self.job), 3)
        self.brief = paragraph("editRequest", "For example, emphasize cloud hardening and keep the audit result concise.", 52)
        field(box, "Editing instructions", self.brief)
        box.setStretch(box.indexOf(self.brief), 1)
        self.keywords = QLineEdit()
        self.keywords.setObjectName("keywords")
        self.keywords.setPlaceholderText("AWS, Terraform, CI/CD")
        field(box, "Priority keywords", self.keywords)
        self.policy = QComboBox()
        self.policy.setObjectName("wordingPolicy")
        self.policy.addItem("Generate tailored wording", "rewrite")
        self.policy.addItem("Use only my verified wording", "verified")
        field(box, "Experience wording", self.policy)
        self.model_label = plain_label("", "modelStatus")
        box.addWidget(self.model_label)
        self.build_button = button("Build resume", "buildButton", self.build_resume)
        box.addWidget(self.build_button)
        return tab_page(box)

    def _experience_tab(self):
        box = QVBoxLayout()
        box.setContentsMargins(16, 14, 16, 14)
        box.addWidget(plain_label("Verified experience", "sectionTitle"))
        box.addWidget(plain_label("Add work you can confirm for a specific job. The engine can use these facts in a tailored resume.", "hint"))
        self.facts = QListWidget()
        self.facts.setObjectName("factList")
        self.facts.setWordWrap(True)
        box.addWidget(self.facts, 1)
        self.remove_fact_button = button("Remove selected fact", "removeFact", self.remove_fact)
        self.facts.currentRowChanged.connect(lambda index: self.remove_fact_button.setEnabled(index >= 0))
        box.addLayout(row(button("Add verified fact…", "addFact", self.new_fact), self.remove_fact_button))
        box.addWidget(button("Edit source profile…", "editProfile", self.edit_source))
        return tab_page(box)

    def _ideas_tab(self):
        box = QVBoxLayout()
        box.setContentsMargins(16, 14, 16, 14)
        box.addWidget(plain_label("Brainstorm bullet ideas", "sectionTitle"))
        box.addWidget(plain_label("These examples use invented details and numbers. Revise an idea to match your work before adding it to your resume.", "hint"))
        self.idea_role = QComboBox()
        self.idea_role.setObjectName("ideaRole")
        self.idea_role.currentIndexChanged.connect(self._show_ideas)
        field(box, "Experience role", self.idea_role)
        self.idea_topic = QLineEdit()
        self.idea_topic.setObjectName("ideaTopic")
        self.idea_topic.setMaxLength(300)
        self.idea_topic.setPlaceholderText("For example, speeding up releases")
        field(box, "Topic (optional)", self.idea_topic)
        box.addWidget(button("Generate three ideas", "generateIdeas", self.generate_ideas))
        self.idea_list = QListWidget()
        self.idea_list.setObjectName("ideaList")
        self.idea_list.setWordWrap(True)
        box.addWidget(self.idea_list, 1)
        self.use_idea = button("Edit and confirm selected idea…", "useIdea", self.promote_idea)
        self.idea_list.currentRowChanged.connect(lambda index: self.use_idea.setEnabled(index >= 0))
        self.use_idea.setEnabled(False)
        box.addWidget(self.use_idea)
        return tab_page(box)

    def _show_profile(self):
        self.account.setText(self.profile.name)
        previous = self.idea_role.currentData()
        self.idea_role.blockSignals(True)
        self.idea_role.clear()
        roles = {role.id: role for role in self.profile.roles}
        for role in self.profile.roles:
            self.idea_role.addItem(role_text(role), role.id)
        self.idea_role.setCurrentIndex(max(0, self.idea_role.findData(previous)))
        self.idea_role.blockSignals(False)
        self._show_ideas()
        self.facts.clear()
        for fact in self.profile.facts:
            role = roles.get(fact.role_id)
            prefix = role.company if role else "Profile"
            status = "" if fact.confirmed else " · Unconfirmed"
            self.facts.addItem(f"{prefix}{status}\n{fact.text}")
        self.remove_fact_button.setEnabled(False)
        self.preview.show_source(self.profile)

    def set_profile(self, profile: Profile):
        """Install a reviewed source. Clear drafts associated with the previous person."""
        self.profile = Profile.model_validate(profile)
        self.ideas = {}
        self._show_profile()
        self._input_changed()
        self.status.setText("Source updated. Build a resume to check the new profile.")

    def _show_settings(self):
        index = self.policy.findData(self.settings.wording_policy)
        self.policy.setCurrentIndex(max(0, index))
        self.policy.setItemText(self.policy.findData("rewrite"), "Use source wording (no model)" if
                                self.settings.provider == "none" else "Generate tailored wording")
        if self.settings.provider == "none":
            self.model_label.setText("Using source wording. Connect a local model in Model settings for AI rewrites.")
        else:
            self.model_label.setText(f"Writing model: {self.settings.model or self.settings.provider}")

    def _show_ideas(self, *_):
        self.idea_list.clear()
        for idea in self.ideas.get(self.idea_role.currentData(), []):
            item = QListWidgetItem(idea["text"])
            item.setToolTip("Fictional example")
            self.idea_list.addItem(item)
        if self.idea_list.count():
            self.idea_list.setCurrentRow(0)

    def _refresh_after_fact(self):
        self._show_profile()
        self._input_changed()
        self.status.setText("Experience updated. Build a resume to include the change.")

    def _scratch_changed(self, *_):
        self._dirty = True

    def _input_changed(self, *_):
        self._dirty = True
        if self.result is not None:
            self.result = None
            self.run_dir = None
            self.review_button.hide()
            self.export_button.setEnabled(False)
            self.right.setTabText(0, "Source resume")
            self.preview.show_source(self.profile)
            self.review_notes.clear()
            self.status.setText("Inputs changed. Build again to check this version.")

    def _current_settings(self):
        return self.settings.model_copy(update={"wording_policy": self.policy.currentData()})

    def _keywords(self):
        return list(dict.fromkeys(part.strip() for part in re.split(r"[,;\n]", self.keywords.text()) if part.strip()))

    def _snapshot(self):
        return {"version": 1, "profile": self.profile.model_dump(),
                "settings": self._current_settings().model_dump(), "job_description": self.job.toPlainText(),
                "edit_request": self.brief.toPlainText(), "keywords": self.keywords.text(),
                "ideas": self.ideas, "idea_role": self.idea_role.currentData(), "idea_topic": self.idea_topic.text()}

    def _restore(self):
        try:
            draft = load_draft(self.data_dir)
            if not draft:
                return
            if draft.get("version") != 1:
                raise ValueError("Unsupported saved-workspace version.")
            profile = Profile.model_validate(draft["profile"])
            settings = ModelSettings.model_validate(draft["settings"])
            roles = {role.id for role in profile.roles}
            # Only accept saved scratch text, never treat an idea as role evidence.
            from .ideas import Idea
            restored = {key: [Idea.model_validate(i).model_dump() for i in batch[:24]]
                        for key, batch in draft.get("ideas", {}).items() if key in roles}
            self.profile, self.settings, self.ideas = profile, settings, restored
            self._show_profile()
            self.job.setPlainText(draft.get("job_description", ""))
            self.brief.setPlainText(draft.get("edit_request", ""))
            self.keywords.setText(draft.get("keywords", ""))
            self.idea_topic.setText(draft.get("idea_topic", ""))
            idx = self.idea_role.findData(draft.get("idea_role"))
            if idx >= 0:
                self.idea_role.setCurrentIndex(idx)
            self.status.setText("Saved workspace restored.")
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.status.setText(f"Could not restore the saved workspace: {exc}")

    def save_workspace(self):
        try:
            save_draft(self.data_dir, self._snapshot())
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not save the workspace: {exc}")
            return False
        self._dirty = False
        self.status.setText("Workspace saved on this computer.")
        return True

    def _start(self, message, work, success):
        if self.worker is not None:
            return
        self._on_success = success
        self._set_busy(True)
        self._progress(message)
        signals = self.signals

        def execute():
            try:
                output = work(signals.progress.emit)
            except Exception as exc:
                signals.failed.emit(str(exc))
            else:
                signals.done.emit(output)

        self.worker = threading.Thread(target=execute, name="ResumeForge task", daemon=True)
        self.worker.start()

    def _set_busy(self, busy):
        for widget in (self.left, self.import_button, self.settings_button,
                       self.save_button, self.review_button):
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.export_button.setEnabled(not busy and self._can_export())

    def _can_export(self):
        if self.result is None or self.run_dir is None:
            return False
        report = self.result["report"]
        return self.result["status"] == "ready" and report.get("geometry_passed") and report.get("quality_review", {}).get("passed")

    @Slot(str)
    def _progress(self, message):
        self.status.setText(message)

    @Slot(object)
    def _done(self, value):
        action = self._on_success
        self.worker, self._on_success = None, None
        self._set_busy(False)
        try:
            action(value)
        except Exception as exc:
            self.status.setText(f"Could not complete this action: {exc}")

    @Slot(str)
    def _failed(self, message):
        self.worker, self._on_success = None, None
        self._set_busy(False)
        self.status.setText(message or "The operation could not be completed.")

    def build_resume(self):
        self._build()

    def _build(self, plan=None, confirmations=None):
        if self.worker is not None:
            return
        try:
            profile = self.profile.model_copy(deep=True)
            if plan is not None:
                # Reconfirmations replace the previous versions from this plan.
                confirmed = {"confirmed:" + p.id for p in plan.proposed_claims}
                profile.facts = [f for f in profile.facts if f.id not in confirmed]
                plan = plan.model_copy(deep=True)
                plan.candidates = [c for c in plan.candidates if not set(c.evidence_ids) & confirmed]
            request = RunRequest(profile=profile, settings=self._current_settings(),
                                 job_description=self.job.toPlainText(), edit_request=self.brief.toPlainText(),
                                 keywords=self._keywords(), plan=plan, confirmed_claim_ids=confirmations or [])
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        folder = self.data_dir / "runs" / uuid4().hex
        self.result, self.run_dir = None, None
        self._reviewed_plan = plan is not None
        self.export_button.setEnabled(False)
        self.review_button.hide()
        self.review_notes.clear()
        self.right.setTabText(0, "Source resume")
        self.preview.show_source(self.profile)
        self._start("Building the resume…", lambda progress: run(request, folder, progress),
                    lambda result: self.render_result(result, folder))

    def render_result(self, result, run_dir):
        self.result = result
        self.run_dir = Path(run_dir)
        returned = Profile.model_validate(result["profile"])
        if self.profile != returned:
            self.profile = returned
            self._dirty = True
            self._show_profile()
        report = result["report"]
        self.review_notes.setPlainText(self._format_review(report))
        self.review_button.setVisible(bool(result.get("plan", {}).get("proposed_claims")))
        self.export_button.setEnabled(bool(self._can_export()))
        labels = {"ready": "Checks passed. Review the PDF before submitting.",
                  "needs_content": "More verified content or different wording is needed to fit the page.",
                  "needs_review": "Content needs review. See Changes and checks."}
        status = labels.get(result["status"], "Review the checks.")
        self.status.setText(f"{status}   •   {report.get('ink_bottom_gap_pt', 0):.1f} pt above bottom margin")
        try:
            self.preview.show_pdf(self.run_dir / "preview.pdf")
        except Exception as exc:
            self.right.setTabText(0, "Source resume")
            self.status.setText(f"{status} The PDF preview could not be displayed: {exc}")
        else:
            self.right.setTabText(0, "PDF preview")
            self.right.setCurrentIndex(0)

    @staticmethod
    def _format_review(report):
        coverage = report.get("keyword_coverage", {})
        content = report.get("quality_review", {})
        lines = ["Page checks", f"{report['pages']} page(s) · {report['ink_bottom_gap_pt']:.2f} pt above the bottom margin",
                 "Geometry passed" if report["geometry_passed"] else "Page fit needs revision",
                 "Content checks passed" if content.get("passed") else "Content checks need review"]
        for heading, values in (
            ("Issues", list(report.get("issues", [])) + list(content.get("issues", []))),
            ("Suggestions", content.get("suggestions", [])),
            ("Matched keywords", coverage.get("matched", [])), ("Missing keywords", coverage.get("missing", [])),
            ("Review notes", report.get("warnings", [])),
        ):
            if values:
                lines.extend(["", heading, *[f"• {value}" for value in values]])
        for change in report.get("changes", []):
            lines += ["", change.get("reason", "Changed bullet"),
                      "Before: " + (change.get("before") or "(new statement)"),
                      "After: " + (change.get("after") or "(omitted)")]
        return "\n".join(lines)

    def export_pdf(self):
        if not self._can_export() or self.worker is not None:
            return
        name = re.sub(r'[^\w .-]', "", self.profile.name).strip() or "Resume"
        path, _ = QFileDialog.getSaveFileName(self, "Save checked resume", name + " - Resume.pdf", "PDF (*.pdf)")
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(".pdf")
        try:
            export_checked(self.run_dir, destination)
        except (ValueError, OSError, KeyError) as exc:
            self.status.setText(f"Could not save the checked PDF: {exc}")
        else:
            self.status.setText(f"Saved {destination.name}.")

    def configure_model(self):
        from .desktop_dialogs import edit_settings
        updated = edit_settings(self, self._current_settings())
        if updated is not None:
            self.settings = updated
            self._show_settings()
            self._input_changed()
            self.status.setText("Model settings updated.")

    def import_resume(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import resume", "", "Resume files (*.pdf *.docx)")
        if not path:
            return
        incoming = Path(path)
        settings = self._current_settings()

        def read_source(progress):
            if incoming.stat().st_size > MAX_BYTES:
                raise ValueError("Choose a PDF or DOCX smaller than 10 MiB.")
            return import_document(incoming.name, incoming.read_bytes(), settings)

        self._start("Reading the source document…", read_source, self._import_finished)

    def _import_finished(self, result):
        from .desktop_dialogs import edit_profile
        mapped = Profile.model_validate(result["profile"]) if result.get("profile") else None
        warnings = "\n".join(result.get("warnings", []))
        self.status.setText("Review the extracted source and its job assignments.")
        extracted = result.get("text", "")
        source_note = f"{warnings}\n\n{extracted}" if warnings else extracted
        profile = edit_profile(self, mapped, source_note)
        if profile is not None:
            self.set_profile(profile)
        else:
            self.status.setText("Import cancelled.")

    def edit_source(self):
        from .desktop_dialogs import edit_profile
        updated = edit_profile(self, self.profile)
        if updated is not None:
            self.set_profile(updated)

    def _append_fact(self, fact):
        if not fact:
            return False
        if any(f.role_id == fact.role_id and f.text == fact.text for f in self.profile.facts):
            self.status.setText("That verified fact already exists under this job.")
            return False
        self.profile.facts.append(fact)
        self._refresh_after_fact()
        return True

    def new_fact(self):
        from .desktop_dialogs import add_fact
        self._append_fact(add_fact(self, self.profile))

    def remove_fact(self):
        index = self.facts.currentRow()
        if 0 <= index < len(self.profile.facts):
            self.profile.facts.pop(index)
            self._refresh_after_fact()

    def generate_ideas(self):
        role_id = self.idea_role.currentData()
        try:
            request = IdeaRequest(profile=self.profile.model_copy(deep=True), role_id=role_id,
                                  job_description=self.job.toPlainText(), keywords=self._keywords(),
                                  focus=self.idea_topic.text(), settings=self._current_settings(),
                                  previous=[i["text"] for i in self.ideas.get(role_id, [])][-8:])
        except ValueError as exc:
            self.status.setText(str(exc))
            return

        def show(batch):
            previous = self.ideas.get(role_id, [])
            self.ideas[role_id] = (batch["ideas"] + previous)[:24]
            self._dirty = True
            self._show_ideas()
            self.status.setText(f"{len(batch['ideas'])} fictional examples added. Edit an idea to make it factual.")

        self._start("Preparing fictional examples…", lambda progress: brainstorm(request), show)

    def promote_idea(self):
        from .desktop_dialogs import add_fact
        role = self.idea_role.currentData()
        index = self.idea_list.currentRow()
        batch = self.ideas.get(role, [])
        if 0 <= index < len(batch):
            idea = batch[index]
            if self._append_fact(add_fact(self, self.profile, role, idea)):
                batch.pop(index)
                self._show_ideas()

    def review_claims(self):
        from .desktop_dialogs import review_proposals
        if not self.result:
            return
        plan = Plan.model_validate(self.result["plan"])
        if not self._reviewed_plan:
            # Models can repeat IDs (for example, "proposal-1") in unrelated
            # plans. Give each proposal a durable ID before it can become a fact.
            for index, proposal in enumerate(plan.proposed_claims):
                proposal.id = f"desktop-{self.run_dir.name}-{index}"
        selection = review_proposals(self, self.profile, plan)
        if selection is not None:
            self._build(*selection)

    def closeEvent(self, event):
        if self.worker is not None:
            answer = QMessageBox.question(self, "Close ResumeForge?", "A task is still running. Close the app now?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self._dirty and not self.save_workspace():
            answer = QMessageBox.question(self, "Workspace could not be saved", "Close without saving the current edits?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
