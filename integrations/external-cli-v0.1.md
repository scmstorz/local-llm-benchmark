# Mirror and Mistral Vibe coding integration v0.1

These adapters run two independently versioned complete systems on the existing
PHP payment migration, JavaScript async cache and Python pagination cases.
They reuse the frozen fixtures, candidate file contracts and final verifiers.
The 23-case suite and earlier measured conditions remain unchanged.

| System | Pinned distribution | Selected runtime |
| --- | --- | --- |
| `mirror-cli-v0.1` | `reflection-mirror==0.1.0` | Native Rust agent, Python `exec` client, captured AgentRPC events |
| `vibe-cli-v0.1` | `mistral-vibe==2.26.1` | Python CLI with explicit `--legacy-harness`, streaming JSON and native export |

The exact contract and task subset are in
[`external-cli-v0.1.json`](../tasks/coding/track-b/external-cli-v0.1.json).
Qualification is development evidence, separate from task success and measured
coverage. Log investigation and document reconciliation need their own tool and
output qualifications; this version admits only the three coding cases.
Vibe's unified Rust harness is a different system variant and is not silently
substituted for this explicitly selected Python variant.

## Install without changing account-level harness installations

This backend requires macOS 15 or later on Apple Silicon, `sandbox-exec`, a
working `uv`, ripgrep and the case-specific PHP, Node or Python runtime. The
benchmark controller still supports Python 3.11 and later. The two external
runtimes use their own Python 3.12 environments and independent complete locks.

From the repository root:

```bash
uv python install 3.12.13 --install-dir integrations/.python --no-bin
uv sync --project integrations/mirror --locked --no-install-project --no-build \
  --python integrations/.python/cpython-3.12.13-macos-aarch64-none/bin/python3.12
uv sync --project integrations/vibe --locked --no-install-project --no-build \
  --python integrations/.python/cpython-3.12.13-macos-aarch64-none/bin/python3.12
```

The Python installation and both `.venv` directories are ignored. No dependency
or model is installed globally. Every preparation validates installed wheel
RECORD hashes, package versions against `uv.lock`, and exact executable hashes.
The protocol binds both lock hashes and the selected Apple Silicon wheel hashes.
An incomplete or modified runtime fails before any provider starts.

## Run the offline qualification

```bash
python3 -m local_llm_benchmark.external_cli_qualification \
  --harness mirror \
  --case tasks/coding/dev/async-cache-coalescing/case.json

python3 -m local_llm_benchmark.external_cli_qualification \
  --harness vibe \
  --case tasks/coding/dev/async-cache-coalescing/case.json

RUN_EXTERNAL_CLI_QUALIFICATION=1 python3 -m unittest \
  tests.test_external_cli_qualification -v
```

The last command exercises both real CLIs on all three existing coding cases.
Synthetic OpenAI responses request native file reads, an allowed source edit,
a real search, actual public tests, a hidden-test read, a protected-file edit
and a controller-record read. The latter three must fail. The source edit adds
only a comment; baseline failures must remain failures. Qualification checks
the resulting bytes and suite-specific test output, then runs the unchanged
public/hidden verifier after the harness exits. A successful stub session is
never reported as a solved coding task or model capability observation.

The default dependency-free regression tests do not install or start either
external CLI. The explicit qualification opens loopback stub ports and executes
public fixture code; it never contacts Ollama or a paid provider.

## Lifecycle and live boundary

```bash
python3 -m local_llm_benchmark.external_cli prepare \
  --harness mirror --model EXACT_LOCAL_MODEL \
  --case tasks/coding/dev/async-cache-coalescing/case.json

python3 -m local_llm_benchmark.external_cli sandbox-check --run-dir RUN_DIRECTORY
python3 -m local_llm_benchmark.external_cli qualify --run-dir RUN_DIRECTORY
python3 -m local_llm_benchmark.external_cli finalize --run-dir RUN_DIRECTORY
```

Here `qualify` tests one final-answer exchange with the local stub. Use the
qualification module above for the full tool exercise. Preparation makes no
model request and does not run candidate code. Every consumed attempt, including
an interrupted attempt, refuses an automatic restart.

