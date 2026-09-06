# Log-Incident Qualification Smokes v0.1

Status: **awaiting execution**

The frozen pair contains one excluded `qwen3.8:27b-mlx` development smoke for
each read-only complete system, in this order:

| Position | Complete system | Outcome |
| ---: | --- | --- |
| 1 | `mini-log-v0.1` | not run |
| 2 | `pi-log-v0.1` | not run |

The smokes qualify orchestration, persistence, tool use and deterministic final
verification. They will never enter measured Capability Sweep aggregates and
cannot support a model or harness ranking.

The future report command publishes no candidate response, log contents, hidden
verifier details, raw evidence or absolute local path. Pi and Mini remain
complete-system conditions rather than a one-factor harness experiment.

No live Ollama request was made while creating this report skeleton.

Live execution also requires explicit confirmation that no external development
agent can restart Behat during the smoke; an instantaneous process check alone
cannot guarantee that exclusive interval.
