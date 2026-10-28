"""Saved renewal proposals (SQLite).

On Render the database lives on the persistent disk (RENEWALS_DB=/var/data/renewals.db, see
render.yaml). Without a disk it falls back to the temp dir, which is wiped on every deploy.
Each proposal is one JSON document plus a few columns for the history list.
"""
import os, json, sqlite3, tempfile, uuid, datetime, threading

DB_PATH = os.getenv("RENEWALS_DB") or os.path.join(tempfile.gettempdir(), "renewals.db")
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            owner TEXT, properties TEXT, status TEXT,
            created_at TEXT, updated_at TEXT, created_by TEXT,
            doc TEXT NOT NULL)""")


def persistent():
    return bool(os.getenv("RENEWALS_DB"))


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def save(doc, user=""):
    pid = doc.get("id") or uuid.uuid4().hex[:10]
    doc["id"] = pid
    props = ", ".join(p.get("address", "") for p in doc.get("properties", []) if p.get("address"))
    now = _now()
    with _lock, _conn() as c:
        row = c.execute("SELECT created_at, created_by FROM proposals WHERE id=?", (pid,)).fetchone()
        created = row["created_at"] if row else now
        by = row["created_by"] if row else user
        doc["created_at"], doc["updated_at"] = created, now
        c.execute("""INSERT OR REPLACE INTO proposals
                     (id, owner, properties, status, created_at, updated_at, created_by, doc)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (pid, doc.get("owner_name", ""), props, doc.get("status", "draft"),
                   created, now, by, json.dumps(doc)))
    return doc


def get(pid):
    with _conn() as c:
        row = c.execute("SELECT doc FROM proposals WHERE id=?", (pid,)).fetchone()
    return json.loads(row["doc"]) if row else None


def listing(q=""):
    sql = "SELECT id, owner, properties, status, created_at, updated_at, created_by FROM proposals"
    args = ()
    if q:
        sql += " WHERE owner LIKE ? OR properties LIKE ?"
        args = ("%" + q + "%", "%" + q + "%")
    sql += " ORDER BY updated_at DESC LIMIT 200"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def delete(pid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM proposals WHERE id=?", (pid,))
