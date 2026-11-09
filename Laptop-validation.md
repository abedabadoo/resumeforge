# ResumeForge on the Intel MacBook · November 8, 2026

**Use Qwen3.5-4B locally on this laptop. Keep newly generated wording under review.** It completed the representative workload without increasing system swap; the larger candidate exceeded the test’s memory budget. We trained and loaded two real adapters on the Mac, but neither fixed the factual problems that mattered in the output. The shipping writer and reviewer therefore use the original 4B weights. A separately trained factual-risk filter is active as an additional veto.

[Open the installed app](http://127.0.0.1:8766). Choose **Generate tailored wording** to get rewrites and inspect their before/after text. Choose **Use only my verified wording** to let the engine rank source material while allowing only an exact experience statement from its original employer and slot to print. The latter can also use a fact you explicitly confirmed for that job; its Skills row can contain only labels already in your profile. If there is too little suitable material, it can withhold the PDF rather than pad the page. It still cannot promise the right selection for every job.

## What the laptop could actually run

Intel Core i7-8569U, four physical cores/eight threads, 16 GiB RAM, integrated Iris Plus 655, macOS 15.8.1. In Activity Monitor, memory used was 10.84 GB in an initial observation and 12.17 GB while running the 4B trial. Swap was already in use: 2.15 GB and 1.80 GB at those respective snapshots. These are whole-system readings; they are separate from the process RSS and within-trial swap growth below.

| Measured on the active laptop | 4B Q4_K_M | 9B Q4_K_M |
|---|---:|---:|
| Peak sampled process RSS | 4,808 MiB | 8,516 MiB |
| Maximum system swap increase during trial | 0 MiB | 864 MiB |
| Completed raw model judgments | 8/8 correct | 0 completed |
| Median generation speed across completed calls | 7.0 tokens/s | No result |

The 9B model loaded but crossed the predefined 768 MiB swap-growth threshold on its first prompt. Its test stopped there. This establishes a practical memory tradeoff on this Mac, not a writing-quality comparison or a claim that 9B can never run. The 4B trial also generated one unscored writing sample. Neither public leaderboards nor eight judgments establish which model writes the best resumes. [4B measurements](evaluation/results/laptop-2026-11-08/size-4B.json) · [9B measurements](evaluation/results/laptop-2026-11-08/size-9B.json).

The app runs the text model on the CPU, one request at a time, with four threads and an 8,192-token context. Ranking, generating alternatives, checking claims, checking the applicant’s directions, and measuring PDF fit are separate steps. Normal operation uses localhost, no API key and no Codex quota. Under this workload a whole resume took minutes. A failed first attempt on the real profile took about 11½ minutes over three rounds; those rounds were *not* a successful export.

Source: [Qwen's Apache-2.0 model card](https://huggingface.co/Qwen/Qwen3.5-4B), [pinned 4B quantization](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523), [pinned 9B quantization](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/3885219b6810b007914f3a7950a8d1b469d598a5), [llama.cpp Intel runtime b12189](https://github.com/ggml-org/llama.cpp/releases/tag/b12189). The installed 4B GGUF is 2,740,937,888 bytes; SHA-256 begins **00fe7986ff5f**. Full pins and checks are in [the installer](tools/install_laptop_model.py). Runtime and base weights live under the user's Library/Application Support/ResumeForge directory, outside the project and its ZIP.

## What was trained

| Component | Actual training and separate tests | Decision |
|---|---|---|
| Writing adapter, rank 4 | Trained on 24 source-specific faithful/unfaithful continuation contrasts. Base and adapted models both preferred the faithful next token on 12/12 new source pairs and passed all six automated free-writing probes. Held-out pair loss improved from 0.00426 to 0.00362. | **Leave off.** Five of six full bullets were identical. Both versions turned before/after counts into an implied personal achievement and blurred rollout leadership with personal deployment. [Paired outputs and qualitative grades](writer_adapter/README.md) |
| Evidence-review adapter, rank 1 | 24 labeled comparisons from 12 source groups; 16 held-out claims from eight other groups. Base and adapted models both classified 16/16. Log loss worsened from 0.04237 to 0.07205. | **Leave off.** No demonstrated gain. [Native results and weights](laptop_adapter/README.md) |
| Auxiliary factual-risk classifier | 270 training pairs, 90 calibration pairs, 40 handwritten challenge pairs. Caught 12/20 unsafe claims and wrongly held 1/20 valid claims. | **Use only to veto.** Passing never establishes truth. [Full results](training/guard-report.json) |

The adapters changed measured native inference scores when loaded in llama.cpp. They are small updates to one model layer, not full retraining. The datasets use synthetic material rather than your personal resume. Automated writing probes are deliberately supplemented by a source-by-source comparison of what the model actually wrote.

## How the application did

All 44 separately authored cases completed with **37 passing and zero execution errors**. Tests included employment attribution, inflated metrics, role isolation, unsupported tools, unsupported credentials, prompt injection, instruction following and fixed PDF geometry. Of 44 cases, 36 made a model request, 72 chat requests in total. Other cases were decided by code or the trained veto. These are system results, not an ATS score, a model accuracy estimate or 44 completed resumes.

| Test | Passed | What went wrong |
|---|---:|---|
| Factual review | 18/22 | Accepted one of 12 invalid claims (treating an endpoint as a reduction); rejected three of ten valid paraphrases. |
| Content planning | 10/10 | All stated checks passed; the grader only inspects selected anchors and cannot detect every unsupported relationship. |
| Editing-instruction judgments | 6/8 | Accepted a forbidden change to body font and a request to both include and remove the same skill. |
| PDF geometry | 3/3 | Correctly held sparse/overflowing inputs and exported the sufficiently full page. |
| Full targeted PDF generation | 0/1 | Exported a good-looking page but the requested shorter bullet became longer. |

[Original manifest](evaluation/results/laptop-2026-11-08/manifest.json) · [all outcomes](evaluation/results/laptop-2026-11-08/observations.jsonl) · [failure analysis](evaluation/results/laptop-2026-11-08/failure-audit.md). The original manifest hashed files at launch. A phrase-grounding change reached disk seconds after launch, so the precise code for the first worker cannot be attested; subsequent workers read the updated tree. Treat this as an observed run, not a bit-for-bit benchmark of the final build. An earlier interrupted development run is excluded. The updated harness checks for source changes between cases and compares wording within its own role and slot.

The app now measures comparative claims, rejects incompatible layout commands and contradictory Skills instructions, and gives the writer a measured word budget for an identifiable length request. The fitter must keep the intended slot and the final check measures the selected text. A missing valid rewrite holds export. Additional checks flag some changes in which tool performed an action or which outcome an action achieved. These checks are bounded and can also hold legitimate paraphrases. The release passes **82 automated application tests**, including real PDF rendering; many use controlled model responses. Live regression results below are reported separately.

**Retest of the seven prior failures: four passed, three valid paraphrases are still held.** With the same model, the corrected system rejected the bad numeric claim, incompatible font change and contradictory Skills request. It also produced a document that actually shortened the intended PostgreSQL bullet from 17 words to 15 while keeping the discrepancy context; final ink ended 2.07 pt above the fixed bottom boundary. This is a targeted regression result on known problems, not a new score across all 44 or a fresh reliability estimate. [Retest summary](evaluation/results/laptop-2026-11-08/regression-summary.json) · [case outputs](evaluation/results/laptop-2026-11-08/regression-observations.jsonl).

## One real resume, inspected

On the real cloud-engineering brief, the first development attempt ended 28.91 pt above the target bottom boundary and withheld export. A later AI-generated version fit within 2.51 pt but moved “AWS” from “configuration” to “authentication” in a list. It also tied Datadog to bug-bounty tracking without evidence and added an unstated claim that the entire hardening scope was complete. That draft is **not the delivered example**. It illustrates why writing and geometry have to be checked independently.

For the delivered example, the editor separated already-documented AWS hardening and Datadog/Slack actions and kept nine other source statements verbatim. No invented metrics were confirmed. The real local model then reviewed the corrected claims and the original editing brief. The delivered, searchable PDF matches the visually inspected page byte for byte: **one US Letter page; 40 pt fixed margins, 12 pt body, 13.2 pt leading; final visible ink 11.71 pt above the bottom content boundary** (tolerance 13.2 pt). Terraform, Prometheus and Grafana were not asserted. GitHub Actions remains listed as an existing skill rather than an invented claim about a CI/CD project. PDF SHA-256: 6dfff06de9d005719680604ae5eaa784f6d9a0a49d7215ad48864df72e644c49. This is an editor-assisted demonstration; the engine did not independently produce the corrected wording.

A separate request through the running desktop app exercised **Use only my verified wording** on a cloud security brief. All 11 selected experience statements matched their source text and role exactly, and all selected skills came from the original skills list. The app held the export because the exact source material ended outside the page-fill tolerance; measured ink gap 28.91 pt. [Live result](evaluation/results/laptop-2026-11-08/verified-wording-live.json).

## Moving to the PC

Transfer the ZIP and extract it. It includes the app, evaluation runner and labels, synthesis and training scripts, and both candidate adapters. The Mac binaries, large weights and virtual environment are not transferable. Use the Windows launcher and a local model endpoint appropriate to the PC. The CUDA QLoRA recipe includes **300 training conversations and 100 validation conversations**; it has not been run on the uninspected PC. [PC setup and training recipe](training/README.md).

Before changing the default model, record the PC’s GPU model, dedicated VRAM, RAM and runtime, then compare the base model and any candidate adapter on the same jobs with the same decoding settings. Keep the old 44 cases as regressions. For any claim about unchecked submissions, use new real job briefs and independently graded before/after bullets spanning relevant roles; count false approvals, false holds, missed edits, and full-page export failures separately. A perfect score on familiar cases would not establish unattended reliability.
