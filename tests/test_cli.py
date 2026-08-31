"""Direct command tests for the thin CLI adapters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mailintel import cli
from mailintel.config import Config
from mailintel.enrich import embeddings
from mailintel.ingest import ingest
from mailintel.sync import SyncError


class _Stats:
    def __init__(self, **values):
        self.__dict__.update(values)

    def as_dict(self):
        return self.__dict__


class _Connection:
    def __init__(self, rows=()):
        self.rows = rows
        self.closed = False

    def close(self):
        self.closed = True

    def execute(self, *_args):
        return SimpleNamespace(fetchall=lambda: list(self.rows))


class _NonClosingConnection:
    def __init__(self, connection):
        self.connection = connection

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_echo_json_and_init(monkeypatch, capsys, tmp_path):
    cli._echo_json({"message": "hello"})
    assert '"message": "hello"' in capsys.readouterr().out
    calls = []
    monkeypatch.setattr(cli, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli, "initialize_config", lambda *args: calls.append(args))
    cli.init()
    assert calls == [(tmp_path / "config.toml", tmp_path, cli.CONFIG_TEMPLATE)]


@pytest.mark.parametrize("enrich_after", [True, False])
def test_sync_command_closes_connection_and_maps_optional_enrichment(
    monkeypatch, tmp_path, enrich_after
):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    connections = []
    calls = []
    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr(
        cli.db, "connect", lambda _path: connections.append(_Connection()) or connections[-1]
    )
    monkeypatch.setattr("mailintel.sync.run_sync", lambda value: calls.append(("sync", value)))
    monkeypatch.setattr(
        "mailintel.ingest.ingest",
        lambda conn, value: calls.append(("ingest", conn, value)) or _Stats(new=1),
    )
    monkeypatch.setattr(
        "mailintel.enrich.pipeline.run_pipeline",
        lambda conn, value, limit: calls.append(("enrich", conn, value, limit))
        or _Stats(done={"enrich": 1}),
    )
    cli.sync(enrich_after=enrich_after, limit=7)
    assert calls[0] == ("sync", cfg)
    assert calls[1][0] == "ingest"
    assert any(call[0] == "enrich" for call in calls) is enrich_after
    assert len(connections) == 1
    assert connections[0].closed


def test_ingest_and_enrich_commands(monkeypatch, capsys, tmp_path):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    connections = []
    calls = []
    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr(
        cli.db, "connect", lambda _path: connections.append(_Connection()) or connections[-1]
    )
    monkeypatch.setattr(
        "mailintel.ingest.ingest",
        lambda conn, value: _Stats(new=2, deleted=1),
    )
    cli.ingest()
    assert '"new": 2' in capsys.readouterr().out

    def pipeline(conn, value, limit):
        calls.append((conn, value, limit, value.enrich.stages))
        return _Stats(done={"embed": 1})

    monkeypatch.setattr("mailintel.enrich.pipeline.run_pipeline", pipeline)
    cli.enrich(limit=3, stage="embed")
    assert calls[-1][2] == 3
    assert calls[-1][3] == ["embed"]
    cli.enrich(limit=4, stage=None)
    assert calls[-1][2] == 4
    assert len(connections) == 3
    assert all(connection.closed for connection in connections)


def test_serve_validation_and_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr("mailintel.mcp_server.main", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(cli.typer.BadParameter, match="transport"):
        cli.serve("invalid")
    cli.serve("stdio", host="127.0.0.1", port=9000)
    assert calls == [{"transport": "stdio", "host": "127.0.0.1", "port": 9000}]


def test_search_fts_and_semantic(monkeypatch, capsys, conn, cfg):
    ingest(conn, cfg)
    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr(cli.db, "connect", lambda _path: _NonClosingConnection(conn))
    cli.search("Kubernetes", limit=2, semantic=False)
    assert "Kubernetes" in capsys.readouterr().out

    class Embedder:
        def embed_query(self, query):
            assert query == "meaning"
            return [0.0] * 8

    monkeypatch.setattr(embeddings, "make_embedder", lambda _cfg: Embedder())
    monkeypatch.setattr(embeddings, "knn_email_ids", lambda _conn, _vec, _limit: [(1, 0.1234)])
    cli.search("meaning", semantic=True)
    assert "0.1234" in capsys.readouterr().out


def test_stats_contacts_audit_and_prune(monkeypatch, capsys, tmp_path):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    conn = _Connection()
    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr(cli.db, "connect", lambda _path: conn)
    monkeypatch.setattr("mailintel.search.get_stats", lambda _conn: {"emails": 3})
    imported_paths = []
    monkeypatch.setattr(
        cli.db,
        "import_contacts_json",
        lambda _conn, path: imported_paths.append(path) or 1,
    )
    monkeypatch.setattr("mailintel.events.prune_events", lambda _conn, before: before)
    cli.stats()
    cli.contacts_import(path=str(cfg.guardrail.contacts_path))
    cli.audit(limit=2, tool="get_stats")
    cli.events_prune(9)
    output = capsys.readouterr().out
    assert '"emails": 3' in output
    assert "Imported 1 contacts" in output
    assert imported_paths == [str(cfg.guardrail.contacts_path)]
    assert "Deleted 9 events" in output
    assert conn.closed


def test_watch_handles_sync_error_then_keyboard_interrupt(monkeypatch, tmp_path, capsys):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    calls = iter([SyncError("temporary"), KeyboardInterrupt()])
    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr(
        "mailintel.sync_cycle.run_sync_cycle",
        lambda _cfg, enrich, limit: (_ for _ in ()).throw(next(calls)),
    )
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    with pytest.raises(KeyboardInterrupt):
        cli.watch()
    assert "sync error: temporary" in capsys.readouterr().err


def test_watch_handles_general_error_then_keyboard_interrupt(monkeypatch, tmp_path, capsys):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    sequence = iter(["error", "interrupt"])

    def run_cycle(_cfg, enrich, limit):
        if next(sequence) == "error":
            raise RuntimeError("unexpected")
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr("mailintel.sync_cycle.run_sync_cycle", run_cycle)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    with pytest.raises(KeyboardInterrupt):
        cli.watch()
    assert "error: unexpected" in capsys.readouterr().err


def test_watch_reports_a_successful_cycle(monkeypatch, tmp_path, capsys):
    cfg = Config()
    cfg.storage.db_path = tmp_path / "mail.db"
    calls = iter(
        [
            SimpleNamespace(
                ingest=_Stats(new=1, deleted=0),
                enrich=_Stats(done={"enrich": 1}),
            ),
            KeyboardInterrupt(),
        ]
    )

    def run_cycle(_cfg, enrich, limit):
        result = next(calls)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(cli, "_cfg", lambda: cfg)
    monkeypatch.setattr("mailintel.sync_cycle.run_sync_cycle", run_cycle)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    with pytest.raises(KeyboardInterrupt):
        cli.watch()
    assert "ingest=" in capsys.readouterr().out
