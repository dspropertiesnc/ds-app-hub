"""Claude reads one property's rent reports (PDFs or images) and drafts the rental analysis page.

Returns the same JSON shape the editor's normalize() expects, so the review screen works
exactly like the claude.ai version did. Also writes the short owner explanation on request.
"""
import os, re, json, base64

MODEL = os.getenv("OWNER_PACKET_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

EXAMPLES = """Examples of the tone:
"The closest matches are two houses on Drakestone Ct, a quarter mile away, built the same year and renting for $1,850 and $1,950. This home is a bit smaller than most nearby comps, which keeps the estimate just under the neighborhood average."
"Five-bedroom rentals are less common in this area, so Rentometer had to search a 10-mile radius and pulled in higher-priced Greensboro homes. Zillow and RentRange stayed local, and the best nearby comp, a same-size 5-bedroom on Mallison Way, rents for $2,369."
"This home has some of the strongest comps in the portfolio, with several rentals on the same street and on Pilot Ridge Ct next door, all between $1,820 and $2,099.\""""

SYSTEM = """You are helping Doss & Spaulding Properties, a property management company in Greensboro, NC, build a one-page rental analysis for a property owner.
The attached files are rent reports for ONE subject property. Sources may include Zillow (Rent Zestimate report), RentRange, Rentometer, Rentfinder, or others.

Reply with ONLY a JSON object in exactly this shape:
{"subject":{"street":"8 Mizell Ct","cityStateZip":"Greensboro, NC 27405","beds":3,"baths":2,"sqft":1008,"yearBuilt":1994,"homeType":"Single-family"},
 "estimates":[{"source":"Zillow","value":1367,"note":"Rent Zestimate"}],
 "comps":[{"address":"515 Denny Rd","beds":3,"baths":2,"sqft":1218,"distanceMi":0.34,"rent":1595,"status":"leased","date":"Sep 2026","sources":["Rentometer"],"pick":true}],
 "recommendedLow":1550,"recommendedHigh":1625,
 "blurb":"...",
 "vacancyRate":3.8,
 "flags":["..."]}

Rules:
- estimates: one per source report. Zillow: the Rent Zestimate, note "Rent Zestimate". RentRange: the RentRange estimate, note "RentRange estimate". Rentometer: the average (mean), note "Average of N rentals" (use "N-mile search radius" instead if the radius is 5 miles or more). Rentfinder: the monthly estimate, note "Monthly estimate". Any other source: its main estimate with a note of 4 words or fewer. Never mention confidence percentages. Source names exactly as the brand writes them.
- subject: prefer public-record and RentRange values. If sources disagree on square feet, beds, or baths, use the majority or public record and add a flag naming the conflict. homeType is one of "Single-family", "Townhouse", "Condo", "Duplex", "Apartment".
- comps: only rentals that match the subject's bedroom count (allow plus or minus one bedroom only when there are fewer than 4 exact matches) and home type. Exclude apartment complexes and multi-unit listings (for example "7 units available") when the subject is a house. Treat the same street address across sources as one row (for example "217 Kinnley, CT" and "217 Kinnley Ct" are the same); if their rents differ, use the most recent listing and add a flag. Up to 12 comps, best match first (closest, similar size, recent). "address" is the street address only, no city, state, or ZIP. Use null for unknown numbers.
- comp status: "leased" when the report shows a completed lease or rented/closed listing, "asking" when it is a current or past list price, null if unclear. date: the month and year it leased or was listed, like "Sep 2026", or null.
- Set "pick": true on the 4 best comps for an owner-facing table, avoiding outliers. All others "pick": false.
- flags: short notes for the reviewer (not the owner): outlier rents, conflicting details, a source whose comps look unrelated, anything to double-check. Empty array if nothing.
- recommendedLow/High: a realistic asking-rent range rounded to $25, usually $50 to $150 wide, grounded more in the closest comps than in the automated estimates.
- blurb: 2 or 3 plain sentences, at most 55 words, written to the owner, explaining the range by pointing to specific nearby comps and how this home compares (size, age, location). Friendly and factual, no hype, no dashes as punctuation.
""" + EXAMPLES + """
- vacancyRate: the estimated vacancy percent if any report gives one, else null.
Output ONLY the JSON object, no prose and no code fences."""


def _client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Server has no ANTHROPIC_API_KEY set.")
    from anthropic import Anthropic
    return Anthropic(api_key=key)


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
        return json.loads(raw[:raw.rfind("}") + 1])


def analyze(files, hint=""):
    """files: list of (filename, bytes) for ONE property."""
    content = []
    for name, data in files:
        if name.lower().endswith(".pdf"):
            content.append({"type": "document", "title": name, "source": {
                "type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
        else:
            mt = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt,
                                                         "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": ("The team says the subject property is: %s\n" % hint if hint else "")
                    + "Build the JSON as specified."})
    msg = _client().messages.create(model=MODEL, max_tokens=6000, system=SYSTEM,
                                    messages=[{"role": "user", "content": content}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    out = _parse_json(raw)
    if not isinstance(out, dict):
        raise RuntimeError("The reports came back in a format the app couldn't use. Try again.")
    return out


def _money(v):
    try:
        return "$" + format(int(round(float(v))), ",")
    except (TypeError, ValueError):
        return "$?"


def redraft(d):
    """Rewrite the 2-3 sentence owner explanation from the comps currently checked."""
    comps = "\n".join("%s: %s bed / %s bath, %s sq ft, %s mi away, %s" % (
        c.get("address", ""), c.get("beds", "?"), c.get("baths", "?"), c.get("sqft", "?"),
        c.get("dist", "?"), _money(c.get("rent"))) for c in (d.get("comps") or []) if c.get("checked"))
    ests = "\n".join("%s: %s" % (e.get("source", ""), _money(e.get("value"))) for e in (d.get("estimates") or []))
    prompt = ("Write 2 or 3 plain sentences (at most 55 words) to a property owner explaining why we recommend "
              "%s to %s per month for %s, a %s bed / %s bath, %s sq ft %s built %s. Point to specific comps below "
              "and how this home compares in size, age, or location. Friendly and factual, no hype, no dashes as "
              "punctuation. Reply with only the sentences.\n%s\nComps:\n%s\nAutomated estimates:\n%s") % (
        _money(d.get("recLow")), _money(d.get("recHigh")), d.get("street", "this home"), d.get("beds", "?"),
        d.get("baths", "?"), d.get("sqft", "?"), d.get("type", "home"), d.get("year", "?"), EXAMPLES, comps, ests)
    msg = _client().messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    return re.sub(r'^"|"$', "", text)
