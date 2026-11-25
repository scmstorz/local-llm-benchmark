# Pinned Mirror runtime

`reflection-mirror==0.1.0` and its transitive dependencies are fixed in `uv.lock`.
The package named `mirror` on PyPI is unrelated. Use the
[shared integration procedure](../external-cli-v0.1.md) for installation,
qualification and run lifecycle.

`capture.py` observes the pinned upstream AgentRPC transport. `worker.py` selects
a fixed loopback RPC port, the seven native filesystem/shell tools, no subagents,
MCP, memory or checkpoints. The worker inherits the controller's process group.
The native tool implementations and model loop remain upstream code.

The benchmark uses a fresh run-local home and configuration, disables analytics
and updates, and selects one exact local model and ripgrep executable. Account
configuration is never used. The native worker and Python dependencies are
installed only in the ignored `.venv` directory.
