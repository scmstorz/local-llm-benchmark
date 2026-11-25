# Pinned Mistral Vibe runtime

`mistral-vibe==2.26.1` and its transitive dependencies are fixed in `uv.lock`.
Use the [shared integration procedure](../external-cli-v0.1.md) for installation,
qualification and run lifecycle.

`vibe-cli-v0.1` explicitly selects the Python CLI and `--legacy-harness`.
Automatic runtime rollouts, the unified Rust harness and interactive account
configuration cannot silently change this system identity. Native tools,
streaming JSON and the native session export remain available.

Every preparation writes a fresh local-only `config.toml`. Telemetry, experiments,
connectors, skills, generated titles and keychain access are disabled. The native
editor's precise temporary-file pattern is admitted by the run-specific sandbox;
the candidate cannot modify protected tests or arbitrary new workspace files.
