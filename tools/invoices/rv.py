"""Rentvine lookups for the invoice generator.

Given a bill number (the number in the bill's Rentvine URL, e.g. /accounting/bills/1099), pull:
vendor name + address, bill/due date, description, line items, work order number, service
property, tenant names, owner (portfolio) name, and the paid date if Rentvine reports one.

Uses the same API key as the renewal tool (tools/renewals/rentvine.py). Rentvine's field names
aren't fully documented, so every read is tolerant: we try the likely endpoints, then search the
JSON for the first matching key. Anything we can't find comes back blank and staff fill it in.
Open /invoices/api/rentvine/bill/<id>/fields on the first live run to see the field names
Rentvine returns and tighten the mapping if needed.
"""
from ..renewals import rentvine as base

configured = base.configured


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
    return str(v)[:10] if v else ""


def _money(v):
    n = base._num(v)
    return round(n, 2) if n is not None else None


def _address(obj):
    if not isinstance(obj, dict):
        return "", ""
    return base._addr(obj), base._city_line(obj)


def _charges(d):
    for k in ("charges", "billCharges", "items", "lineItems"):
        lst = d.get(k) if isinstance(d, dict) else None
        if isinstance(lst, list) and lst:
            out = []
            for c in lst:
                c = c.get("billCharge", c.get("charge", c)) if isinstance(c, dict) else {}
                amt = _money(c.get("amount"))
                if amt is None:
                    continue
                out.append({"description": (c.get("description") or c.get("memo") or "").strip(),
                            "qty": 1, "rate": amt})
            if out:
                return out
    return []


def bill(bill_id):
    """Everything we can fill from one Rentvine bill. Missing pieces are left blank."""
    bill_id = int(bill_id)
    raw, _ = _try(["/accounting/bills/%d" % bill_id, "/bills/%d" % bill_id],
                  {"includes": "contact,charges,payments"})
    if raw is None:
        raise RuntimeError("Couldn't find bill #%d in Rentvine." % bill_id)
    b = _unwrap(raw, "bill")

    out = {"bill_id": bill_id, "warnings": []}
    out["bill_date"] = _date(_find(b, "billDate", "date", "postDate"))
    out["due_date"] = _date(_find(b, "dueDate"))
    out["description"] = (_find(b, "description", "memo") or "").strip()
    out["items"] = _charges(raw) or _charges(b)
    if not out["items"]:
        total = _money(_find(b, "amount", "total", "totalAmount"))
        if total:
            out["items"] = [{"description": out["description"], "qty": 1, "rate": total}]

    # Paid status. Rentvine marks bills paid via a payout; look for any paid-date style field.
    out["paid_date"] = _date(_find(raw, "datePaid", "paidDate", "paymentDate", "lastPaymentDate", "payoutDate"))
    bal = _money(_find(b, "balance", "amountDue", "balanceDue", "remainingAmount"))
    out["paid"] = bool(out["paid_date"]) or (bal == 0 and bool(out["items"]))
    if out["paid"] and not out["paid_date"]:
        out["warnings"].append("Rentvine shows the bill as paid but didn't give a paid date. Enter it.")

    # Vendor
    vid = _find(b, "payeeContactID", "contactID", "vendorContactID")
    contact = raw.get("contact") if isinstance(raw, dict) and isinstance(raw.get("contact"), dict) else None
    if vid and not (contact and _find(contact, "address", "city")):
        c, _ = _try(["/vendors/%s" % vid, "/contacts/vendors/%s" % vid, "/contacts/%s" % vid])
        if c:   # the vendor record wins, but keep anything only the bill's contact had (e.g. phone)
            contact = {**_unwrap(contact or {}, "contact"), **_unwrap(c, "contact")}
    contact = _unwrap(contact or {}, "contact")
    addr_obj = contact
    for k in ("addresses", "contactAddresses"):
        if isinstance(contact.get(k), list) and contact[k]:
            a = contact[k][0]
            addr_obj = a.get("address", a) if isinstance(a, dict) else contact
            break
    line, city = _address(addr_obj)
    out["vendor"] = {"rentvine_id": vid, "name": (_find(contact, "name", "displayName") or "").strip(),
                     "address": line, "city_line": city,
                     "phone": _find(contact, "phone", "phoneNumber") or "",
                     "email": _find(contact, "email") or ""}

    # Work order -> number, property, lease
    wo_id = _find(b, "workOrderID")
    prop_id = _find(b, "propertyID") or _find(raw, "propertyID")
    lease_id = None
    out["wo_number"] = ""
    if wo_id:
        w, _ = _try(["/maintenance/work-orders/%s" % wo_id, "/work-orders/%s" % wo_id])
        w = _unwrap(w or {}, "workOrder")
        out["wo_number"] = str(_find(w, "workOrderNumber", "number") or "")
        prop_id = prop_id or _find(w, "propertyID")
        lease_id = _find(w, "leaseID")

    # Service location + owner
    out["service"] = {"address": "", "city_line": "", "tenant": "", "owner": ""}
    if prop_id:
        p, _ = _try(["/properties/%s" % prop_id])
        p = _unwrap(p or {}, "property")
        out["service"]["address"], out["service"]["city_line"] = _address(p)
        port_id = _find(p, "portfolioID")
        if port_id:
            pf, _ = _try(["/portfolios/%s" % port_id])
            out["service"]["owner"] = (_find(_unwrap(pf or {}, "portfolio"), "name") or "").strip()
    if lease_id:
        l, _ = _try(["/leases/%s" % lease_id], {"includes": "tenants"})
        tenants = _find(l or {}, "tenants") or []
        names = [t.get("name") or _find(t, "name") for t in tenants if isinstance(t, dict)]
        out["service"]["tenant"] = ", ".join(n for n in names if n)

    for k, label in (("name", "vendor name"), ("address", "vendor address")):
        if not out["vendor"][k]:
            out["warnings"].append("Couldn't read the %s from Rentvine. Enter it." % label)
    if not out["service"]["address"]:
        out["warnings"].append("Couldn't read the service address from Rentvine. Enter it.")
    return out


def bill_fields(bill_id):
    """Field names (no values) Rentvine returns for a bill, for the first-run mapping check."""
    def shape(d, depth=0):
        if isinstance(d, dict) and depth < 3:
            return {k: shape(v, depth + 1) for k, v in d.items()}
        if isinstance(d, list):
            return [shape(d[0], depth + 1)] if d else []
        return type(d).__name__
    raw, path = _try(["/accounting/bills/%d" % int(bill_id), "/bills/%d" % int(bill_id)],
                     {"includes": "contact,charges,payments"})
    return {"endpoint": path, "fields": shape(raw)}
