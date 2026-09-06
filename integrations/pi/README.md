# Pinned Pi integration

This directory isolates the external dependency used by the Coding Track B Pi
adapter. The package and every transitive dependency are resolved by
`package-lock.json`; the top-level package is fixed to
`@earendil-works/pi-coding-agent@0.84.4` rather than a version range.

Install and verify the integration with:

```bash
npm install --ignore-scripts
npm test
./node_modules/.bin/pi --version
```

`benchmark-policy.mjs` is the historical v0.2 extension.
`benchmark-policy-v0.3.mjs` is the qualified time-first extension for future
runs. Both enforce candidate-visible reads, writes to an exact existing-file
allowlist, one exact public-test command and a compact audit log without
recording candidate source text. V0.3 records turns and tokens without using
them as normal abort limits; its 200-read, 100-write and 30-test ceilings are
emergency loop safeguards.

These policy checks provide benchmark consistency but are not a security
sandbox. Live execution is additionally contained by a run-specific,
versioned macOS Seatbelt profile. Its deny-by-default acceptance suite must pass
before every live run. Only the pinned Pi and exact case-specific runtime may
execute; the current run and pinned integration are readable; writes are
limited to the exact candidate targets, audit file, run-local Pi state and
temporary directories; and the only network destination is local Ollama on
port 11434.

The controller never runs hidden verification in the Pi process. Pi exits and
its raw event stream, audit log and workspace are hash-frozen first. A separate
finalization command revalidates those hashes and then invokes the deterministic
verifier without Ollama access.

Apple marks `sandbox-exec` as deprecated. The selected backend is therefore a
versioned macOS pilot boundary with executable adversarial tests, not a claim
that Seatbelt is a permanent portable solution. A container backend remains a
future alternative.

Run all default policy and settings checks with `npm test`. The real transport
deadline probe is explicit because it opens a temporary local stub port:

```bash
npm run test:transport-v0.3
```

The probe never contacts Ollama or an external service. It makes one request to
an intentionally non-responsive loopback stub and verifies that pinned Pi
honors the configured provider timeout.

Primary integration references:

- [Pi coding-agent documentation](https://github.com/earendil-works/pi/tree/main/packages/coding-agent)
- [Ollama Pi integration](https://docs.ollama.com/integrations/pi)
- [Pinned npm release](https://www.npmjs.com/package/@earendil-works/pi-coding-agent/v/0.84.4)
- [OpenAI Codex Seatbelt base policy](https://github.com/openai/codex/blob/main/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl)
- [Docker bind-mount security and read-only mounts](https://docs.docker.com/engine/storage/bind-mounts/)
