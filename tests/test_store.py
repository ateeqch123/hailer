import sqlite3
import threading

from hailer.store import DedupStore


def test_mark_is_remembered_and_scoped_to_account(tmp_path):
    path = tmp_path / "state" / "notified.db"
    with DedupStore(path) as store:
        assert store.already_notified("a@example.com", "m1") is False
        store.mark_notified("a@example.com", "m1", "recruiter")
        assert store.already_notified("a@example.com", "m1") is True
        assert store.already_notified("b@example.com", "m1") is False
        assert store.already_notified("a@example.com", "m2") is False
        store.mark_notified("a@example.com", "m1", "recruiter")

    with DedupStore(path) as again:
        assert again.already_notified("a@example.com", "m1") is True


def test_parallel_marks_leave_one_row(tmp_path):
    path = tmp_path / "notified.db"
    store = DedupStore(path)
    threads = [
        threading.Thread(target=store.mark_notified, args=("a@example.com", "m1", "autoreply"))
        for _ in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    store.close()

    conn = sqlite3.connect(path)
    count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    conn.close()
    assert count == 1
