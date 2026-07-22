"""Tests for the external sync runner."""

from __future__ import annotations

import subprocess

import pytest

from mailintel.config import Config
from mailintel.sync import SyncError, run_sync


def test_run_sync_not_found(cfg: Config):
    cfg.sync.command = "definitely-not-a-real-command-xyz"
    with pytest.raises(SyncError, match="not found"):
        run_sync(cfg)


def test_run_sync_failure(cfg: Config, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/false")
    cfg.sync.command = "false"
    with pytest.raises(SyncError, match="exit 1"):
        run_sync(cfg)


def test_run_sync_timeout(cfg: Config, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["sleep"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/sleep")
    cfg.sync.command = "sleep 10"
    with pytest.raises(SyncError, match="timed out"):
        run_sync(cfg, timeout=1)


def test_run_sync_success(cfg: Config, monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: FakeProc())
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/echo")
    cfg.sync.command = "echo ok"
    assert run_sync(cfg) == "ok"
