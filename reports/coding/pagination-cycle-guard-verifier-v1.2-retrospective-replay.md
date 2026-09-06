# Pagination cycle guard — verifier v1.2 retrospective replay

Verifier v1.2 closes the non-empty-start-cursor gap found after the immutable
v1.1 comparison. No model was called. The exact four saved valid candidate
responses were installed again and evaluated with the revised hidden suite.

## Result

| Original order | Deployment | V1.1 frozen verifier | V1.2 saved-artifact replay | Reason |
| ---: | --- | --- | --- | --- |
| 1 | `gpt-oss:20b` | fail | not replayable | no visible artifact |
| 2 | `qwen3.6:35b-a3b-mxfp8` | fail | fail | existing exact-budget test |
| 3 | `qwen3.8:27b-mlx` | pass | **fail** | new non-empty-start-cursor cycle test |
| 4 | `ornith-1.5:35b` | pass | **pass** | all 4 public and 7 hidden tests passed |
| 5 | `muse-glimmer:30b-mlx` | pass | **pass** | all 4 public and 7 hidden tests passed |

The replay caught the one known v1.1 false positive and introduced no
unexpected regression. Qwen 3.6 passes the newly added test but continues to
fail the pre-existing page-limit test. This matters because it demonstrates
that v1.2 is not merely configured to reject every previously unsuccessful
candidate.

## What changed

The candidate-visible task already required the collector never to fetch the
same non-terminal cursor twice. The v1.1 hidden suite tested cycles after a
default `None` start, but omitted a cycle returning to a supplied non-empty
`start_cursor`.

V1.2 adds exactly this scenario:

```text
start_cursor = "resume"
resume -> next -> resume
expected fetches: ["resume", "next"]
expected error cursor: "resume"
```

The task, system prompt, fixture, public tests, visible repository context,
whole-file envelope and inference defaults are unchanged. The case and
benchmark card are separately versioned because the hidden verifier—and
therefore the meaning of `verified_success`—changed.

## Red-to-green controls

- The defective baseline remains red in both public and hidden layers.
- The reference repair passes all 4 public and 7 hidden tests.
- The known Qwen 3.8 counterexample now deterministically fails the added test.
- Ornith and Glimmer still pass the complete suite.

## Evidence boundary

This is a retrospective diagnostic replay, not a fresh v1.2 Capability Sweep.
It made zero inference requests and cannot replace the preregistered v1.1
result of 3/5 frozen-verifier passes. It confirms that, under the corrected
verifier applied post hoc, Ornith and Glimmer are the two saved outcomes that
pass all known requirements.

A fresh v1.2 model comparison is optional. If run later, it needs its own
frozen plan and explicit authorization. The corrected verifier can already be
carried forward into both planned Track B harness configurations.
