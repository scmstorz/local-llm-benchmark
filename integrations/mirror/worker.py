"""Preserve the native worker, choosing its otherwise ephemeral RPC port."""

import json
import os
from pathlib import Path
import sys

config = json.loads(sys.argv[-1])
config["rpc_address"] = "127.0.0.1:" + os.environ["BENCHMARK_MIRROR_RPC_PORT"]
config["tools"] = ["read", "bash", "write", "edit", "grep", "glob", "ls"]
config["mcp_connections"] = []
config["additional_skills"] = []
config["memory_dir"] = None
config["checkpoints_enabled"] = False
Path(os.environ["BENCHMARK_WORKER_PID"]).write_text(str(os.getpid()) + "\n")
os.execv(sys.argv[1], [sys.argv[1], json.dumps(config)])
