"""Minimal Rentvine API client for the renewal tool.

Auth (per docs.rentvine.com): HTTP Basic, API access key = username, secret = password.
Base URL: https://{RENTVINE_ACCOUNT}.rentvine.com/api/manager

We use the documented lease export (GET /leases/export), which returns each lease with
its property, unit, portfolio and tenants in one record.

Current rent = the rent on the TENANT'S LEASE, never the unit's "market rent" (`unit.rent`),
which often doesn't match the lease. We look for the lease-level rent on the export record,
then on the lease itself (GET /leases/{leaseID}), including its recurring rent charges.
If neither has it, current rent is left blank and the editor asks staff to enter it from
the lease. `/renewals/api/rentvine/lease/<id>/fields` lists the field names Rentvine returns,
to confirm the mapping on the first live run.
"""
import os, time, base64, json, datetime, threading
import urllib.request, urllib.parse, urllib.error

ACCOUNT = os.getenv("RENTVINE_ACCOUNT", "").strip()
KEY = os.getenv("RENTVINE_API_KEY", "").strip()
SECRET = os.getenv("RENTVINE_API_SECRET", "").strip()
CACHE_SECONDS = int(os.getenv("RENTVINE_CACHE_SECONDS", "600"))
PAGE_SIZE = 100
MAX_PAGES = 60

_cache = {"at": 0, "rows": None}
_lock = threading.Lock()


def configured():
    return bool(ACCOUNT and KEY and SECRET)


