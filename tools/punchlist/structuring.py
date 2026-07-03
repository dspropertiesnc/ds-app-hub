"""Turns a raw checklist (typed text and/or photos of a checklist) into the
structured punchlist spec: grouped by Interior/Exterior -> room/trade
subsections, cleaned wording, clarifying notes, and 'completed' flags.
Uses the Anthropic API when ANTHROPIC_API_KEY is set; otherwise a simple parser
handles typed text (images require the API)."""
import os, json, datetime, base64, io
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass


SYSTEM = """You organize property unit-turn punchlists for a property manager.
You receive a rough checklist as typed text and/or as photos of a written or
on-screen checklist. Read everything and return STRICT JSON only, matching:

{
  "sections": [
    {"name": "Interior", "subsections": [
        {"name": "<room or trade group>", "items": [
            {"task": "<clean, clear instruction>", "note": "<optional clarification, else omit>", "done": <true only if the text says it was already completed>}
        ]}
    ]},
    {"name": "Exterior", "subsections": [ ... ]}
  ]
}

RULES:
- Transcribe items from the photos of the checklist exactly, then clean them up.
- Split every item into Interior or Exterior based on where the work is.
- Within each section, group items into logical room/trade subsections, e.g. Interior:
  "Walls & Paint", "Doors", "Windows & Blinds", "Electrical & Fixtures", "Bathrooms",
  "Kitchen", "Flooring", "Cleanout & General"; Exterior: "Landscaping",
  "Debris & Item Removal", "Structure & Exterior". Only include subsections that have items.
- Rewrite shorthand into clear, complete task sentences a handyman can act on.
- PRESERVE all specific locations, counts, and measurements exactly. Never invent specifics.
- If something is cut off, ambiguous, or unreadable, keep it and add a "note" flagging it.
- Set "done": true ONLY when it clearly says it was already handled/completed.
- Do not add tasks that are not in the input. Do not include a materials list.
- Output ONLY the JSON object, no prose, no code fences."""

def _img_block(path):
    from PIL import Image, ImageOps
    im=Image.open(path); im=ImageOps.exif_transpose(im); im.thumbnail((1500,1500))
    if im.mode in ("RGBA","P"): im=im.convert("RGB")
    buf=io.BytesIO(); im.save(buf,"JPEG",quality=80)
    data=base64.b64encode(buf.getvalue()).decode()
    return {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":data}}

def _fallback(raw):
    interior, exterior = [], []
    ext_kw = ("yard","lawn","weed","vine","mulch","pine","exterior","outside","crawlspace",
              "gutter","siding","brick","bush","shrub","tree","landscap","backyard","patio",
              "downspout","foundation","soffit","fascia","driveway")
    for line in (raw or "").splitlines():
        t=line.strip(" -\t*•")
        if not t: continue
        done = any(k in t.lower() for k in ("completed","done already","already done"))
        it={"task":t[0].upper()+t[1:]}
        if done: it["done"]=True
        (exterior if any(k in t.lower() for k in ext_kw) else interior).append(it)
    secs=[]
    if interior: secs.append({"name":"Interior","subsections":[{"name":"General","items":interior}]})
    if exterior: secs.append({"name":"Exterior","subsections":[{"name":"General","items":exterior}]})
    if not secs: secs.append({"name":"Interior","subsections":[{"name":"General","items":[]}]})
    return {"sections":secs}

def structure_checklist(raw_text, image_paths=None):
    key=os.environ.get("ANTHROPIC_API_KEY")
    image_paths=image_paths or []
    if not key:
        return _fallback(raw_text), "fallback"
    try:
        import anthropic
        client=anthropic.Anthropic(api_key=key)
        content=[]
        for p in image_paths:
            try: content.append(_img_block(p))
            except Exception as e: print("img block failed",p,e)
        user_text=raw_text.strip() if raw_text else ""
        if image_paths and not user_text:
            user_text="Transcribe and organize the checklist shown in the image(s) above."
        elif image_paths:
            user_text="Typed notes:\n"+user_text+"\n\nAlso include everything from the checklist photo(s) above."
        content.append({"type":"text","text":user_text or "(no input)"})
        msg=client.messages.create(
            model=os.environ.get("PUNCHLIST_MODEL","claude-sonnet-4-6"),
            max_tokens=4000, system=SYSTEM,
            messages=[{"role":"user","content":content}],
        )
        txt="".join(b.text for b in msg.content if getattr(b,"type","")=="text").strip()
        if txt.startswith("```"): txt=txt.strip("`").split("\n",1)[1].rsplit("```",1)[0]
        return json.loads(txt), "claude"
    except Exception as e:
        print("structuring error, using fallback:",e)
        return _fallback(raw_text), "fallback"

def make_spec(address, raw_text, interior_photos, exterior_photos, checklist_images=None):
    data,mode=structure_checklist(raw_text, checklist_images)
    by={s["name"]:s for s in data["sections"]}
    if interior_photos and "Interior" not in by:
        s={"name":"Interior","subsections":[]}; data["sections"].append(s); by["Interior"]=s
    if exterior_photos and "Exterior" not in by:
        s={"name":"Exterior","subsections":[]}; data["sections"].append(s); by["Exterior"]=s
    if "Interior" in by: by["Interior"]["photos"]=interior_photos
    if "Exterior" in by: by["Exterior"]["photos"]=exterior_photos
    today=datetime.date.today().strftime("%m-%d-%Y")
    spec={"title":f"{address} — Unit Turn Punchlist",
          "subtitle":f"Doss & Spaulding Properties  |  {today}",
          "sections":data["sections"]}
    return spec,mode
