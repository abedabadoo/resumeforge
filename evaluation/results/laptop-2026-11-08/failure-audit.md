# Frozen v2 qualification audit

All 44 synthetic cases ran; 37 passed, seven failed, zero execution errors. 36 cases made at least one actual chat request. This is a mixed system suite, not resume accuracy. There were 22 factual review cases, ten plan cases, eight editorial-brief judgments, three geometry checks and one targeted end-to-end export. The frozen result and answer keys were not changed.

| Failure | Observed outcome | Classification |
|---|---|---|
| h-rev-04 | Held an accurate paraphrase of writing meeting notes as documenting the manager's review. | Overstrict model; false hold. |
| h-rev-05 | Held a statement explicitly describing a proposed pilot because the evidence said the pilot was subsequently cancelled. The candidate did not say it occurred. | Overstrict model; false hold. |
| h-rev-18 | Held an accurate comparison of a prototype's recommendations. The evidence added a non-deployment disclaimer; the candidate retained the prototype qualifier without that sentence. | Learned veto reacted to removed negation; false hold. |
| h-rev-12 | Accepted a change **by 30** when the source specified **from 40 to 30**. Every number was present but its relationship was wrong. | Unsafe false approval, not caught by the previous token-presence check or model. |
| h-req-04 | Accepted an instruction to change fixed body font to 20 points. | Unfulfilled constraint wrongly approved; template itself remained fixed. |
| h-req-05 | Accepted directives to both include and remove the same skill from the same list. | Contradictory brief wrongly approved. |
| h-pdf-04 | Exported a geometrically valid PDF as ready although the requested database bullet grew from 17 to 20 words. | Instruction fulfillment false approval. A polished page concealed a missed edit. |

Factual reviewer: one false approval among 12 invalid claims and three false holds among ten valid paraphrases. Two of eight request-judgment cases misjudged unfulfillable briefs. All ten planning scenarios passed their stated checks; that is not proof every admitted alternative was faithful. Independent PDF checks caught the single E2E failure the semantic gate missed.

## Corrective changes

Added a deterministic comparison check for explicit start/end versus amount-of-change, including reversed ranges and unit-aware percentage interpretation. Explicitly incompatible typographic commands and opposing directives for the same named profile skill/field are now held without relying on the language model. For a resolved singular shorter/longer bullet, filter layout choices by measured word length and require the source slot to survive the fit. Reject ambiguous target resolution, omission or failure to shorten/lengthen; do not silently rate a different fact as success. No model-training data or test labels changed. Seven independent no-inference regression checks pass, including a real PDF typesetter selection. Replaying frozen inputs shows the new rules recognize the three unsafe condition classes and correctly identify the previously missed target. The old PDF plan contained no valid shorter alternative, so its corrected outcome is a *hold*, not proof of a successful live repair.

## Remaining limits

These are bounded parsers for common comparisons, layout commands, known skills and identifiable singular word-length requests, not a general purpose language interpreter. They may refuse valid ambiguous instructions; they cannot establish every fact, handle every numeric or unit conversion, or guarantee a valid alternative exists. No blanket weakening of the three historical false holds was made. A stronger generation pass should explicitly target word budgets and retry eligible alternatives, with fresh validation. The original 37/44 is the valid pre-correction score; these are now regression cases, not a fresh independent post-correction score. No unattended submission qualification.
