"""Reads uploaded rent comp reports (Rentometer, RentRange, Zillow Rent Zestimate, or similar)
for ONE property and returns structured comps plus a suggested market range.

The source names (Zillow etc.) are kept for the team's reference in the editor only.
They never reach the owner PDF or the email draft.
"""
import os, re, json, base64

MODEL = os.getenv("RENEWALS_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

SYSTEM = """You read residential rent comparable reports for ONE subject property and return strict JSON.
Reports may be Rentometer, RentRange "Rental Property Analysis", Zillow "Rent Zestimate Report", or similar.

Return ONLY this JSON object (omit fields you cannot find; never invent numbers):
{
 "subject": {"address": "", "city_line": "City, ST 12345", "beds": 0, "baths": 0, "sqft": 0,
             "year_built": 0, "home_type": "Single-family|Condo|Townhouse|Duplex|Apartment"},
 "estimates": [{"source": "Zillow|RentRange|Rentometer|...", "value": 0, "detail": "short note, e.g. 'range $1,403-$1,564' or '92% confidence' or 'average of 24 rentals'"}],
 "comps": [{"address": "street only, no city", "beds": 0, "baths": 0, "sqft": 0, "distance_mi": 0,
            "rent": 0, "type": "House|Condo|Apartment|Townhouse", "year_built": 0, "last_seen": "",
            "source": "", "outlier": false}],
 "market_low": 0, "market_high": 0,
 "featured": ["addresses of the 4 best comps to show the owner, best first"],
 "notes": ["short internal notes for the property manager, e.g. data conflicts"]
}

Rules:
- comps: include every listed comparable rental from every report. Merge duplicates of the same street
  address (keep the most recent/most complete row). Mark a row "outlier": true if the report says it was
  excluded as an outlier, or it is clearly not comparable (different bedroom count AND far larger/smaller).
- Strip city/state/zip from comp addresses ("3207 Harte Pl"). Unit numbers stay ("2620 Guyer St, Unit 1A").
- Size or distance missing in the report = omit the field (do not write 0).
- subject: prefer the values most reports agree on. If reports disagree (e.g. 1 vs 1.5 baths), use the
  majority and add a note.
- market_low / market_high: the realistic asking-rent range for the SUBJECT as it stands today, based on
  the comps most like it (same bedroom count, similar size, age and home type, closest first), cross-checked
  against the automated estimates. Discount comps that are bigger, newer, or a different home type, and
  estimates built from them (say so in notes). Round both to the nearest $25. Typical spread $100-$200.
- featured: 4 comps that best support the range: same bedroom count, closest, similar type and size.
  Prefer a unit in the same complex/street if there is one. Never feature an outlier.
- Money values are plain numbers (1550), never strings with $ or commas.
Output ONLY the JSON object, no prose and no code fences."""


def _parse_json(raw):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    i = raw.find("{")
    if i > 0:
        raw = raw[i:]
    try:
        return json.loads(raw)
    except Exception:
        cut = raw.rfind("}")
        return json.loads(raw[:cut + 1])


def _key(addr):
    a = (addr or "").lower()
    a = re.sub(r"[^a-z0-9 ]", " ", a)
    a = re.sub(r"\b(street|st|road|rd|avenue|ave|place|pl|drive|dr|court|ct|lane|ln|way|circle|cir|boulevard|blvd)\b", "", a)
    return " ".join(a.split())


def extract(files, hint=""):
    """files: list of (filename, bytes). Returns the cleaned dict."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("Server has no ANTHROPIC_API_KEY set.")
    content = []
    for name, data in files:
        if name.lower().endswith(".pdf"):
            content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                            "data": base64.b64encode(data).decode()}, "title": name})
        else:
            mt = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt,
                            "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": "Subject property: %s\nExtract as specified." % (hint or "see reports")})
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                 messages=[{"role": "user", "content": content}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return clean(_parse_json(raw))


def _round25(v):
    try:
        return int(round(float(v) / 25.0) * 25)
    except (TypeError, ValueError):
        return None


def clean(d):
    d = d if isinstance(d, dict) else {}
    seen, comps = {}, []
    for c in d.get("comps") or []:
        if not isinstance(c, dict) or not c.get("address") or not c.get("rent"):
            continue
        k = _key(c["address"])
        if k in seen:
            prev = seen[k]
            for f, v in c.items():
                if v not in (None, "", 0) and prev.get(f) in (None, "", 0):
                    prev[f] = v
            continue
        seen[k] = c
        comps.append(c)
    feat = [_key(a) for a in (d.get("featured") or []) if isinstance(a, str)]
    for c in comps:
        c["featured"] = _key(c["address"]) in feat and not c.get("outlier")
    # featured first in the model's order, then the rest by distance
    order = {k: i for i, k in enumerate(feat)}
    comps.sort(key=lambda c: (0 if c["featured"] else 1, order.get(_key(c["address"]), 99),
                              c.get("distance_mi") or 99))
    lo, hi = _round25(d.get("market_low")), _round25(d.get("market_high"))
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    return {"subject": d.get("subject") or {}, "estimates": d.get("estimates") or [],
            "comps": comps, "market_low": lo, "market_high": hi,
            "notes": [n for n in (d.get("notes") or []) if isinstance(n, str)]}
