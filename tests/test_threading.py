from mailintel.ingest import ingest
from mailintel.threading_ import normalize_subject
from tests.conftest import make_email, write_message


def test_normalize_subject():
    assert normalize_subject("Re: Re: FWD: Hello  world") == "hello world"
    assert normalize_subject("Aw: Budget") == "budget"
    assert normalize_subject("Plain subject") == "plain subject"


def test_references_threading(conn, cfg):
    ingest(conn, cfg)
    rows = conn.execute(
        "SELECT message_id, thread_id FROM emails "
        "WHERE message_id IN ('<m1@example.com>', '<m2@example.com>')"
    ).fetchall()
    tids = {r["thread_id"] for r in rows}
    assert len(tids) == 1
    t = conn.execute("SELECT * FROM threads WHERE id = ?", (tids.pop(),)).fetchone()
    assert t["message_count"] == 2
    assert t["first_date"] == "2025-06-05 10:00:00"
    assert t["last_date"] == "2025-06-05 12:30:00"


def test_out_of_order_arrival_merges(conn, cfg, maildir):
    # Child sorts before parent within the same scan, so it is ingested first.
    write_message(
        maildir,
        "0001.child.host:2,",
        make_email(
            "<child@example.com>",
            "Re: Design review",
            refs=["<parent@example.com>"],
            date="Tue, 10 Jun 2025 09:00:00 +0000",
        ),
    )
    write_message(
        maildir,
        "0002.parent.host:2,",
        make_email(
            "<parent@example.com>",
            "Design review",
            date="Mon, 09 Jun 2025 09:00:00 +0000",
        ),
    )
    ingest(conn, cfg)
    rows = conn.execute(
        "SELECT thread_id FROM emails "
        "WHERE message_id IN ('<child@example.com>', '<parent@example.com>')"
    ).fetchall()
    assert len({r["thread_id"] for r in rows}) == 1


def test_subject_fallback_threading(conn, cfg, maildir):
    ingest(conn, cfg)
    # Reply with no References header joins the thread by normalized subject.
    write_message(
        maildir,
        "3000.noref.host:2,",
        make_email(
            "<noref@example.com>",
            "RE: Kubernetes cluster upgrade",
            from_="Eve <eve@example.com>",
            date="Fri, 06 Jun 2025 10:00:00 +0000",
        ),
    )
    ingest(conn, cfg)
    tid_orig = conn.execute(
        "SELECT thread_id FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()["thread_id"]
    tid_new = conn.execute(
        "SELECT thread_id FROM emails WHERE message_id = '<noref@example.com>'"
    ).fetchone()["thread_id"]
    assert tid_orig == tid_new


def test_fresh_subject_starts_new_thread(conn, cfg):
    ingest(conn, cfg)
    n_threads = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    # 5 emails: m1+m2 share a thread -> 4 threads
    assert n_threads == 4
