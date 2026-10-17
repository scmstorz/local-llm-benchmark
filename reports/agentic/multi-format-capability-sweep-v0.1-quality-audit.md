# Multi-Format Capability Sweep v0.1 — Supplemental Quality Audit

The required separate prose review is complete. It covers claim polarity,
source entailment, wording accuracy, epistemic calibration, German writing
quality and usefulness for the steering decision. It does not repair or replace
the deterministic verifier and does not create a composite score.

## Outcome

- 13 of 15 cells produced a parseable candidate report.
- 7 of those 13 reports pass the supplemental prose review.
- 6 fail the prose review; 2 are not applicable because no report was produced.
- The two deterministic semantic successes, positions 8 and 12, both pass this
  review and strict transport. The combined fully accepted result is therefore
  2 of 15 cells.

## By condition

| Condition | Applicable | Pass | Fail | N/A |
| --- | ---: | ---: | ---: | ---: |
| `canonical-representation-v0.1` | 5 | 1 | 4 | 0 |
| `mini-multi-format-v0.1` | 3 | 3 | 0 | 2 |
| `pi-multi-format-v0.3` | 5 | 3 | 2 | 0 |

## By model

| Model | Applicable | Pass | Fail | N/A |
| --- | ---: | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | 3 | 1 | 2 | 0 |
| `qwen3.8:27b-mlx` | 3 | 2 | 1 | 0 |
| `muse-glimmer:30b-mlx` | 2 | 1 | 1 | 1 |
| `ornith-1.5:35b` | 2 | 1 | 1 | 1 |
| `gemma4:31b-mlx` | 3 | 2 | 1 | 0 |

## Material findings

| Position | Classification | Finding |
| ---: | --- | --- |
| 1 | contradictory West approval | The prose calls West a passing region while also recording its 94% completion against the 95% threshold. |
| 4 | contradictory West approval | The prose approves West and repeats that it may launch even though the same report contains West's failed completion value. |
| 6 | unsupported regulatory characterization | The rollout-policy gates are described as regulatory requirements, which is stronger than the dossier establishes. |
| 7 | German language requirement not met | Most explanations, evidence descriptions, rationales and uncertainty reasons are English although all free text was required in German. |
| 10 | contradiction and unsupported exception | The prose both approves and blocks West and suggests an exception path absent from the dossier. |
| 15 | dashboard recommendation conflicts with phased policy | A proposed portfolio-wide HOLD rule would obscure the policy's valid North-only phased launch. |

Minor spelling or grammar defects were not treated as failures when meaning and
decision usefulness remained unambiguous. Likewise, an omission already caught
by a deterministic completeness check did not automatically fail this prose
layer; the deterministic failure remains unchanged.

The judge was the interactive Codex session and was not blinded to run order,
model identities or deterministic outcomes. Raw candidate text, document
contents, hidden references and absolute paths remain excluded from this public
audit.

Every exact system/model observation is still n=1. Track A and Track B remain
separate, and the result supports neither reliability rates nor a causal
Mini-versus-Pi comparison.
