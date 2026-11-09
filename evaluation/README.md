# ResumeForge acceptance evaluation

This is a **local inference** and document-export benchmark, separate from the application unit tests and the training corpus. It uses fictional names with `.invalid` contact addresses. No user resume, live posting, API key, paid external judge, or model download is needed. Run it against an already running local model. Inference jobs are serialized; run on the machine that hosts the model.

There are 16 development cases and 44 separately authored holdout cases. The latter include 22 reviewer judgments, 10 planning tasks, 8 editing-brief judgments, 3 deterministic geometry checks and one end-to-end PDF. Expected decisions and scoring anchors are applied by Python and are not included in prompts. The answer key is visible in these files: do not add holdout rows or their outputs to fine-tuning data, few-shot examples, or model prompts. After adjusting a model based on a holdout failure, treat that set as a regression set; collect a fresh independent set for any new reliability claim.

## Run

From the project directory with the ResumeForge Python environment active. On Windows substitute your Python executable and a writable output path.

```sh
# Inventory; no model requests.
python evaluation/run.py --split holdout --list

# Geometry only, using the actual engine and PDF files.
python evaluation/run.py --split holdout --suite layout --out ../eval-geometry

# A bounded 8-case live smoke on this laptop's configured local server.
python evaluation/run.py --preset laptop-smoke --provider openai-compatible \
  --strategy laptop --base-url http://127.0.0.1:18766/v1 \
  --model resumeforge-qwen35-4b --revision YOUR_GGUF_SHA256 \
  --timeout 240 --case-budget 420 --total-budget 2400 --out ../eval-smoke

# Full frozen corpus; allow more time on an Intel CPU. Run on the PC for through-put.
python evaluation/run.py --split holdout --suite all --provider openai-compatible \
  --strategy laptop --base-url http://127.0.0.1:18766/v1 --model YOUR_MODEL_ID \
  --revision YOUR_GGUF_SHA256 --timeout 240 --case-budget 1200 --total-budget 21600 \
  --repeat 3 --out ../eval-holdout
```

Ollama is also supported via `--provider ollama --base-url http://127.0.0.1:11434 --model MODEL_TAG`. Use `--strategy full` to exercise the full planner on a more capable machine. `--suite review`, `plan`, `request`, `layout`, and `end-to-end` isolate components. For a shorter live trial pass `--case h-rev-01 --case h-rev-02` (with `--split holdout`, provider/model and a new output path). The preset always selects the held-out split. Localhost only; provider=none is restricted to geometry cases. The harness will not use source-only fallback for model tests.

Each case writes a result immediately, with raw synthetic model decisions, failed assertions, elapsed time and observed chat HTTP attempts. These count requests, not successful generations. Some cases can be rejected before inference by deterministic or learned guards: this measures the deployed system and is **not** evidence that the base model got that case right. Model/API errors, timeouts, missing fields or missing trusted edit support do not count as successful safe refusals. The PDF checker independently reopens exports, measures character bounds and typography, tests exact selected-text presence and, on the positive final case, verifies the target bullet actually shortened. A preview is not a checked export.

A fresh output directory is required. Use `--resume` with the same settings and unchanged source, corpus and model identity after interruption: all completed outcomes, including failures, remain in the report. An individual timed-out case counts as a failure; a global deadline can leave unattempted cases. Exit 0 means the requested cases completed and passed, 1 means failures, and 2 indicates incomplete selection or invalid input. Repeated runs with a fixed decoding seed primarily exercise reproducibility, not independent samples.

## What is measured

- **Fact preservation:** human-authored labels distinguish paraphrases from changes in role ownership, median vs. mean, units, metric attachment, old/new values, causality, pilots, proposed technology, scope and credentials. Wrongly accepting an invalid bullet and wrongly rejecting a valid bullet are reported separately.
- **Useful tailoring:** some planner cases must return a novel alternative with the right role, cited evidence, substantive wording anchors and (where requested) a word limit. Retaining every original or rejecting every change cannot pass these. Unsupported terms, unconfirmed experience, job-posting injection and cross-job transfers are tested separately. Skills assertions inspect the core ranking function; the PDF case checks final output.
- **Editing instructions:** applicant briefs are sent through the trusted edit field. Separate cases judge known final content against constraints on skills, wording, unsupported fixed fields, contradictory requests and missing context. These tests do not treat a job posting as a trusted instruction.
- **Fit and export:** insufficient facts must withhold export; an overflowing fixed section must also withhold export. A sufficiently populated synthetic profile must fit actual ink inside the 40-point margins with unchanged font sizes. The full model path must turn the targeted evidence into a shorter, present, searchable bullet.
- **Limits:** lexical anchors are narrow, repeatable checks, not a general entailment oracle. A good paraphrase may miss an anchor; a plausible false claim may evade one. Read predictions and grade borderline cases separately rather than weakening criteria until a particular model passes. The corpus is small and built in English for this layout. No result, even a perfect sweep, establishes universal reliability or safe unattended submission. Independent factual review on representative, previously unseen applications remains necessary before considering any change to approval policy.
