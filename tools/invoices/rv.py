"""Rentvine lookups for the invoice generator.

`find(q)` takes whatever staff have: a bill #, a work order # (e.g. 100389, with or without "#"),
a property address, a vendor name, a few words about the job ("Henderson faucet leak"), or a mix.
It returns a short list of matching bills (and work orders that don't have a bill yet) to pick from.
`bill(id)` / `work_order(id)` then fill the invoice.

Uses the same API key as the renewal tool (tools/renewals/rentvine.py). Bill shape confirmed on the
live account (Nov 2026): GET /accounting/bills/{id}?includes=contact,charges returns
{bill:{billDate,dateDue,description,payeeContactID,workOrderID,...}, contact:{name,address,city,
stateID,postalCode,phone,email}, charges:[{transaction:{...}, property:{...}, portfolio:{...}}]}.
List/search endpoint names aren't documented, so those calls are tolerant: they try the likely
paths and params and keep whatever answers. /invoices/api/rentvine/probe?path=... shows the
field names any read-only path returns, to tighten the mapping.
"""
import re
from ..renewals import rentvine as base

configured = base.configured


# ---------- helpers ----------
def _try(paths, params=None):
    """First endpoint that answers wins. Returns (payload, path) or (None, None)."""
    for p in paths:
        try:
            d = base._get(p, params)
            if d:
                return d, p
        except RuntimeError as e:
            if "rejected the API key" in str(e) or "isn't connected" in str(e):
                raise
    return None, None


def _find(obj, *keys, depth=0):
    """First non-empty value for any of `keys` (case-insensitive), searching nested dicts."""
    if depth > 4 or obj is None:
        return None
    want = {k.lower() for k in keys}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in want and v not in (None, "", [], {}):
                return v
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = _find(v, *keys, depth=depth + 1)
                if r not in (None, ""):
                    return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = _find(v, *keys, depth=depth + 1)
            if r not in (None, ""):
                return r
    return None


def _unwrap(d, key):
    return d.get(key) if isinstance(d, dict) and isinstance(d.get(key), dict) else d


def _date(v):
    return str(v)[:10] if v and str(v)[:4] != "0000" else ""


def _money(v):
    n = base._num(v)
    return round(n, 2) if n is not None else None


def _address(obj):
    if not isinstance(obj, dict):
        return "", ""
    return base._addr(obj), base._city_line(obj)


def _owner_name(name):
    """'Oak Ridge Medical Properties LLC - Bo Fried (P)' -> 'Oak Ridge Medical Properties LLC'."""
    name = re.sub(r"\s*\([A-Za-z]\)\s*$", "", (name or "").strip())
    return re.sub(r"\s+-\s+[^-]+$", "", name).strip()


# ---------- one bill / one work order -> invoice fields ----------
def _vendor(contact_id, contact=None):
    contact = _unwrap(contact or {}, "contact")
    if contact_id and not (contact.get("address") or contact.get("city")):
        c, _ = _try(["/vendors/%s" % contact_id, "/contacts/vendors/%s" % contact_id,
                     "/contacts/%s" % contact_id])
        if c:
            contact = {**contact, **_unwrap(c, "contact")}
    line, city = _address(contact)
    return {"rentvine_id": str(contact_id or contact.get("contactID") or ""),
            "name": (contact.get("payeeName") or contact.get("name") or "").strip(),
            "address": line, "city_line": city,
            "phone": contact.get("phone") or "", "email": contact.get("email") or ""}


def _service(prop_id=None, lease_id=None, prop=None, portfolio=None):
    out = {"address": "", "city_line": "", "tenant": "", "owner": ""}
    if not prop and prop_id:
        p, _ = _try(["/properties/%s" % prop_id])
        prop = _unwrap(p or {}, "property")
    if prop:
        out["address"], out["city_line"] = _address(prop)
        if not portfolio and prop.get("portfolioID"):
            pf, _ = _try(["/portfolios/%s" % prop["portfolioID"]])
            portfolio = _unwrap(pf or {}, "portfolio")
    if portfolio:
        out["owner"] = _owner_name(portfolio.get("name"))
    if lease_id:
        l, _ = _try(["/leases/%s" % lease_id], {"includes": "tenants"})
        tenants = _find(l or {}, "tenants") or []
        names = [t.get("name") or _find(t, "name") for t in tenants if isinstance(t, dict)]
        out["tenant"] = ", ".join(n for n in names if n)
    return out


