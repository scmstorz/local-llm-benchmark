"""Exact rendered-prompt admission for the text-only writing workflow.

The renderer is the pinned running backend. The tokenizer loads only the bound
artifact's tokenizer.json; no estimated character/token conversion is accepted.
Runtime parity must be separately qualified before a scored run.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path


class ContextExhausted(ValueError):
    pass


class ArtifactTokenizer:
    def __init__(self, path: Path, sha256: str):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha256:
            raise ValueError('Tokenizer artifact identity drift')
        # Optional, pinned helper dependency; deliberately no from_pretrained.
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_str(raw.decode('utf-8'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.sha256 = sha256

    def __call__(self, prompt: str) -> int:
        return len(self.tokenizer.encode(prompt, add_special_tokens=False).ids)


class ContextAdmission:
    def __init__(self, render, count, *, context_tokens: int):
        if type(context_tokens) is not int or context_tokens < 2:
            raise ValueError('Explicit context capacity required')
        self.render = render
        self.count = count
        self.context_tokens = context_tokens

    def admit(self, native: dict) -> tuple[dict, dict]:
        request = copy.deepcopy(native)
        if request['options'].get('num_ctx') != self.context_tokens:
            raise ValueError('Context configuration drift')
        if any(m.get('images') for m in request['messages']):
            raise ValueError('Only the text-only condition is qualified')
        # Never permit source/history truncation or a sliding context shift.
        request.update(truncate=False, shift=False)
        debug = self.render({**request, 'stream': False, '_debug_render_only': True})
        if debug.get('model') != request['model']:
            raise ValueError('Debug renderer model identity drift')
        info = debug.get('_debug_info', {})
        prompt = info.get('rendered_template')
        if not isinstance(prompt, str) or not prompt or info.get('image_count', 0) != 0:
            raise ValueError('Missing text-only rendered prompt')
        tokens = self.count(prompt)
        if type(tokens) is not int or tokens < 1:
            raise ValueError('No exact input token count')
        free = self.context_tokens - tokens
        if free < 1:
            raise ContextExhausted('Full original context leaves no output capacity')
        ceiling = request['options'].get('num_predict')
        if type(ceiling) is not int or ceiling < 1:
            raise ValueError('Explicit per-request ceiling required')
        request['options']['num_predict'] = min(ceiling, free)
        return request, {'input_tokens': tokens, 'context_tokens': self.context_tokens,
                         'available_output_tokens': free,
                         'effective_output_ceiling': request['options']['num_predict'],
                         'rendered_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                         'rendered_prompt': prompt, 'truncate': False, 'shift': False}
