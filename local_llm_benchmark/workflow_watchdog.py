"""Independent parent deadline for one complete writing-workflow process group.

The watchdog owns only its child group. Killing that group closes upstream HTTP
connections; a separate verified backend postflight is required before declaring
live cancellation complete. Cleanup time is recorded outside the trial budget.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path

from .calibration_run import ROOT, save, stop_group
from .runner import utc_now

MAXIMUM_TRIAL_SECONDS = 3600


def run_bounded(argv: list[str], directory: Path, *, seconds: float = MAXIMUM_TRIAL_SECONDS,
                monitor=None, cwd: Path = ROOT, environment: dict | None = None) -> dict:
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= MAXIMUM_TRIAL_SECONDS:
        raise ValueError('Explicit deadline must be positive and at most the agreed3600seconds')
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started+seconds
    record = {'started_at': utc_now(), 'budget_seconds': seconds, 'timed_out': False,
              'deadline_monotonic': deadline,
              'monitor_error': None, 'cleanup_finished': False,
              'backend_cancellation_verified': False}
    cleanup_lock = threading.Lock()
    process = None

    def cleanup(reason):
        with cleanup_lock:
            record.setdefault('cleanup', []).append({'reason': reason, 'result': stop_group(process)})

    with (directory/'worker.stdout').open('xb') as stdout, (directory/'worker.stderr').open('xb') as stderr:
        child_environment = dict(os.environ if environment is None else environment)
        child_environment['LOCAL_LLM_WORKFLOW_DEADLINE_MONOTONIC'] = str(deadline)
        process = subprocess.Popen(argv, cwd=cwd, env=child_environment, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        record['owned_process_group'] = process.pid

        def expire():
            if process.poll() is None:
                record['timed_out'] = True
                record['deadline_signal_elapsed_seconds'] = time.monotonic()-started
                try:
                    cleanup('deadline')
                except Exception as exc:
                    record['deadline_cleanup_error'] = {'type': type(exc).__name__, 'message': str(exc)}

        timer = threading.Timer(max(0.001, seconds-(time.monotonic()-started)), expire)
        timer.start()
        next_monitor = started
        try:
            while process.poll() is None:
                if monitor and time.monotonic() >= next_monitor:
                    try:
                        monitor()
                    except Exception as exc:
                        record['monitor_error'] = {'type': type(exc).__name__, 'message': str(exc)}
                        cleanup('monitor_failure')
                        break
                    next_monitor = time.monotonic()+5
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            timer.cancel()
            timer.join()
            cleanup_started = time.monotonic()
            try:
                cleanup('final')
                process.wait(timeout=5)
                record['cleanup_finished'] = True
            except Exception as exc:
                record['final_cleanup_error'] = {'type': type(exc).__name__, 'message': str(exc)}
            record.update(returncode=process.returncode, elapsed_seconds=time.monotonic()-started,
                          final_cleanup_seconds=time.monotonic()-cleanup_started, finished_at=utc_now())
            save(directory/'watchdog.json', record)
    return record