def _wo_basics(wo_id):
    w, _ = _try(["/maintenance/work-orders/%s" % wo_id, "/work-orders/%s" % wo_id])
    w = _unwrap(w or {}, "workOrder")
    return w


def bill(bill_id):
    """Everything we can fill from one Rentvine bill. Missing pieces are left blank."""
    bill_id = int(bill_id)
    raw, _ = _try(["/accounting/bills/%d" % bill_id, "/bills/%d" % bill_id],
                  {"includes": "contact,charges,payments"})
    if raw is None:
        raise RuntimeError("No bill #%d in Rentvine." % bill_id)
    b = _unwrap(raw, "bill")
    out = {"bill_id": bill_id, "warnings": []}
    out["bill_date"] = _date(b.get("billDate"))
    out["due_date"] = _date(b.get("dateDue") or b.get("dueDate"))
    out["description"] = (b.get("description") or "").strip()

    # line items: each charge wraps a transaction (amount, description) plus property/portfolio
    items, prop, portfolio, paid_flags, txn_prop = [], None, None, [], None
    for c in (raw.get("charges") or []) if isinstance(raw, dict) else []:
        if not isinstance(c, dict):
            continue
        t = c.get("transaction") if isinstance(c.get("transaction"), dict) else c
        amt = _money(t.get("amount") if "amount" in t else _find(c, "amount"))
        if amt is not None:
            items.append({"description": (t.get("description") or out["description"] or "").strip(),
                          "qty": 1, "rate": amt})
        prop = prop or (c.get("property") if isinstance(c.get("property"), dict) else None)
        portfolio = portfolio or (c.get("portfolio") if isinstance(c.get("portfolio"), dict) else None)
        txn_prop = txn_prop or t.get("propertyID")
        paid_amt = _money(t.get("amountPaid"))
        if amt is not None and paid_amt is not None:
            paid_flags.append(paid_amt >= amt)
    out["items"] = items
    out["paid"] = bool(paid_flags) and all(paid_flags)
    out["paid_date"] = _payout_date(bill_id, txn_prop or (prop or {}).get("propertyID") or b.get("propertyID")) if out["paid"] else ""
    if out["paid"] and not out["paid_date"]:
        out["warnings"].append("Rentvine shows this bill paid but the payout date wasn't found. Enter the paid date.")

    out["vendor"] = _vendor(b.get("payeeContactID"), raw.get("contact") if isinstance(raw, dict) else None)
    wo_id, lease_id, wo_prop = b.get("workOrderID"), None, None
    out["wo_number"] = ""
    if wo_id:
        w = _wo_basics(wo_id)
        out["wo_number"] = str(w.get("workOrderNumber") or "")
        lease_id, wo_prop = w.get("leaseID"), w.get("propertyID")
    out["service"] = _service(txn_prop or wo_prop or b.get("propertyID"), lease_id, prop=prop, portfolio=portfolio)
    if not out["vendor"]["name"]:
        out["warnings"].append("Couldn't read the vendor from Rentvine. Enter it.")
    if not out["service"]["address"]:
        out["warnings"].append("Couldn't read the service address from Rentvine. Enter it.")
    if not items:
        out["warnings"].append("Couldn't read the bill amount from Rentvine. Enter the line items.")
    return out


def _payout_date(bill_id, prop_id):
    """Date the bill was paid out: the Bill Payout Charge (type 8) transaction for this bill.
    Rentvine's transaction search filters by property but not by bill, so page through the
    property's payouts (newest first) until this bill shows up."""
    if not prop_id:
        return ""
    for page in range(1, 11):
        try:
            rows = base._get("/accounting/transactions/search",
                             {"transactionTypeIDs[]": [8], "propertyIDs[]": [prop_id], "page": page})
        except RuntimeError:
            return ""
        rows = rows if isinstance(rows, list) else []
        dates = [_date(r["transaction"].get("datePosted")) for r in rows
                 if isinstance(r, dict) and isinstance(r.get("transaction"), dict)
                 and str(r["transaction"].get("billID")) == str(bill_id)]
        if dates:
            return max(dates)
        if len(rows) < 10:
            return ""
    return ""