def _get(path, params=None):
    if not configured():
        raise RuntimeError("Rentvine isn't connected (set RENTVINE_ACCOUNT, RENTVINE_API_KEY, RENTVINE_API_SECRET).")
    url = "https://%s.rentvine.com/api/manager%s" % (ACCOUNT, path)
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    auth = base64.b64encode(("%s:%s" % (KEY, SECRET)).encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + auth,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Rentvine rejected the API key (check the key, secret and its role).")
        raise RuntimeError("Rentvine error %s on %s" % (e.code, path))
    except urllib.error.URLError as e:
        raise RuntimeError("Couldn't reach Rentvine: %s" % e.reason)


def _records(payload):
    """Export endpoints return a list of wrapped records; tolerate a {data: [...]} envelope too."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "results", "items", "leases"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _addr(obj):
    if not isinstance(obj, dict):
        return ""
    line = obj.get("address") or " ".join(
        str(x) for x in (obj.get("streetNumber"), obj.get("streetName")) if x)
    if obj.get("address2"):
        line = "%s %s" % (line, obj["address2"])
    return (line or "").strip()


def _city_line(obj):
    if not isinstance(obj, dict):
        return ""
    state = obj.get("stateID") or obj.get("state") or ""
    city = obj.get("city") or ""
    zipc = obj.get("postalCode") or ""
    left = ", ".join(x for x in (city, str(state)) if x)
    return ("%s %s" % (left, zipc)).strip()


RENT_KEYS = ("rent", "rentAmount", "monthlyRent", "leaseRent", "currentRent", "recurringRentAmount")
CHARGE_LISTS = ("recurringCharges", "recurring_charges", "charges")
# Section 8 leases split rent: the tenant portion posts as Rent, the housing authority's (HAP)
# portion posts to 4110 Government Assistance Rent. Lease rent = both added together.
GOV_ACCOUNT = os.getenv("RENTVINE_GOV_RENT_ACCOUNT", "4110")


def _is_gov(c, acct, name):
    codes = " ".join(str(x) for x in (c.get("accountNumber"), c.get("accountCode"), acct.get("number"),
                                       acct.get("code"), acct.get("accountNumber")) if x)
    return GOV_ACCOUNT in codes or name.startswith(GOV_ACCOUNT) or "government assistance" in name


def _rent_charges(obj):
    """Active monthly rent lines from a recurring-charges list -> {"total", "gov"} or None."""
    if not isinstance(obj, dict):
        return None
    today = datetime.date.today().isoformat()
    for k in CHARGE_LISTS:
        lst = obj.get(k)
        if not (isinstance(lst, list) and lst):
            continue
        total = gov = 0.0
        found = False
        for c in lst:
            c = c.get("recurringCharge", c) if isinstance(c, dict) else {}
            acct = c.get("chargeAccount") or c.get("account") or {}
            acct = acct if isinstance(acct, dict) else {}
            name = " ".join(str(x) for x in (c.get("description"), c.get("accountName"), acct.get("name")) if x).lower()
            amt = _num(c.get("amount"))
            if not amt or (c.get("endDate") and str(c["endDate"])[:10] < today):
                continue
            if _is_gov(c, acct, name):          # HAP portion counts even if not flagged as rent
                total += amt; gov += amt; found = True
                continue
            flag = c.get("isRent", acct.get("isRent"))
            if flag is not None:                # Rentvine's own rent flag wins when it's there
                is_rent = flag in (1, "1", True)
            else:                               # otherwise go by name, skipping pet rent and fees
                is_rent = "rent" in name and not any(w in name for w in ("pet", "fee", "storage", "parking"))
            if is_rent:
                total += amt; found = True
        if found:
            return {"total": total, "gov": gov}
    return None


def _field_rent(lease):
    if isinstance(lease, dict):
        for k in RENT_KEYS:
            v = _num(lease.get(k))
            if v:
                return {"total": v, "gov": 0.0}
    return None


def fetch_lease_rent(lease_id):
    """Read the lease directly for its recurring rent charges (tenant rent + any 4110 HAP rent)."""
    field = None
    for params in ({"includes": "recurringCharges"}, None):
        try:
            d = _get("/leases/%s" % int(lease_id), params)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        rec = d.get("lease", d)
        r = _rent_charges(rec) or _rent_charges(d)
        if r:
            return r
        field = field or _field_rent(rec)
    return field


def lease_fields(lease_id):
    """Field names (no values) on the lease export record and the lease detail, for setup checks."""
    out = {}
    for r in _records(_get("/leases/export", {"leaseIDs[]": [int(lease_id)]})):
        out["export"] = {k: sorted(v.keys()) if isinstance(v, dict) else type(v).__name__ for k, v in r.items()}
    try:
        d = _get("/leases/%s" % int(lease_id), {"includes": "recurringCharges"})
        out["detail"] = {k: sorted(v.keys()) if isinstance(v, dict) else type(v).__name__ for k, v in d.items()} \
            if isinstance(d, dict) else type(d).__name__
    except Exception as e:
        out["detail"] = str(e)
    return out


def _normalize(rec):
    lease = rec.get("lease") or {}
    prop = rec.get("property") or {}
    unit = rec.get("unit") or {}
    port = rec.get("portfolio") or {}
    tenants = [t.get("name") for t in (lease.get("tenants") or []) if isinstance(t, dict) and t.get("name")]
    end = (lease.get("endDate") or "")[:10]
    today = datetime.date.today().isoformat()
    mtm = (not end) or end < today
    addr = _addr(unit) or _addr(prop)
    baths = None
    fb, hb = _num(unit.get("fullBaths")), _num(unit.get("halfBaths"))
    if fb is not None:
        baths = fb + 0.5 * (hb or 0)
    return {
        "lease_id": lease.get("leaseID"),
        "address": addr,
        "city_line": _city_line(unit) or _city_line(prop),
        "tenants": tenants,
        "_rent": _rent_charges(lease) or _rent_charges(rec),   # never unit.rent (market rent)
        "_field_rent": _field_rent(lease),
        "start_date": (lease.get("startDate") or "")[:10],
        "end_date": end,
        "month_to_month": mtm,
        "closed": bool(lease.get("closedDate")),
        "beds": _num(unit.get("beds")),
        "baths": baths,
        "sqft": _num(unit.get("size")),
        "owner": port.get("name") or "",
        "portfolio_id": port.get("portfolioID"),
    }


def _all_leases(force=False):
    with _lock:
        if not force and _cache["rows"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["rows"]
        rows = []
        for page in range(1, MAX_PAGES + 1):
            batch = _records(_get("/leases/export", {"page": page, "pageSize": PAGE_SIZE}))
            rows.extend(_normalize(r) for r in batch if isinstance(r, dict))
            if len(batch) < PAGE_SIZE:
                break
        rows = [r for r in rows if not r["closed"]]
        _cache.update(at=time.time(), rows=rows)
        return rows


def _fill_rent(rows):
    """Lease rent for each row: recurring charges on the export record, else the lease detail
    (charges, then a plain rent field). Section 8 HAP rent (4110) is added in and reported."""
    out = []
    for r in rows:
        if not r.get("_rent_checked"):
            rent = r.get("_rent")
            if not rent and r["lease_id"]:
                rent = fetch_lease_rent(r["lease_id"])
            rent = rent or r.get("_field_rent")
            r["current_rent"] = rent["total"] if rent else None
            r["gov_rent"] = rent["gov"] if rent and rent["gov"] else None
            r["_rent_checked"] = True   # cached rows keep the result until the cache refreshes
        out.append({k: v for k, v in r.items() if not k.startswith("_")})
    return out


def search(q, limit=12):
    q = (q or "").lower().strip()
    if len(q) < 2:
        return []
    terms = q.split()
    out = []
    for r in _all_leases():
        hay = " ".join([r["address"], r["city_line"], r["owner"]] + r["tenants"]).lower()
        if all(t in hay for t in terms):
            out.append(r)
    out.sort(key=lambda r: (not r["month_to_month"], r["address"]))
    return _fill_rent(out[:limit])


def by_owner(owner):
    """Every open lease in one owner's portfolio, month-to-month first (for 'add all of Munish's MTM leases')."""
    owner = (owner or "").lower().strip()
    rows = [r for r in _all_leases() if owner and owner in r["owner"].lower()]
    rows.sort(key=lambda r: (not r["month_to_month"], r["address"]))
    return _fill_rent(rows[:40])
