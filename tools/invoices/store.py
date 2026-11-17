"""Saved invoices and the vendor list (SQLite).

Lives on the Render disk next to the other tools' databases (INVOICES_DB, default: same folder as
RENEWALS_DB). Without a disk it falls back to the temp dir, which is wiped on every deploy.

Invoice numbers:
  - With a work order:     INV-<WO#>          (INV-100363; a 2nd invoice on that WO is INV-100363-2)
  - Without a work order:  <street#>-<YYMM>-<NN>  (1560-2611-01, counting up per address per month)
"""
import os, re, json, sqlite3, tempfile, uuid, datetime, threading


def _default_path():
    if os.getenv("INVOICES_DB"):
        return os.getenv("INVOICES_DB")
    if os.getenv("RENEWALS_DB"):
        return os.path.join(os.path.dirname(os.getenv("RENEWALS_DB")), "invoices.db")
    return os.path.join(tempfile.gettempdir(), "invoices.db")


DB_PATH = _default_path()
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY, number TEXT UNIQUE, vendor TEXT, service_address TEXT,
            total REAL, paid INTEGER, created_at TEXT, updated_at TEXT, doc TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS vendors (
            id TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, address TEXT, city_line TEXT,
            phone TEXT, email TEXT, rentvine_id TEXT, updated_at TEXT)""")


def persistent():
    return bool(os.getenv("INVOICES_DB") or os.getenv("RENEWALS_DB"))


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


# ---------- invoice numbers ----------
def _taken(c, number, own_id=None):
    row = c.execute("SELECT id FROM invoices WHERE number=?", (number,)).fetchone()
    return bool(row) and row["id"] != own_id


def next_number(wo_number="", service_address="", own_id=None, on_date=None):
    wo = re.sub(r"\D", "", str(wo_number or ""))
    with _conn() as c:
        if wo:
            base = "INV-%s" % wo
            if not _taken(c, base, own_id):
                return base
            n = 2
            while _taken(c, "%s-%d" % (base, n), own_id):
                n += 1
            return "%s-%d" % (base, n)
        m = re.match(r"\s*(\d+)", service_address or "")
        street = m.group(1) if m else "DS"
        d = on_date or datetime.date.today()
        base = "%s-%s" % (street, d.strftime("%y%m"))
        n = 1
        while _taken(c, "%s-%02d" % (base, n), own_id):
            n += 1
        return "%s-%02d" % (base, n)


def number_free(number, own_id=None):
    with _conn() as c:
        return not _taken(c, number, own_id)


# ---------- invoices ----------
def save(doc):
    iid = doc.get("id") or uuid.uuid4().hex[:10]
    doc["id"] = iid
    now = _now()
    with _lock, _conn() as c:
        row = c.execute("SELECT created_at FROM invoices WHERE id=?", (iid,)).fetchone()
        created = row["created_at"] if row else now
        doc["created_at"], doc["updated_at"] = created, now
        c.execute("""INSERT OR REPLACE INTO invoices
                     (id, number, vendor, service_address, total, paid, created_at, updated_at, doc)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (iid, doc["number"], doc["vendor"]["name"], doc["service"]["address"],
                   doc["total"], 1 if doc["paid"] else 0, created, now, json.dumps(doc)))
    return doc


def get(iid):
    with _conn() as c:
        row = c.execute("SELECT doc FROM invoices WHERE id=?", (iid,)).fetchone()
    return json.loads(row["doc"]) if row else None


def listing(q=""):
    sql = "SELECT id, number, vendor, service_address, total, paid, created_at FROM invoices"
    args = ()
    if q:
        sql += " WHERE number LIKE ? OR vendor LIKE ? OR service_address LIKE ?"
        args = ("%" + q + "%",) * 3
    sql += " ORDER BY created_at DESC LIMIT 200"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def delete(iid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM invoices WHERE id=?", (iid,))


# ---------- vendors ----------
def vendors():
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, name, address, city_line, phone, email, rentvine_id FROM vendors ORDER BY name").fetchall()]


def upsert_vendor(v):
    name = (v.get("name") or "").strip()
    if not name:
        return None
    now = _now()
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM vendors WHERE name=?", (name,)).fetchone()
        if row:
            # only overwrite a saved field when the new value isn't blank
            merged = {k: (v.get(k) or row[k] or "") for k in ("address", "city_line", "phone", "email", "rentvine_id")}
            c.execute("""UPDATE vendors SET address=?, city_line=?, phone=?, email=?, rentvine_id=?, updated_at=?
                         WHERE id=?""", (merged["address"], merged["city_line"], merged["phone"],
                                         merged["email"], str(merged["rentvine_id"] or ""), now, row["id"]))
            return row["id"]
        vid = uuid.uuid4().hex[:10]
        c.execute("""INSERT INTO vendors (id, name, address, city_line, phone, email, rentvine_id, updated_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (vid, name, v.get("address", ""), v.get("city_line", ""), v.get("phone", ""),
                   v.get("email", ""), str(v.get("rentvine_id") or ""), now))
        return vid


def delete_vendor(vid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM vendors WHERE id=?", (vid,))
