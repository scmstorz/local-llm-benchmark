"""Sequential usage accounting and request/deadline guards for a workflow.

The aggregate token cap is optional; None records usage without rationing it.
Per-request ceilings still apply. Interrupted/unmetered responses close the
controller rather than inventing usage. Deadline checks are not a watchdog.
"""
from __future__ import annotations
from dataclasses import dataclass,field
import threading,time,math

class BudgetExhausted(ValueError):pass

@dataclass
class GenerationBudget:
    generated_tokens:int|None
    maximum_requests:int
    deadline:float
    clock:object=time.monotonic
    used_tokens:int=field(default=0,init=False)
    input_tokens:int=field(default=0,init=False)
    requests:int=field(default=0,init=False)
    poisoned:bool=field(default=False,init=False)
    unmetered:bool=field(default=False,init=False)
    allocations:list=field(default_factory=list,init=False)

    def __post_init__(self):
        if self.generated_tokens is not None and (type(self.generated_tokens)is not int or self.generated_tokens<1):
            raise ValueError('Aggregate token cap must be a positive integer or explicit None')
        if type(self.maximum_requests)is not int or self.maximum_requests<1:
            raise ValueError('Explicit positive request guard required')
        if type(self.deadline) not in (int,float) or not math.isfinite(self.deadline):raise ValueError('Finite monotonic deadline required')
        self.lock=threading.RLock();self.pending=None

    def begin(self,ceiling:int,sequence:int)->int:
        with self.lock:
            if type(ceiling)is not int or ceiling<1:raise ValueError('Invalid per-call ceiling')
            if self.poisoned or self.pending is not None:raise BudgetExhausted('Workflow budget closed or concurrent model request')
            if self.clock()>=self.deadline:raise BudgetExhausted('Whole-trial deadline exhausted')
            if self.requests>=self.maximum_requests:raise BudgetExhausted('Whole-trial request guard exhausted')
            if self.generated_tokens is not None and self.used_tokens>=self.generated_tokens:
                raise BudgetExhausted('Whole-trial token budget exhausted')
            cap=ceiling if self.generated_tokens is None else min(ceiling,self.generated_tokens-self.used_tokens)
            self.requests+=1
            item={'sequence':sequence,'cap':cap,'usage':None,'status':'reserved'}
            self.allocations.append(item);self.pending=item
            return cap

    def finish(self,sequence:int,usage:dict|None,*,complete:bool):
        with self.lock:
            item=self.pending
            if item is None or item['sequence']!=sequence:raise ValueError('Unmatched workflow reservation')
            self.pending=None
            valid=isinstance(usage,dict) and all(type(usage.get(k))is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens'))
            if not complete or not valid:
                item['status']='unmetered_or_incomplete';self.poisoned=True;self.unmetered=True
                return
            item['usage']=dict(usage);self.used_tokens+=usage['completion_tokens'];self.input_tokens+=usage['prompt_tokens']
            item['status']='complete'
            if usage['completion_tokens']>item['cap'] or (self.generated_tokens is not None and self.used_tokens>self.generated_tokens):
                item['status']='backend_exceeded_ceiling';self.poisoned=True
            if self.clock()>=self.deadline:
                item['status']='completed_after_deadline';self.poisoned=True

    def snapshot(self):
        with self.lock:return {'maximum_generated_tokens':self.generated_tokens,'aggregate_token_cap_enabled':self.generated_tokens is not None,'maximum_requests':self.maximum_requests,
          'requests_admitted':self.requests,'actual_generated_tokens':None if self.unmetered else self.used_tokens,'actual_input_tokens':None if self.unmetered else self.input_tokens,'known_generated_tokens':self.used_tokens,'usage_complete':not self.unmetered,
          'remaining_generated_tokens':None if self.generated_tokens is None else (0 if self.poisoned else self.generated_tokens-self.used_tokens),
          'poisoned':self.poisoned,'request_in_flight':self.pending is not None,'allocations':[dict(x) for x in self.allocations]}
