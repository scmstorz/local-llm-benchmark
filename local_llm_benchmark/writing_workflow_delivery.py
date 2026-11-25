"""Prospective Pi delivery v2: exact terminal text, never an earlier draft.

The SDK selects its normal final response. The controller independently verifies
the last completed native response and accepts it without another model/tool call.
"""
import hashlib
import json
import time

from .calibration_run import once
from .external_cli_native import NativeResponse

LEGACY='submit_tool_only_v1'
PROTOCOL='tool_or_regular_final_v2'


def accept_regular_final(directory,tools,budget,payload):
    # Caller holds the transport admission lock, so a later model request cannot
    # race the selection. Budget lock excludes in-flight/reserved generations.
    with budget.lock:
        if set(payload)!={'article','response_id'} or budget.poisoned or budget.pending is not None:
            raise ValueError('Final delivery controller closed')
        files=sorted(p for p in directory.glob('request-*.json') if not p.name.endswith('.partial-message.json'))
        if not files:raise ValueError('No native final response')
        path=files[-1];row=json.loads(path.read_text())
        if (row.get('status')!='complete' or row.get('finish_reason')!='stop'
                or row.get('finished_monotonic',float('inf'))>=budget.deadline
                or payload['response_id']!='ollama-native-'+str(row['sequence'])):
            raise ValueError('Not the last normally completed native response')
        raw=path.with_suffix('.native.ndjson')
        if not raw.exists():raw=path.with_suffix('.native-response')
        converter=NativeResponse(row['request'],row['sequence'])
        for line in raw.read_bytes().splitlines(keepends=True):
            if not line.endswith(b'\n'):raise ValueError('Incomplete native response')
            converter.feed(json.loads(line))
        converter.finish()
        if (converter.finish_reason!='stop' or converter.message.get('tool_calls')
                or converter.message.get('content')!=payload['article']):
            raise ValueError('SDK/native final response mismatch')
        receipt=tools.accept_final(payload['article'],kind='assistant_final_text')
        receipt.update(delivery_protocol=PROTOCOL,response_id=payload['response_id'],
                       request_sequence=row['sequence'],accepted_monotonic=time.monotonic(),
                       native_response_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                       request_journal_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if receipt['accepted_monotonic']>=budget.deadline:raise ValueError('Final delivery completed too late')
        once(directory.parent/'final-delivery.json',receipt)
        return receipt
