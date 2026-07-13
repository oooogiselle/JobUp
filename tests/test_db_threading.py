"""Regression test for the SQLite cross-thread bug. FastAPI runs sync endpoints
across threadpool threads, so a Store opened in one thread gets used in another.
Before check_same_thread=False this raised sqlite3.ProgrammingError at runtime
(and the single-threaded TestClient never caught it)."""

from __future__ import annotations

import concurrent.futures

from jobup.db import Store


def test_store_usable_from_another_thread(tmp_path):
    store = Store(tmp_path / "t.sqlite3")   # created on the main thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        # used on a worker thread — the exact scenario that used to crash
        rows = ex.submit(store.list_applications).result()
        companies = ex.submit(store.companies).result()
        stats_ok = ex.submit(lambda: store.count() == 0).result()
    assert rows == [] and companies == [] and stats_ok
    store.close()
