"""Find an owner in Rentvine and list their homes for the packet.

Built on the shared Rentvine client (tools/renewals/rentvine.py). Homes come from the lease
export: a home with an open lease is occupied (current lease rent filled in, never the unit's
market rent); a home whose leases are all closed is vacant. A home that has never had a lease
in Rentvine won't show up, so staff add those by hand.
"""
from tools.renewals import rentvine

MAX_OWNERS = 8
MAX_HOMES = 40


def configured():
    return rentvine.configured()


def _key(r):
    return ("%s|%s" % (r.get("address", ""), r.get("city_line", ""))).lower().strip()


def owners(q):
    q = (q or "").lower().strip()
    if len(q) < 2:
        return []
    terms = q.split()
    groups = {}
    for r in rentvine.all_rows():
        name = r.get("owner") or ""
        hay = " ".join([name, r.get("address", ""), r.get("city_line", "")] + (r.get("tenants") or [])).lower()
        if not all(t in hay for t in terms):
            continue
        gid = r.get("portfolio_id") or name
        groups.setdefault(gid, {"owner": name, "portfolio_id": r.get("portfolio_id")})
    out = []
    for gid, g in list(groups.items())[:MAX_OWNERS]:
        homes = {}
        for r in rentvine.all_rows():
            if (r.get("portfolio_id") or r.get("owner")) != gid:
                continue
            homes.setdefault(_key(r), []).append(r)
        g["count"] = len(homes)
        out.append(g)
    out.sort(key=lambda g: g["owner"].lower())
    return out


def homes(portfolio_id=None, owner=""):
    rows = [r for r in rentvine.all_rows()
            if (portfolio_id and str(r.get("portfolio_id")) == str(portfolio_id))
            or (not portfolio_id and owner and r.get("owner") == owner)]
    grouped = {}
    for r in rows:
        grouped.setdefault(_key(r), []).append(r)
    out = []
    for k, rs in list(grouped.items())[:MAX_HOMES]:
        open_ = [r for r in rs if not r.get("closed")]
        base = (open_ or sorted(rs, key=lambda r: r.get("end_date") or "", reverse=True))[0]
        rent = None
        tenants = []
        if open_:
            filled = rentvine._fill_rent([open_[0]])
            rent = filled[0].get("current_rent") if filled else None
            tenants = open_[0].get("tenants") or []
        out.append({
            "address": base.get("address", ""), "city_line": base.get("city_line", ""),
            "beds": base.get("beds"), "baths": base.get("baths"), "sqft": base.get("sqft"),
            "occupied": bool(open_), "rent": rent, "tenants": tenants,
        })
    out.sort(key=lambda h: h["address"])
    return out
