"""Run the external mail synchronizer (mbsync by default), then ingest."""

from __future__ import annotations

import shlex
import shutil
import subprocess

from .config import Config


class SyncError(RuntimeError):
    pass


def run_sync(cfg: Config, timeout: int = 900) -> str:
    argv = shlex.split(cfg.sync.command)
    if not argv:
        raise SyncError("sync.command is empty in config")
    if shutil.which(argv[0]) is None:
        raise SyncError(
            f"Sync command '{argv[0]}' not found. Install it (e.g. `brew install isync`) "
            f"and configure ~/.mbsyncrc — see docs/mbsync-setup.md."
        )
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SyncError(f"Sync timed out after {timeout}s") from exc
    if proc.returncode != 0:
        raise SyncError(
            f"Sync command failed (exit {proc.returncode}):\n{proc.stderr.strip()[:2000]}"
        )
    return proc.stdout.strip()[-2000:]
