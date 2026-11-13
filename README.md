# ResumeForge

A native Windows and Intel macOS desktop app for tailoring a resume and saving a checked PDF. A browser interface is also available for local use. It turns a structured profile into a searchable, selectable PDF using a fixed template. The writing model proposes content; the renderer controls typography. No ChatGPT subscription, conversation, or Codex process is needed to run the installed app.

[Laptop evaluation, training results and known limits](Laptop-validation.md)

## Install on Windows

Download **ResumeForge-Setup-x64.exe** from the [Windows desktop release](https://github.com/abedabadoo/resumeforge/releases/tag/v0.4.1). Run the installer, then open **ResumeForge** from the Start menu. The installer includes Python, the native Qt interface, fonts, and the PDF engine. If you prefer a portable copy, extract the entire **ResumeForge-Windows-x64.zip** and launch **ResumeForge.exe** inside its folder. Both builds target 64-bit Intel and AMD Windows PCs.

A fresh public install opens a fictional demo profile. An upgrade opens your previously saved workspace. Import your resume or open your existing profile, then choose **Analyze job description** to see the posting’s ranked priorities.

The first launch can build with offline examples. To generate new wording with Qwen, start your local model service on your PC. Open **Model settings**, select **Ollama** or **OpenAI-compatible endpoint**, enter the service URL, and choose **Find installed models** or enter its model name. The PC model is a separate installation. Your workspace, generated previews, and run reports are stored under `%LOCALAPPDATA%\ResumeForge\workspace`.

For development from a Windows source checkout with Python installed, run **Launch ResumeForge on Windows.cmd**. To recreate the downloadable installer, run `python tools/windows/build.py --work dist/build --out dist/windows` with Go and NSIS available. `tools/windows/runtime-lock.json` records the downloads and SHA-256 hashes.

## Install the native app on an Intel Mac

Download the latest **ResumeForge-macOS-Intel.dmg** or **ResumeForge-macOS-Intel.zip** from the [GitHub Releases page](https://github.com/abedabadoo/resumeforge/releases). The packaged **ResumeForge.app** runs on Intel (x86_64) Macs with **macOS 13 or newer**. Open the DMG, drag the app into Applications, then double-click ResumeForge. It includes the Python runtime and native Qt window; there is no need to install Python or start a web server.

The Intel Mac preview is **not Apple Developer ID signed or notarized**. macOS may prevent the first launch; if you trust the downloaded file, use Finder's Open command or **System Settings → Privacy & Security → Open Anyway**. The app opens a fictional starter profile and stores your workspace in `~/Library/Application Support/ResumeForge/workspace`.

The downloadable app does not include AI model weights. You can run it without a model or configure Ollama / an OpenAI-compatible local endpoint in **Model settings**.

### Updating on Intel Mac

This build introduces **Check for updates…** in the desktop toolbar. After the first installation of an updater-enabled version, you no longer have to download a DMG and manually drag ResumeForge into Applications to get subsequent updates. Choose **Check for updates…**, approve the download and installation, and the app will verify the official GitHub release ZIP and its SHA-256 digest, save your workspace, replace the old app after exiting, and reopen automatically. A previous version remains in a hidden `.ResumeForge-previous.app` backup beside the installed copy.

The current updater downloads the complete Intel Mac ZIP **in the background** (roughly 60–70 MB); it is not yet a differential/delta updater. It only accepts official releases with a matching digest, verified macOS app signature, and Intel binary. It never installs without your confirmation. If ResumeForge was launched from a DMG or a protected installation folder, the new copy is installed under `~/Applications/ResumeForge.app`, where later updates can replace it without asking for administrator privileges. Launch the new copy from that folder and update any Dock shortcut pointing to the old location. Your workspace is always separate at `~/Library/Application Support/ResumeForge/workspace`.

For local development, use `python -m pip install -e ".[desktop]"` and `python -m resumeforge.desktop`. The build script is `tools/macos/build.py` and the Intel macOS GitHub Actions workflow creates ZIP and DMG downloads.

## Alternative: browser version on Mac

Double-click **Launch ResumeForge.command**, or run:

```sh
./"Launch ResumeForge.command"
```

The app opens at **http://127.0.0.1:8766**. Keep its terminal running; press Control+C to stop. Python dependencies are installed separately under `~/Library/Application Support/ResumeForge/venv`. On this Intel Mac, Qwen3.5-4B Q4_K_M is installed separately under that same ResumeForge support folder. The app starts its loopback inference service when first needed and the service releases model memory after five idle minutes. The app binds only to the local computer.

If port 8766 is occupied, run `python -m resumeforge serve --port 8767 --open` using the installed environment. A running instance can be reopened at its existing URL.

## Use it

1. Open your profile or import a resume. Generic PDF/DOCX import uses the configured model to map extracted text to the right jobs. You can also supply structured profile JSON.
2. Paste the posting and choose **Analyze job description**. Review the ranked capabilities and their supporting evidence. ResumeForge distinguishes exact matches, related experience, and gaps. Add, remove, or reorder the priorities and give any editing instructions before building.
3. **Generate new example achievements** is the default. It writes replacement bullets for relevant roles and can invent projects, tools, and numbers. Each example belongs to the current draft. The PDF prints it as ordinary resume prose. The app shows which bullets it generated. With the model disconnected, the editor draws on built-in examples.
4. Choose **Build resume**. Use **Edit generated bullets** to change wording or clear an example, then refit the page. **Save checked PDF** exports the version shown in the preview after its page and content checks pass. For applications, replace invented claims with your actual experience.
5. To work from your source alone, choose **Rewrite using my experience**, or choose **Use my verified wording** for exact source statements. You can add confirmed, role-specific experience to the profile separately.

The Skills row prioritizes both explicitly named tools and skills relevant to the broader capability. For example, cloud infrastructure can support retaining AWS and IaC, while Microsoft Azure alone does not establish Azure DevOps experience.

Advanced editors expose the source profile and candidate plan as JSON. Editing the source is an assertion that its facts are accurate. Editing a candidate is subject to the same review checks as model writing. Save draft explicitly to retain the editable state in this browser.

## What the fitting loop does

The template uses US Letter, 40-point margins, embedded Liberation Sans, 12-point body text with 13.2-point leading, 14-point section headings, and a 32-point name. It follows the supplied PDF's overall structure. Liberation Sans replaces the source's unembedded Helvetica with stable, distributable fonts. This is a controlled reconstruction, not a pixel-identical edit of arbitrary PDF objects. Dates, rules, bullet indents, and section spacing are fixed by the template.

Each bullet has a stable slot and can have multiple complete wording alternatives. Source-backed alternatives cite evidence from the same job. Generated examples have a distinct origin in the run report. The optimizer measures the actual paragraphs that the renderer draws, considers omissions, preserves at least two bullets per job (or all available if fewer), and searches for a combination that fits. It accounts for font descenders, not just nominal line boxes. It prefers relevance and writing quality among sufficiently full combinations.

ResumeForge targets **one page with approximately 13.2 points or less of unused space before the fixed bottom boundary**, but this is a *visual preference, not an export requirement*. A readable one-page PDF is export-ready when text stays inside the actual 40-point margins, the selected content survives PDF extraction, and content checks pass—even if the page cannot be filled exactly. The engine automatically tries longer or shorter alternatives when available, and can trim low-priority skills to protect the single-page layout. It never changes font size, leading, tracking, or margins merely to force a fit.

With AI enabled, a failed fit can request shorter or longer bullet alternatives based on measurements from the rendered page. The renderer selects the best completed pass within the configured round limit. Example drafts check page geometry, printable prose, and editing instructions. Source-backed rewrites also check evidence. Edited examples retain the exact wording you chose.

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
- Public Windows packages include a fictional starter. A personal build can set `--starter-profile path/to/profile.json`. Source checkouts use the profile under `resumeforge/data/`.
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
| POST | `/api/analyze` | Send `profile`, `job_description`, and optional `keywords` to get the ranked priorities and source evidence |
| POST | `/api/ideas` | Return editable fictional bullet ideas for one role; does not create a run, edit evidence, or render a PDF |
| POST | `/api/model-health` | ModelSettings JSON; inspect provider readiness |
| POST | `/api/import` | `{filename, data_base64, settings}`; inspect/map a document |
| POST | `/api/run` | RunRequest JSON; returns HTTP 202 with a run ID |
| GET | `/api/runs/{id}` | Poll until ready, needs_content, needs_review, or failed |
| GET | `/api/runs/{id}/preview.pdf` | Draft preview after rendering |
| GET | `/api/runs/{id}/resume.pdf` | Checked output; HTTP 409 unless ready |

Use `Content-Type: application/json`. The local server accepts same-origin browser calls and local API clients; it is not a public hosting service. It serializes model/render jobs, limits the queue, rejects foreign browser origins, and does not log request bodies. Run IDs are kept in memory for the server session; reports and PDFs remain on disk after restart.

Set `settings.draft_mode` to `inspiration` (default) or `grounded`. Set `settings.wording_policy` to `verified` for exact source text. Pass the ordered list from the priority review in `reviewed_priorities`. An empty list clears it. Refit edited examples by passing the returned `plan` and `draft_edits` mapping generated candidate IDs to their new text. An empty edit removes that example. Send `plan: null` for a fresh content plan; send the returned plan plus explicit confirmations to apply reviewed claims. A confirmed proposal becomes a role-specific fact in the returned profile. Retain that returned profile for later runs.

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

This version supports the supplied resume's single-column, one-page structure: experience, skills/certifications/interests, and education. It does not provide OCR, arbitrary PDF layout cloning, multi-column/multi-page templates, or DOCX output. The native macOS download is currently an unsigned Intel preview (not a notarized public release). Generic import is conservative and may require manual mapping. A model-assisted semantic reviewer is a useful check, not a guarantee of factual correctness. Review the finished wording before using it in an application.

The font files remain under their included SIL Open Font License. No original PDF/DOCX is bundled in the application.
