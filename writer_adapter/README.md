# Writing preference experiment for Qwen3.5-4B

This experiment trains a rank-4 update to the last feed-forward down projection of the locally installed Qwen3.5-4B Q4_K_M. It takes a short piece of work evidence and learns from two possible bullet completions, one faithful and one that changes an important fact. The training signal is a pairwise preference at the first token where the completions diverge. The full-sequence QLoRA recipe for a GPU is in [training](../training/README.md).

The [corpus](cases.json) contains invented work examples. Across six categories it provides 24 training sources, 12 separate sources for measuring token preferences, and six additional sources for generating whole bullets. Categories cover attribution, release stage, scope, measurements, tools and outcomes. Both stronger and weaker claims can be correct when the evidence supports them. A preflight check rejects reused sources and training examples that share a seven-word span with the frozen application qualification files or other evaluation evidence.

## Reproduce

Run on the Intel Mac in an exclusive inference window using Python 3 and NumPy. The command reads the existing base model and runtime from `~/Library/Application Support/ResumeForge`. It verifies the SHA-256 of the base model and release archive, then verifies the installed native libraries against that archive before opening the model.

From the ResumeForge project directory:

```sh
python3 writer_adapter/experiment.py --check-only
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 -u writer_adapter/experiment.py
```

Use a NumPy-enabled Python executable if your default interpreter lacks NumPy. Paths can be supplied with `--model`, `--runtime`, `--archive` and `--out`. This script uses the pinned Intel macOS b12189 ABI and the model digest embedded in the script.

The native library returns the final feed-forward input, residual, and logit margin at each training prefix. The program dequantizes the two associated rows of the tied output embedding and reads the output normalization weights. A training-only SVD chooses four output directions. Gradient descent fits the 36,864 input weights using regularized pairwise logistic loss through the final RMS normalization. It writes the two matrices in llama.cpp's GGUF LoRA format. The rest of Qwen stays frozen.

The experiment first measures the base model. It then loads the adapter in llama.cpp and replays each held-out prefix to measure the actual change in its token preferences. For the six independent prompts it generates fresh, greedy, whole bullets in both configurations. The automated checks look for required details, selected unsupported statements, refusals, malformed answers and truncation. Read each source alongside the generated wording before drawing conclusions. A grammatical token at the divergence can precede the substantive claim, and the source-specific rules cannot detect every omission, invented detail, or change in responsibility.

The script writes `result/qwen35-4b-resume-writing-r4.gguf` and `result/report.json`. The application chooses its model configuration separately. Passing the short-writing probes alone is insufficient evidence for an unattended resume export.

## Result and deployment decision

Keep the base Qwen3.5-4B writer active on this laptop. Both versions preferred the faithful continuation on 12 of 12 held-out pairs and passed the automated checks on six of six generated bullets. The adapter reduced mean pairwise log loss from 0.004256 to 0.003624. Loading the two trained matrices into llama.cpp changed one held-out margin by 0.834 logits. Of the six generated bullets, five were identical and one rephrased projected savings. The fit and evaluations took 334 seconds after model loading.

I compared each generated sentence directly with its source. This was a second, qualitative grading pass by the coding assistant after the run. A stricter source-grounding review identifies two bullets in each configuration that deserve attention before use.

| Evidence | Original and adapted outputs |
| --- | --- |
| Cashier training | Both correctly credit the applicant with training six cashiers and the manager with supervision. Mentioning the manager's responsibilities weakens the bullet's focus. |
| Leak detector | Both preserve the Arduino, the bench test and prototype status. “Which remained in the lab” has an ambiguous antecedent, although neither version claims deployment. |
| Repairs queue | Both give the correct endpoints of 48 and 30 overdue jobs. “Reducing overdue jobs” credits the applicant with causing the drop. The source establishes a before-and-after count only. Flag for revision or confirmation. |
| Projected printing savings | Both preserve the $9,000 annual estimate and the approval condition. The adapter's “would save an estimated $9,000 annually if approved” makes the condition clear. |
| Room-booking rollout | Both preserve the applicant's leadership and all four locations. “Successfully deploying it” could imply personal responsibility for the technical deployment. The source establishes rollout leadership and a completed launch. Clarify the wording before export. |
| QGIS mapping | Both correctly credit the applicant with mapping unsheltered stops and the planning unit with selecting inspection sites. |

The token preference gain did not resolve the two attribution concerns in the generated prose. Keep the adapter as a reproducible experiment. The six probes sample distinct kinds of evidence and are too few to establish a general failure rate. Full machine-scored outputs and digests are in [the run report](result/report.json).
