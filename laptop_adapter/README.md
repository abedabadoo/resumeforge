# On-device Qwen training experiment

This is real supervised training of a rank-one LoRA for the pinned Qwen3.5-4B Q4_K_M model. It changes the last feed-forward down projection (blk.31.ffn_down.weight) for one narrow task: answering Yes/No to whether a claim is established by a source. It does not train prose generation. The base file is never modified.

The training set contains 24 labeled claims from 12 synthetic sources. There are 16 held-out claims from eight *different* sources. No resume, job application or private personal data enters this training set. The capture process measures the actual last-layer activations and native Yes-minus-No logit. The output embedding is tied, so the adapter operates on the last FFN rather than changing a shared output/token embedding. A 9,216-value input direction is learned from training labels against a fixed output direction. Fitting uses regularized binary cross-entropy; the decoder's final RMS normalization is included. All training hyperparameters are fixed before the held-out run. The held-out feature rows are not used to fit the weights. Validation reloads the GGUF through llama.cpp and re-runs every held-out prompt, rather than just scoring an offline approximation.

Both base and trained versions classified 16/16 correctly. Binary log loss was **0.04237 base, 0.07205 trained** (lower is better). The largest observed change in the live Yes-minus-No score was 0.87688, verifying the weights had an effect. This experiment did not demonstrate an improvement; **the adapter is not used by the live writer or reviewer**. Do not attach the binary-review adapter to a general writing request.

The adapter and full per-case results are in `result/`. The user can compare future candidates without changing their running app.

## Reproduce on the Intel Mac

Requires NumPy, the exact b12189 x86-64 runtime and the exact SHA-256-verified Q4_K_M file. The native bridge uses an ABI-specific C interface; do not point it at another llama.cpp release. Stop any active generation first to avoid running two large models together. Run from the project folder, substituting your scratch directory:

```sh
RF_DIR="$HOME/Library/Application Support/ResumeForge"
python laptop_adapter/capture.py --runtime "$RF_DIR/inference/b12189/llama-b12189" --model "$RF_DIR/models/Qwen3.5-4B-Q4_K_M.gguf" --features /tmp/rf-states.npz
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python laptop_adapter/fit.py --features /tmp/rf-states.npz --runtime "$RF_DIR/inference/b12189/llama-b12189" --model "$RF_DIR/models/Qwen3.5-4B-Q4_K_M.gguf" --out /tmp/rf-trained-candidate
```

The laptop experiment is separate from the independent application-level holdout in `evaluation/` and the PC writer QLoRA recipe in `training/`.
