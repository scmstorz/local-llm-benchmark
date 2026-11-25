"""Run pinned Mirror exec, retaining its unmodified AgentRPC events.

Only transport plumbing changes: a fixed loopback RPC port for Seatbelt,
an event observer, and keeping the worker in the controller's process group.
The upstream model loop and native tool implementations are unchanged; worker
configuration selects the versioned benchmark tool allowlist.
"""

import json
import os
from pathlib import Path
import sys

from google.protobuf.json_format import MessageToDict
from mirror.cli import local_rpc_client, rpc_client
from mirror.cli.main import run


_deliver_message = rpc_client.deliver_message


async def observed_delivery(handler, event):
    # Both the gRPC Client and stdout transport deliver through this upstream
    # function. Observing Transport alone misses committed assistant/tool chat.
    with Path(os.environ["BENCHMARK_EVENTS"]).open("a") as sink:
        sink.write(json.dumps(MessageToDict(event, preserving_proto_field_name=True)) + "\n")
    await _deliver_message(handler, event)


class ObservedTransport(local_rpc_client.Transport):
    async def connect(self, host_tools=()):
        self._worker_command = [
            sys.executable, str(Path(__file__).with_name("worker.py")),
            *self._worker_command,
        ]
        return await super().connect(host_tools)


local_rpc_client.Transport = ObservedTransport
rpc_client.deliver_message = observed_delivery
# Upstream detaches the worker with setsid. Retain the controller's group so
# the parent's deadline also kills the worker and its ordinary descendants.
assert local_rpc_client._WORKER_LAUNCHER.count("os.setsid(); ") == 1
local_rpc_client._WORKER_LAUNCHER = local_rpc_client._WORKER_LAUNCHER.replace("os.setsid(); ", "")
run()
