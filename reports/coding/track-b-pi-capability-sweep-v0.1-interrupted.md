# Coding Track B Pi capability sweep v0.1 — interrupted cohort

This first eight-model by two-case sweep stopped after the complete PHP block
when the computer crashed. Ollama subsequently changed from 0.32.15 to 0.33.2,
so resuming the same deployment cohort would have violated the frozen runtime
identity. The partial result is retained but is not pooled with the later
complete sweep.

## Completed observations

| # | Model | Verified | Diagnostic outcome | Checks | Active time | Turns / tools |
| ---: | --- | :---: | --- | ---: | ---: | ---: |
| 1 | `qwen3.6:35b-a3b-mxfp8` | no | output-token budget | 4/4 + 8/8 | 197.51 s | 69 / 79 |
| 2 | `qwen3.8:27b-mlx` | yes | verified success | 4/4 + 8/8 | 81.63 s | 6 / 17 |
| 3 | `gpt-oss:20b` | no | incomplete provider stream (inconclusive) | 2/4 + 3/8 | 69.74 s | 13 / 12 |
| 4 | `muse-glimmer:30b-mlx` | yes | verified success | 4/4 + 8/8 | 337.77 s | 13 / 22 |
| 5 | `ornith-1.5:35b` | no | hidden-test failure | 4/4 + 7/8 | 177.13 s | 17 / 25 |
| 6 | `granite4.2:30b` | yes | verified success | 4/4 + 8/8 | 225.97 s | 5 / 11 |
| 7 | `nemotron-3.5-lightning:30b-mlx` | yes | verified success | 4/4 + 8/8 | 108.90 s | 14 / 28 |
| 8 | `gemma4:31b-mlx` | yes | verified success | 4/4 + 8/8 | 190.80 s | 14 / 13 |

Five of eight complete PHP configurations were verified successes. Qwen 3.6
produced verifier-complete code but exceeded the total output budget and did
not terminate validly. Ornith ended normally but missed one hidden check.
GPT-OSS encountered an incomplete provider stream, so its negative outcome is
inconclusive rather than a clean capability failure.

## Exclusions and interpretation limit

The JavaScript block is not reported: its first attempt was nonterminal when
the computer crashed, and the other seven attempts had not started. Completed
terminal units were never retried. With one attempt per configuration, this is
descriptive capability evidence, not a reliability or latency distribution.
