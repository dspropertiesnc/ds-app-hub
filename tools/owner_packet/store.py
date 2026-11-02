"""Saved owner packets and the shared pricing settings (SQLite).

On Render the database sits on the persistent disk next to the renewal proposals
(OWNER_PACKETS_DB, default: same folder as RENEWALS_DB). Without a disk it falls back to the
temp dir, which is wiped on every deploy. Each packet is the editor's full state as one JSON
document, plus a few columns for the history list.
"""
import os, json, sqlite3, tempfile, uuid, datetime, threading


def _default_path():
    if os.getenv("OWNER_PACKETS_DB"):
        return os.getenv("OWNER_PACKETS_DB")
    if os.getenv("RENEWALS_DB"):
        return os.path.join(os.path.dirname(os.getenv("RENEWALS_DB")), "owner_packets.db")
    return os.path.join(tempfile.gettempdir(), "owner_packets.db")


DB_PATH = _default_path()
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS packets (
            id TEXT PRIMARY KEY,
            owner TEXT, properties TEXT, mode TEXT,
            created_at TEXT, updated_at TEXT,
            state TEXT NOT NULL)""")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def persistent():
    return bool(os.getenv("OWNER_PACKETS_DB") or os.getenv("RENEWALS_DB"))


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _summary(state):
    props = []
    for p in state.get("props") or []:
        d = p.get("data") or {}
        a = (d.get("street") or p.get("hint") or "").strip()
        if a:
            props.append(a)
    mode = "Services & pricing" if state.get("skipAnalysis") else "Rental analysis"
    return (state.get("owner") or "").strip(), ", ".join(props), mode


def save(pid, state):
    pid = pid or uuid.uuid4().hex[:10]
    owner, props, mode = _summary(state)
    now = _now()
    with _lock, _conn() as c:
        row = c.execute("SELECT created_at FROM packets WHERE id=?", (pid,)).fetchone()
        created = row["created_at"] if row else now
        c.execute("""INSERT OR REPLACE INTO packets (id, owner, properties, mode, created_at, updated_at, state)
                     VALUES (?,?,?,?,?,?,?)""", (pid, owner, props, mode, created, now, json.dumps(state)))
    return {"id": pid, "updated_at": now}


def get(pid):
    with _conn() as c:
        row = c.execute("SELECT state, updated_at FROM packets WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    return {"state": json.loads(row["state"]), "updated_at": row["updated_at"]}


def listing(q=""):
    sql = "SELECT id, owner, properties, mode, created_at, updated_at FROM packets"
    args = ()
    if q:
        sql += " WHERE owner LIKE ? OR properties LIKE ?"
        args = ("%" + q + "%", "%" + q + "%")
    sql += " ORDER BY updated_at DESC LIMIT 300"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def delete(pid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM packets WHERE id=?", (pid,))


def get_settings():
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key='pricing'").fetchone()
    return json.loads(row["value"]) if row else {}


def set_settings(values):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pricing', ?)", (json.dumps(values),))