def work_order(wo_id):
    """Fill from a work order that has no bill yet: vendor, address, tenant, description.
    The search row carries the vendor contact and property, so we read the WO through it."""
    w = _wo_basics(wo_id)
    if not w:
        raise RuntimeError("No work order with ID %s in Rentvine." % wo_id)
    row = next((r for r in _wo_search(str(w.get("workOrderNumber") or ""), 1)
                if str(r["workOrder"].get("workOrderID")) == str(wo_id)), {})
    vc = row.get("vendorContact") if isinstance(row.get("vendorContact"), dict) else None
    vendor_id = w.get("vendorContactID")
    out = {"bill_id": "", "warnings": ["This work order has no bill in Rentvine yet. Enter the amount."],
           "wo_number": str(w.get("workOrderNumber") or ""), "description": (w.get("description") or "").strip(),
           "bill_date": _date(w.get("dateClosed") or w.get("actualEndDate") or w.get("scheduledStartDate")),
           "due_date": "", "paid": False, "paid_date": "",
           "vendor": _vendor(vendor_id, vc) if (vendor_id or vc) else
                     {"name": "", "address": "", "city_line": "", "phone": "", "email": "", "rentvine_id": ""},
           "service": _service(w.get("propertyID"), w.get("leaseID"),
                               prop=row.get("property") if isinstance(row.get("property"), dict) else None)}
    out["items"] = [{"description": out["description"], "qty": 1, "rate": ""}]
    return out


# ---------- search ----------
# Confirmed on the live account (Nov 2026):
#   GET /maintenance/work-orders/search?search=...  matches WO #, description, property address and
#       vendor name; rows are {workOrder, property, vendorContact, ...}, 25 per page. A multi-word
#       phrase must appear as-is, so we search word by word and keep rows that match every word.
#   GET /maintenance/work-orders/{id}?includes=bills -> {workOrder, bills:[{bill, transaction}]}
#   The bill list endpoint ignores search/filters, so bills are always found through their work order.
def _wo_search(term, pages=2):
    rows = []
    for page in range(1, pages + 1):
        try:
            d = base._get("/maintenance/work-orders/search", {"search": term, "page": page})
        except RuntimeError as e:
            if "rejected the API key" in str(e) or "isn't connected" in str(e):
                raise
            break
        d = d if isinstance(d, list) else []
        rows += [r for r in d if isinstance(r, dict) and isinstance(r.get("workOrder"), dict)]
        if len(d) < 25:
            break
    return rows


def _haystack(r):
    w, p, v = r["workOrder"], r.get("property") or {}, r.get("vendorContact") or {}
    return " ".join(str(x) for x in (w.get("workOrderNumber"), w.get("description"), w.get("closingDescription"),
                                     base._addr(p) if isinstance(p, dict) else "", (v or {}).get("name"))
                    if x).lower()


def _bills_for_wo(wo_id):
    try:
        d = base._get("/maintenance/work-orders/%s" % wo_id, {"includes": "bills"})
    except RuntimeError:
        return []
    out = []
    for r in (d or {}).get("bills") or [] if isinstance(d, dict) else []:
        b, t = r.get("bill") or {}, r.get("transaction") or {}
        if b.get("billID"):
            amt, paid = _money(t.get("amount")), _money(t.get("amountPaid"))
            out.append({"bill_id": int(b["billID"]), "date": _date(b.get("billDate")), "amount": amt,
                        "paid": amt is not None and paid is not None and paid >= amt,
                        "description": (t.get("description") or "").strip()})
    return out


