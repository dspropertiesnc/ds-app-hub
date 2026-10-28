"""Minimal Rentvine API client for the renewal tool.

Auth (per docs.rentvine.com): HTTP Basic, API access key = username, secret = password.
Base URL: https://{RENTVINE_ACCOUNT}.rentvine.com/api/manager

We use the documented lease export (GET /leases/export), which returns each lease with
its property, unit, portfolio and tenants in one record. Current rent comes from
`unit.rent`, the rent amount Rentvine keeps on the unit. The editor shows it as
"from Rentvine" and the team can correct it before saving.
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
        "current_rent": _num(unit.get("rent")),
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
    return out[:limit]


def by_owner(owner):
    """Every open lease in one owner's portfolio, month-to-month first (for 'add all of Munish's MTM leases')."""
    owner = (owner or "").lower().strip()
    rows = [r for r in _all_leases() if owner and owner in r["owner"].lower()]
    rows.sort(key=lambda r: (not r["month_to_month"], r["address"]))
    return rows
