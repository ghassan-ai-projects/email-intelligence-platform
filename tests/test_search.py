from mailintel.ingest import ingest
from mailintel.search import (
    fts_query,
    get_email,
    get_stats,
    get_thread,
    search_emails,
    search_threads,
)


def test_fts_query_sanitization():
    assert fts_query("kubernetes upgrade") == '"kubernetes" "upgrade"'
    assert fts_query('"exact phrase" other') == '"exact phrase" "other"'
    assert fts_query('inj" OR 1') == '"inj" "OR" "1"'


def test_fulltext_search(conn, cfg):
    ingest(conn, cfg)
    results = search_emails(conn, query="kubernetes")
    assert len(results) == 2
    assert all("Kubernetes" in r["subject"] for r in results)


def test_search_filters(conn, cfg):
    ingest(conn, cfg)
    assert len(search_emails(conn, from_addr="billing@vendor.com")) == 1
    assert len(search_emails(conn, folder="Projects")) == 1
    assert len(search_emails(conn, has_attachments=True)) == 1
    assert len(search_emails(conn, unread_only=True)) == 2
    assert len(search_emails(conn, date_from="2025-06-06", date_to="2025-06-07")) == 2
    assert len(search_emails(conn, to_addr="dave@client.example")) == 1


def test_get_email_detail(conn, cfg):
    ingest(conn, cfg)
    eid = conn.execute("SELECT id FROM emails WHERE message_id = '<m4@example.com>'").fetchone()[
        "id"
    ]
    d = get_email(conn, eid)
    assert d["subject"] == "Quarterly report attached"
    assert "quarterly report" in d["body"].lower()
    assert d["attachments"][0]["filename"] == "doc.pdf"
    assert d["recipients"][0]["addr"] == "me@example.com"
    assert get_email(conn, 999_999) is None


def test_get_thread_and_search_threads(conn, cfg):
    ingest(conn, cfg)
    tid = conn.execute(
        "SELECT thread_id FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()["thread_id"]
    t = get_thread(conn, tid)
    assert t["message_count"] == 2
    assert "alice@example.com" in t["participants"]
    assert "bob@example.com" in t["participants"]
    assert next(e["subject"] for e in t["emails"]) == "Kubernetes cluster upgrade"

    hits = search_threads(conn, "kubernetes")
    assert hits[0]["thread_id"] == tid
    assert hits[0]["matching_messages"] == 2
    assert search_threads(conn, '""') == []
    assert search_threads(conn, "!!!") == []


def test_get_stats(conn, cfg):
    ingest(conn, cfg)
    s = get_stats(conn)
    assert s["emails"] == 5
    assert s["threads"] == 4
    assert s["enriched"] == 0
    assert {f["folder"] for f in s["folders"]} == {"INBOX", "Projects", "Sent"}
    assert s["pipeline_jobs"]["enrich:pending"] == 5