def _candidates(rows):
    cands = []
    for r in rows:
        w, p, v = r["workOrder"], r.get("property") or {}, r.get("vendorContact") or {}
        base_c = {"wo_id": w.get("workOrderID"), "wo_number": str(w.get("workOrderNumber") or ""),
                  "address": base._addr(p) if isinstance(p, dict) else "",
                  "vendor": (v or {}).get("name") or "", "wo_description": (w.get("description") or "").strip()}
        bills = _bills_for_wo(w["workOrderID"])
        for b in bills:
            cands.append(dict(base_c, type="bill", bill_id=b["bill_id"], date=b["date"], amount=b["amount"],
                              paid=b["paid"], description=b["description"] or base_c["wo_description"]))
        if not bills:
            cands.append(dict(base_c, type="wo", date=_date(w.get("dateClosed") or w.get("dateTimeCreated")),
                              amount=None, paid=False, description=base_c["wo_description"]))
    return cands


def find(q):
    """Bills (plus work orders with no bill yet) matching a bill #, WO #, address, vendor or job words."""
    q = (q or "").strip()
    if not q:
        return []
    m = re.match(r"^\s*(bill|b|wo|work\s*order)\s*#?\s*(\d+)\s*$", q, re.I)
    if m and m.group(1).lower() in ("bill", "b"):
        try:
            b = bill(int(m.group(2)))
        except Exception:
            return []
        return [{"type": "bill", "bill_id": int(m.group(2)), "date": b["bill_date"],
                 "amount": round(sum(i["rate"] for i in b["items"]), 2) or None, "paid": b["paid"],
                 "description": b["description"], "wo_number": b["wo_number"],
                 "address": b["service"]["address"], "vendor": b["vendor"]["name"]}]
    compact = m.group(2) if m else re.sub(r"[#\s]", "", q)
    rows = []
    if compact.isdigit():
        rows = [r for r in _wo_search(compact, 1) if str(r["workOrder"].get("workOrderNumber")) == compact]
        cands = _candidates(rows)
        if not cands and len(compact) < 6:          # not a WO number: treat it as a bill #
            try:
                b = bill(int(compact))
                cands = [{"type": "bill", "bill_id": int(compact), "date": b["bill_date"], "amount":
                          round(sum(i["rate"] for i in b["items"]), 2) or None, "paid": b["paid"],
                          "description": b["description"], "wo_number": b["wo_number"],
                          "address": b["service"]["address"], "vendor": b["vendor"]["name"]}]
            except Exception:
                cands = []
        return cands

    words = [w.lower() for w in re.findall(r"[A-Za-z0-9']+", q) if len(w) > 1]
    if not words:
        return []
    found = {}
    # whole phrase first, then each word (longest first) so "Henderson faucet" still finds the WO
    for term in [q] + sorted(set(words), key=len, reverse=True)[:3]:
        for r in _wo_search(term):
            found.setdefault(r["workOrder"]["workOrderID"], r)
        hits = [r for r in found.values() if all(w in _haystack(r) for w in words)]
        if len(hits) >= 1 and term != q:
            break
    rows = [r for r in found.values() if all(w in _haystack(r) for w in words)]
    if not rows:   # nothing matches every word: show the best partial matches
        rows = sorted(found.values(), key=lambda r: -sum(w in _haystack(r) for w in words))[:8]
    rows.sort(key=lambda r: str(r["workOrder"].get("dateTimeCreated") or ""), reverse=True)
    return _candidates(rows[:10])


# ---------- setup helpers ----------
def _shape(d, depth=0):
    if isinstance(d, dict) and depth < 5:
        return {k: _shape(v, depth + 1) for k, v in d.items()}
    if isinstance(d, list):
        return [_shape(d[0], depth + 1)] if d else []
    return type(d).__name__


PROBE_PREFIXES = ("/accounting/bills", "/maintenance/", "/properties", "/portfolios", "/vendors", "/contacts")


def probe(path, params=None):
    """Field names (no values) a read-only Rentvine path returns. Limited to the paths this tool uses."""
    if not path.startswith(PROBE_PREFIXES) or ".." in path:
        raise RuntimeError("Path not allowed.")
    return {"path": path, "fields": _shape(base._get(path, params or None))}


def bill_fields(bill_id):
    return probe("/accounting/bills/%d" % int(bill_id), {"includes": "contact,charges,payments"})
