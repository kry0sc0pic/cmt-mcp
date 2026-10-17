"""SQLite cache: TTL'd API responses + a persistent submission-status history."""
import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("CMT_CACHE", Path(__file__).resolve().parents[2] / ".cache" / "cmt.db"))
STATUS_TTL = 15 * 60       # status/list data
DETAIL_TTL = 6 * 3600      # summaries, reviews


class Cache:
    def __init__(self, path: Path | None = None):
        path = path or DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, fetched_at REAL);
        CREATE TABLE IF NOT EXISTS status (
            conference TEXT, submission_id INTEGER, title TEXT, track TEXT,
            status_id INTEGER, status_name TEXT, num_reviews INTEGER, num_meta_reviews INTEGER,
            prev_status_id INTEGER, prev_status_name TEXT,
            first_seen REAL, last_checked REAL, last_changed REAL,
            acked_status_id INTEGER, acked_status_name TEXT, acked_num_reviews INTEGER, acked_at REAL,
            PRIMARY KEY (conference, submission_id));
        """)
        for col, typ in (("acked_status_id", "INTEGER"), ("acked_status_name", "TEXT"),
                         ("acked_num_reviews", "INTEGER"), ("acked_at", "REAL")):  # migrate older DBs
            try:
                self.db.execute(f"ALTER TABLE status ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass

    def get(self, key: str, ttl: float):
        row = self.db.execute("SELECT value, fetched_at FROM kv WHERE key=?", (key,)).fetchone()
        if row and time.time() - row["fetched_at"] < ttl:
            return json.loads(row["value"])
        return None

    def put(self, key: str, value):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (key, json.dumps(value), time.time()))
        self.db.commit()

    def record_status(self, conf: str, sub: dict) -> dict:
        """Upsert status; returns the stored row (with `changed` flag)."""
        now = time.time()
        sid, st_id, st_name = sub["Id"], sub.get("StatusId"), sub.get("StatusName")
        old = self.db.execute("SELECT * FROM status WHERE conference=? AND submission_id=?", (conf, sid)).fetchone()
        changed = bool(old and (old["status_id"], old["status_name"]) != (st_id, st_name))
        if old is None:
            self.db.execute("""INSERT INTO status (conference, submission_id, title, track, status_id, status_name,
                num_reviews, num_meta_reviews, first_seen, last_checked, last_changed) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (conf, sid, sub.get("Title"), sub.get("TrackName"), st_id, st_name,
                 sub.get("NumberOfReviews"), sub.get("NumberOfMetaReviews"), now, now, now))
        else:
            self.db.execute("""UPDATE status SET title=?, track=?, status_id=?, status_name=?, num_reviews=?,
                num_meta_reviews=?, last_checked=?,
                prev_status_id=CASE WHEN ? THEN status_id ELSE prev_status_id END,
                prev_status_name=CASE WHEN ? THEN status_name ELSE prev_status_name END,
                last_changed=CASE WHEN ? THEN ? ELSE last_changed END
                WHERE conference=? AND submission_id=?""",
                (sub.get("Title"), sub.get("TrackName"), st_id, st_name, sub.get("NumberOfReviews"),
                 sub.get("NumberOfMetaReviews"), now, changed, changed, changed, now, conf, sid))
        self.db.commit()
        row = dict(self.db.execute("SELECT * FROM status WHERE conference=? AND submission_id=?", (conf, sid)).fetchone())
        row["changed"] = changed
        return row

    def cached_statuses(self, conf: str | None = None):
        q, a = "SELECT * FROM status", ()
        if conf:
            q, a = q + " WHERE conference=?", (conf,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY conference, submission_id", a)]

    def delta(self, conf: str | None = None, acknowledge: bool = True) -> dict:
        """Changes since the last acknowledged delta. The first ever call only sets a baseline."""
        rows = self.cached_statuses(conf)
        baseline_exists = self.db.execute("SELECT 1 FROM status WHERE acked_at IS NOT NULL LIMIT 1").fetchone() is not None
        changes = []
        for r in rows:
            cur = (r["status_id"], r["status_name"])
            if r["acked_at"] is None:
                kind, frm = "new", None
            elif (r["acked_status_id"], r["acked_status_name"]) != cur:
                kind, frm = "status_changed", (r["acked_status_id"], r["acked_status_name"])
            elif (r["num_reviews"] or 0) > (r["acked_num_reviews"] or 0):
                kind, frm = "new_reviews", None
            else:
                continue
            changes.append({"row": r, "kind": kind, "from": frm})
        if acknowledge:
            now = time.time()
            for r in rows:
                self.db.execute("""UPDATE status SET acked_status_id=?, acked_status_name=?, acked_num_reviews=?, acked_at=?
                    WHERE conference=? AND submission_id=?""",
                    (r["status_id"], r["status_name"], r["num_reviews"], now, r["conference"], r["submission_id"]))
            self.db.commit()
        return {"baseline_established": not baseline_exists, "changes": [] if not baseline_exists else changes}