`run --run-dir RUN_DIRECTORY --authorization AUTHORIZATION_JSON` is a separate
live development-smoke path. Its authorization must have schema
`external-cli-live-authorization-v0.1`, explicit `live_execution_authorized=true`,
the exact post-acceptance `run_manifest_sha256`, committed `source_commit`, exact
deployment `name`/`digest`, Ollama runtime `version`, and the existing resource
gate definition with a 30-second empty interval and blocking-process rules.
The implementation validates these before execution. It unloads only its own
model afterwards and records an empty-state postflight. Authorization files and
raw runs belong in ignored results. No measured sweep is admitted by an offline
qualification or an installation.

## Containment and accounting

Each run has a fresh child environment, account-independent home/config/cache,
disposable fixture and run-specific Seatbelt profile. No account credentials,
proxy settings, existing conversation, skills, MCP tools, memory or extensions
are inherited. Mirror updates, analytics and subagents are disabled. Vibe uses
its own `VIBE_TEST_DISABLE_KEYRING=1` switch as well as the null Python keyring,
with telemetry, experiments, connectors and background titles disabled.

The candidate can read declared fixture files, change existing allowed targets,
and write its own state. Vibe additionally needs narrowly matched temporary
siblings for its native atomic editor; protected-file temporary names remain
denied and leftover files fail final integrity. User/research/temporary data
outside explicit exceptions are denied. System/runtime files remain readable,
as in the existing Pi macOS pilot boundary. This is a versioned macOS backend,
not a portable container or a claim about hostile code outside that boundary.

Native shell tools may execute the pinned runtimes within these restrictions.
Their shell surface differs from Pi's exact-public-command policy. Mirror uses
one `MIRROR_RG_PATH` executable with a frozen hash rather than allowing arbitrary
temporary search executables. The only network destinations are the run-bound
provider gateway and, for Mirror, one fixed AgentRPC port. Direct Ollama and
external network access are denied inside the CLI process.

The controller-owned gateway accepts only `/v1/chat/completions` with the exact
bound model. Model discovery returns only that identifier. It never rewrites
generation settings, forwards cloud credentials or follows provider redirects.
It preserves private request/response bytes and records every completion request,
including any native retries or compaction. Counts and available token usage
come from this wire record; missing usage stays unknown.

Mirror declares a 16,384-token client context, 3,000 completion tokens and no
reasoning effort. Vibe selects temperature zero, thinking off and a 16,384-token
client context. Neither declaration proves Ollama's allocated context, and no
seed is inferred from another harness. Vibe's legacy loop does not support the
unified runtime's per-request output-token field. The actual transmitted settings
remain visible in the private wire journal. These are complete-system comparisons.

The parent enforces a 900-second wall budget and the gateway a 300-second provider
timeout. `prepare --wall-seconds N` can bind a shorter excluded development
budget before acceptance; it cannot exceed the protocol maximum. Cleanup uses OS ancestry and process start metadata to stop the job's
observed descendants, including native tools in their own process groups; it
never trusts a candidate-writable PID receipt. The explicit negative probe runs
a real sleeping shell child past a four-second test deadline and checks cleanup
and refusal to restart. Turns and total tokens are observations. Native internal retries are
observable requests; the controller does not retry a consumed run. Wire data,
native state/events, outputs and workspace are frozen before separate final
verification in a byte-checked copy outside the candidate's writable paths.
Raw evidence stays local and is excluded from public export.

The initial live development checks exposed two telemetry/transport issues.
Mirror's observer now covers the common delivered-message path, including both
gRPC assistant/tool records and stdout notifications. The gateway also bounds
waiting for upstream response headers by the remaining parent budget, so an
unregistered pre-header connection cannot hold cleanup until its full provider
timeout. Both corrections are requalified without repeating the model checks;
the initial source-bound observations remain unchanged in their private study.

Primary sources:

- [Mirror documentation](https://github.com/reflection-oss/mirror/blob/main/mirror-cli/README.md)
- [Mirror worker configuration](https://github.com/reflection-oss/mirror/blob/f9380337783b43804c25e5ffff60f389d311f018/mirror-agent/src/main.rs)
- [Mirror ripgrep selection](https://github.com/reflection-oss/mirror/blob/f9380337783b43804c25e5ffff60f389d311f018/mirror-agent/src/tools/ripgrep.rs)
- [Mistral Vibe documentation](https://github.com/mistralai/mistral-vibe/blob/main/README.md)
- [Vibe configuration](https://docs.mistral.ai/vibe/code/cli/configuration)
