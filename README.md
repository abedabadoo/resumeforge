# ResumeForge

A native Windows desktop app for tailoring a resume and saving a checked PDF. A browser interface is also available for local use. It turns a structured profile into a searchable, selectable PDF using a fixed template. The writing model proposes content; the renderer controls typography. No ChatGPT subscription, conversation, or Codex process is needed to run the installed app.

[Laptop evaluation, training results and known limits](Laptop-validation.md)

## Install on Windows

Download **ResumeForge-Setup-x64.exe** from the [Windows desktop release](https://github.com/abedabadoo/resumeforge/releases/tag/v0.3.0) while signed in to the private repository. Run the installer, then open **ResumeForge** from the Start menu. The installer includes Python, the native Qt interface, fonts, and the PDF engine. If you prefer a portable copy, extract the entire **ResumeForge-Windows-x64.zip** and launch **ResumeForge.exe** inside its folder. Both builds target 64-bit Intel and AMD Windows PCs.

Start with your preloaded resume, paste a posting, then choose **Build resume**. The right pane previews the generated PDF. **Save checked PDF** becomes available after the writing and layout checks pass. **Bullet ideas** provides fictional examples you can turn into verified facts.

The first launch works with source wording. For AI rewrites, start a local model service on your PC. Open **Model settings**, select **Ollama** or **OpenAI-compatible endpoint**, enter the service URL, and choose **Find installed models** or enter its model name. The PC model is a separate installation. Your workspace, generated previews, and run reports are stored under `%LOCALAPPDATA%\ResumeForge\workspace`.

For development from a Windows source checkout with Python installed, run **Launch ResumeForge on Windows.cmd**. To recreate the downloadable installer, run `python tools/windows/build.py --work dist/build --out dist/windows` with Go and NSIS available. `tools/windows/runtime-lock.json` records the downloads and SHA-256 hashes.

## Start on this Mac

Double-click **Launch ResumeForge.command**, or run:

```sh
./"Launch ResumeForge.command"
```

The app opens at **http://127.0.0.1:8766**. Keep its terminal running; press Control+C to stop. Python dependencies are installed separately under `~/Library/Application Support/ResumeForge/venv`. On this Intel Mac, Qwen3.5-4B Q4_K_M is installed separately under that same ResumeForge support folder. The app starts its loopback inference service when first needed and the service releases model memory after five idle minutes. The app binds only to the local computer.

If port 8766 is occupied, run `python -m resumeforge serve --port 8767 --open` using the installed environment. A running instance can be reopened at its existing URL.

## Use it

1. The supplied resume is preloaded as a checked structured profile. Import a PDF/DOCX to inspect another source. Generic AI-assisted import requires a model; without one, extracted text is available for manual profile mapping. Review job assignments and extracted fields before generation.
2. Paste the posting, then enter your own editing instructions and optional priority keywords in their separate fields.
3. The installed laptop model is preselected on a fresh workspace. A previously saved draft can restore its prior settings. Select the sequential workflow under Engine settings, or choose **No model · layout only** to exercise the renderer using original bullets and confirmed facts.
4. For a starting point, open **Brainstorm bullet ideas**, choose the job from your resume, and optionally describe a topic. You get editable fictional accomplishments with example tools, details, and numbers. Replace them with what actually happened (or remove a number you did not measure), confirm your corrected wording, and add it as experience. Generating ideas alone does not change a resume, even in the normal rewriting workflow. You can also add role-specific experience directly under **Add verified experience**. Only add work you can confirm. This gives the engine useful material beyond what is already on the one-page resume.
5. Under **Experience wording**, choose **Generate tailored wording** for new prose or **Use only my verified wording** to rank and select exact statements from their original roles. In the latter mode, add your preferred alternative accomplishments as verified role facts; the Skills row can use existing profile labels only. Build and inspect the PDF, keyword coverage, changes, and measured fit.
6. For proposed claims, select the correct job, replace questions with a complete factual accomplishment, then check the confirmation box. Unchecked proposals are excluded. Apply the reviewed edits to render and check again.
7. Download becomes available when the one-page geometry and content checks pass. The preview remains available for a failed draft; it is not an approved export.

Skill selection can promote a requested technical term from confirmed role evidence into an existing Skills row, retain relevant source labels, and remove less relevant listed skills. A tool appearing only in a posting cannot establish experience. Personal strengths stay out of the technical skills list; the writing model can express a supported strength through a concrete accomplishment.

Advanced editors expose the source profile and candidate plan as JSON. Editing the source is an assertion that its facts are accurate. Editing a candidate is subject to the same review checks as model writing. Save draft explicitly to retain the editable state in this browser.

## What the fitting loop does

The template uses US Letter, 40-point margins, embedded Liberation Sans, 12-point body text with 13.2-point leading, 14-point section headings, and a 32-point name. It follows the supplied PDF's overall structure. Liberation Sans replaces the source's unembedded Helvetica with stable, distributable fonts. This is a controlled reconstruction, not a pixel-identical edit of arbitrary PDF objects. Dates, rules, bullet indents, and section spacing are fixed by the template.

Each bullet has a stable slot and can have multiple complete wording alternatives. Alternatives cite source evidence from the same job. The optimizer measures the actual paragraphs that the renderer draws, considers omissions, preserves at least two bullets per job (or all available if fewer), and searches for a combination that fits. It accounts for font descenders, not just nominal line boxes. It prefers relevance and writing quality among sufficiently full combinations.

The target is **one page ending within 13.2 points of the fixed bottom boundary**, with no text outside the margins. Both text bounding boxes and content blocks are checked. The remaining physical bottom margin stays 40 points. The engine never changes font size, leading, tracking, or margins to force a fit.

With AI enabled, a failed fit produces measured feedback and requests revised wording, up to the configured round limit. The selected text then receives a separate semantic review for fidelity, coherence, repetition, and stuffing. If content is insufficient, incoherent, or overflowing after the limit, export remains blocked. No amount of fitting can create truthful experience that is absent from the source.

The PDF is reopened to verify page count, text boundaries, exact selected-bullet text extraction, consistent font sizes, and bottom fill. `result.json` records the template fingerprint, PDF SHA-256, per-pass measurements, selected changes, and review result. Layout percentages describe page use, **not ATS matching**. Keyword presence is not a prediction of ranking or hiring outcomes.

## Installed laptop model and PC handoff

The laptop uses **Qwen3.5-4B Q4_K_M** with the pinned Intel build of llama.cpp (b12189). On this Mac the local OpenAI-compatible endpoint is `http://127.0.0.1:18766/v1`, model ID `resumeforge-qwen35-4b`. Pick **Sequential editor and reviewer**. The app starts the model on demand, uses four CPU threads, one inference slot and an 8,192-token context. The target brief, evidence ranking, short and detailed wording variants, factual review, and final instruction check are separate tasks. The source profile's contact details aren't needed for the laptop's bullet-writing calls. No model download is part of normal app startup. The standalone model installer, if needed on another compatible Intel Mac, is `tools/install_laptop_model.py`. It pins both downloads and checks their SHA-256 digests.

The 2.74 GB weights are an Unsloth conversion of Qwen's Apache-2.0 model. Installed outside the app: weights, verified inference runtime, and the Python environment. The ZIP contains code and small training artifacts, not the multi-gigabyte base model. The actual hardware observations, training comparisons and live tests are in the accompanying laptop validation report. [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-4B) · [exact quantization revision](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523) · [runtime release](https://github.com/ggml-org/llama.cpp/releases/tag/b12189).

On the PC, use the Windows desktop installer above. Reuse the cases in `evaluation/` to compare candidate local models on that hardware.

If you deliberately configure a remote endpoint instead, that service receives the data required for its tasks. Keys for such services are read from an environment variable and not stored as secrets in the UI. The installed laptop endpoint needs no key.

## Storage and privacy

- Original input files are read without modification. Upload inspection is in memory.
- Generated previews, checked PDFs, selected candidates, and run reports are stored in `.local-runs/` beside the source when using the launcher. These contain your resume content. You can choose a different folder with `--data-dir`.
- Browser drafts use localStorage only after Save draft. Clear saved draft removes that browser copy, not generated files on disk.
- The packaged example is your personal resume. Remove or replace both `examples/abu.profile.json` and `resumeforge/data/abu.profile.json` before distributing the app to other people.
- Documents and job postings are data, never executable instructions. The DOCX template's editing advice is not treated as resume evidence.

## Integrate with JobPilot

The core API is Python:

```python
from pathlib import Path
from resumeforge.engine import run
from resumeforge.models import RunRequest

request = RunRequest.model_validate(payload)
result = run(request, Path("jobpilot-output/run-001"))
if result["status"] == "ready":
    # Only this branch has a checked resume.pdf.
    pass
```

The local HTTP API exposes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/bootstrap` | Example profile and default settings |
| GET | `/api/health` | App readiness |
| POST | `/api/ideas` | Return editable fictional bullet ideas for one role; does not create a run, edit evidence, or render a PDF |
| POST | `/api/model-health` | ModelSettings JSON; inspect provider readiness |
| POST | `/api/import` | `{filename, data_base64, settings}`; inspect/map a document |
| POST | `/api/run` | RunRequest JSON; returns HTTP 202 with a run ID |
| GET | `/api/runs/{id}` | Poll until ready, needs_content, needs_review, or failed |
| GET | `/api/runs/{id}/preview.pdf` | Draft preview after rendering |
| GET | `/api/runs/{id}/resume.pdf` | Checked output; HTTP 409 unless ready |

Use `Content-Type: application/json`. The local server accepts same-origin browser calls and local API clients; it is not a public hosting service. It serializes model/render jobs, limits the queue, rejects foreign browser origins, and does not log request bodies. Run IDs are kept in memory for the server session; reports and PDFs remain on disk after restart.

`RunRequest` fields are `profile`, `job_description`, `edit_request`, `keywords`, `settings`, optional `plan`, and `confirmed_claim_ids`. Send `plan: null` for a fresh content plan; send the returned plan plus explicit confirmations to apply reviewed claims. A confirmed proposal becomes a role-specific fact in the returned profile. Retain that returned profile for later runs.

## CLI and development

Requires Python 3.10 or newer. On another machine:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: .
.venv/bin/python -m resumeforge serve --open --port 8766
```

Run a source-only check:

```sh
python -m resumeforge run --profile examples/abu.profile.json --out ./my-run
```

Inspect an input:

```sh
python -m resumeforge inspect /absolute/path/to/resume.pdf
```

Run tests:

```sh
python -m unittest discover -s tests -v
```

Tests include actual PDF rendering and extraction, fitting failures, immutable typography, source/role grounding, reviewed claims, upload parsing, model JSON contracts, and a measured multi-pass loop with simulated model responses. Additional live-model tests are in `evaluation/`; see the dated validation results. A checked PDF is not a certification for unchecked submission. The report field `unattended_submission_qualified` is false.

## Current scope

This version supports the supplied resume's single-column, one-page structure: experience, skills/certifications/interests, and education. It does not provide OCR, arbitrary PDF layout cloning, multi-column/multi-page templates, a native macOS window, or DOCX output. Generic import is conservative and may require manual mapping. A model-assisted semantic reviewer is a useful check, not a guarantee of factual correctness. Review the finished wording before using it in an application.

The font files remain under their included SIL Open Font License. No original PDF/DOCX is bundled in the application.
