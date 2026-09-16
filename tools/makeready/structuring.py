"""Turns flagged make-ready inspection items into the punchlist spec.

Unlike the punchlist tool, we already know the room and the exact item that was
flagged, so the fallback (no API key) produces a perfectly usable document on its
own. Claude is used to rewrite an inspection flag into an actionable repair
instruction and to merge duplicates across rooms.
"""
import os, json, datetime

SYSTEM = """You convert a property make-ready INSPECTION into a REPAIR PUNCHLIST
for Doss & Spaulding Properties, a property manager in Greensboro, NC.

You receive only the items an inspector flagged as needing attention. Each line
gives the zone (Interior/Exterior), the room or system, the checklist item, and
the inspector's note. Return STRICT JSON only, matching:

{
  "sections": [
    {"name": "Interior", "subsections": [
        {"name": "<room or system>", "items": [
            {"task": "<clear repair instruction a handyman can act on>",
             "note": "<optional clarification, else omit>"}
        ]}
    ]},
    {"name": "Exterior", "subsections": [ ... ]}
  ]
}

RULES:
- Turn each flag into an ACTION. The checklist item says what was checked; the
  note says what is wrong. Write what needs to be DONE.
  "Toilet working & flappers good" + note "runs constantly" -> "Replace the
  toilet flapper and fill valve; toilet runs continuously."
- KEEP THE ROOM. Use the room/system given as the subsection name, exactly as
  provided (e.g. "Bathroom 2", "Bedroom 3", "Kitchen — Range & Vent Hood").
  Never merge Bedroom 2 and Bedroom 3 into one "Bedrooms" group.
- PRESERVE every specific location, count and measurement from the note exactly.
  Never invent specifics, quantities, part numbers or causes that aren't stated.
- If a note is vague ("looks bad"), still write the task and add a "note"
  flagging that it needs a closer look on site. Do not guess the fix.
- If an item was flagged with NO note, write the task from the checklist item
  itself, phrased as the repair (e.g. "Window locks" -> "Install/repair window
  locks"), and add note "Flagged during inspection - no detail given."
- Put each item in the zone it was given. Do not move items between zones.
- Order subsections the way they arrive.
- Do not add tasks that are not in the input. Do not include a materials list.
- Output ONLY the JSON object. No prose, no code fences."""


def _line(f):
    note = (f.get("note") or "").strip()
    base = "[%s / %s] %s" % (f["zone"], f["room"], f["label"])
    return base + (" — NOTE: " + note if note else " — (no note given)")


def _fallback(flags):
    """Group straight from the inspection structure. Already well organised."""
    zones = {}
    for f in flags:
        z = zones.setdefault(f["zone"], {})
        z.setdefault(f["room"], []).append(f)
    sections = []
    for zname in ("Interior", "Exterior"):
        if zname not in zones:
            continue
        subs = []
        for room, items in zones[zname].items():
            rows = []
            for f in items:
                note = (f.get("note") or "").strip()
                it = {"task": f["label"]}
                it["note"] = note if note else "Flagged during inspection - no detail given."
                rows.append(it)
            subs.append({"name": room, "items": rows})
        sections.append({"name": zname, "subsections": subs})
    if not sections:
        sections = [{"name": "Interior", "subsections": [{"name": "General", "items": []}]}]
    return {"sections": sections}


def structure(flags, extra_notes=""):
    """flags: [{zone, room, label, note}] -> (data, mode)"""
    if not flags:
        return _fallback(flags), "fallback"
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _fallback(flags), "fallback"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        body = "\n".join(_line(f) for f in flags)
        if (extra_notes or "").strip():
            body += "\n\nAdditional notes from the inspector (fold these in where they belong):\n" + extra_notes.strip()
        msg = client.messages.create(
            model=os.environ.get("PUNCHLIST_MODEL", "claude-sonnet-4-6"),
            max_tokens=6000, system=SYSTEM,
            messages=[{"role": "user", "content": body}],
        )
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if txt.startswith("```"):
            txt = txt.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(txt)
        if not data.get("sections"):
            raise ValueError("no sections")
        return data, "claude"
    except Exception as e:
        print("makeready structuring error, using fallback:", e)
        return _fallback(flags), "fallback"


def make_spec(address, flags, interior_photos, exterior_photos,
              extra_notes="", inspector="", access=""):
    """photos: [(abs_path, caption)] already split by zone."""
    data, mode = structure(flags, extra_notes)
    by = {s["name"]: s for s in data["sections"]}
    for zname, photos in (("Interior", interior_photos), ("Exterior", exterior_photos)):
        if photos and zname not in by:
            s = {"name": zname, "subsections": []}
            data["sections"].append(s); by[zname] = s
        if zname in by:
            by[zname]["photos"] = photos
    today = datetime.date.today().strftime("%m-%d-%Y")
    sub = "Doss & Spaulding Properties  |  %s" % today
    if inspector:
        sub += "  |  Inspected by %s" % inspector
    spec = {"title": "%s — Unit Turn Punchlist" % address,
            "subtitle": sub,
            "sections": data["sections"]}
    if access:
        spec["access"] = access
    return spec, mode
