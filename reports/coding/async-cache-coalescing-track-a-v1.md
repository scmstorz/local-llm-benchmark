# Async cache coalescing — Track A v1

None of the five deployments solved the JavaScript asynchronous-cache task.
Four returned valid, scoped replacement files and reached both deterministic
test layers, so the zero-success result is a behavioral capability finding
rather than another artifact-transport floor.

## Results

| Order | Deployment | Public | Hidden | Verified | Wall time |
| ---: | --- | ---: | ---: | --- | ---: |
| 1 | `ornith-1.5:35b` | 2/4 | 3/8 | fail: public | 12.38 s |
| 2 | `muse-glimmer:30b-mlx` | 4/4 | 5/8 | fail: hidden | 60.84 s |
| 3 | `qwen3.6:35b-a3b-mxfp8` | 2/4 | 3/8 | fail: public | 34.08 s |
| 4 | `gpt-oss:20b` | not run | not run | fail: empty output | 39.35 s |
| 5 | `qwen3.8:27b-mlx` | 4/4 | **6/8** | fail: hidden | 20.89 s |

The preregistered primary result is 0/5 verified successes. Test counts are
useful diagnostics but do not constitute partial task success. No minimum
sufficient model exists in the tested set for this case.

## Model-level findings

- Qwen 3.8 was closest at 10/12 checks. It handled ordinary caching,
  coalescing, fulfillment-time TTL, `undefined`, asynchronous and synchronous
  failures, and per-key independence. It failed both invalidation races because
  a caller arriving after `invalidate()` or `clear()` still received the old
  in-flight promise instead of starting a fresh attempt.
- Muse Glimmer passed all public tests and 5/8 hidden checks. In addition to the
  same two invalidation races, its cleanup ordering retained a rejected promise
  after a synchronously thrown loader call.
- Ornith reproduced its excluded smoke byte for byte. Its inverted ownership
  check prevented normal values from being cached and allowed stale completion
  after invalidation. It passed 5/12 checks.
- Qwen 3.6 also passed 5/12. It treated absence from the settled-value map as an
  invalidation marker, which prevented ordinary successful loads from entering
  the cache.
- GPT-OSS consumed all 3,000 output tokens in hidden reasoning and emitted no
  visible candidate file. The attempt remains an `empty_output` failure; no
  retry or controller repair replaced it.

## Cross-case interpretation

The ranking changed materially from the Python pagination case. Ornith and
Muse Glimmer had no known counterexample under its corrected verifier, whereas
both failed here. Qwen 3.8 was the closest candidate here but had a post-hoc
counterexample on pagination. This supports the project's core premise:
coding capability is conditional on the task, language, state model, harness
and verifier rather than a single scalar property of a model.

The verifier exposed a specific shared boundary. The two strongest candidates
understood caching and most concurrency mechanics but did not model
invalidation as both cancellation of cache ownership and permission for a new
attempt. That is exactly the kind of difference hidden tests are intended to
surface.

## Execution controls

The initial resource gate did not pass: `fseventsd` remained near 100% CPU and
18.1% memory, so no model attempt was started. After the user ended that
runaway process, macOS restarted it normally. The repeated 30-second gate
observed only 0.08 CPU seconds from the new process. All model digests matched
the frozen plan, Ollama was empty, News-App and the user-facing Mnemosyn worker
were absent, and the three Mnemosyn MCP helpers plus persistent Behat
infrastructure were idle.

The authoritative `EDACB` order was preserved. Every elevated Ollama
generation stopped with verification pending, its output was inspected for
scope and safety, and only then did the separate workspace-sandbox command run
Node.js 22.22.1 verification. Each model was explicitly unloaded after its
attempt. Ollama remained empty through the 30-second postflight. There was no
warm-up, retry, repair, adaptive repeat or test feedback.

## Interpretation limits

This is one development task and one attempt per deployment. It can identify
verified behavior and failure modes for this case, but it cannot estimate
general coding superiority, reliability, stochasticity, latency tails or a
language-wide capability hierarchy. Wall times are exploratory cold-attempt
diagnostics, not performance distributions.
