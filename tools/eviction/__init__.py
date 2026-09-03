import os, io, json, uuid, base64, tempfile, re
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from flask import Blueprint, request, jsonify, render_template, send_file, abort
from werkzeug.utils import secure_filename
from . import builder, casecalc

bp = Blueprint("eviction", __name__, url_prefix="/eviction", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.environ.get("EVICTION_TMP", os.path.join(tempfile.gettempdir(), "eviction_jobs"))
os.makedirs(JOBS, exist_ok=True)
MODEL = os.getenv("EVICTION_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

META = {"name": "Eviction Prep Packet",
        "desc": "Upload the case documents; get a courtroom quick-reference card and full prep binder.",
        "url": "/eviction/", "group": "Leasing & Contracts", "icon": "⚖️", "ready": True}

DEFAULT_FIRM = {
    "name": "Doss & Spaulding Properties LLC", "license": "C39183",
    "managerName": "John Doss", "managerLicense": "342080",
    "phone": "(336) 494-1710", "email": "info@dspropertiesnc.com",
}

SYSTEM = """You extract the facts for a North Carolina summary ejectment (eviction) court-prep packet.
You receive case documents: lease (often NCAR 410-T) + addenda, Complaint in Summary Ejectment (AOC-CVM-201),
Magistrate Summons (AOC-CVM-100) including the sheriff's RETURN OF SERVICE, SCRA declaration (AOC-G-250),
the tenant ledger, and a late-rent / Notice & Demand for Possession.

Return STRICT JSON only, in this shape (omit any field you cannot find - do NOT invent values):
{
 "landlord": {"name": "", "address": "", "article": "the |"},
 "tenant": {"name": "", "phone": ""},
 "property": {"address": "", "county": "", "type": ""},
 "court": {"division": "", "fileNo": "", "countyCourt": "", "hearingDate": "", "hearingTime": "",
           "arriveTime": "", "courthouse": "", "courthouseShort": "", "room": "", "clerkLine": ""},
 "tenancy": {"moveIn": "", "leaseForm": "", "leaseSignedDate": "", "term": "",
             "para_noNotice": "", "para_immediateBreach": "", "para_lateFee": "", "para_partialRent": "",
             "militaryAddendum": ""},
 "rent": {"monthly": 0, "dueDayText": "the 1st", "lateFee": 0, "lateFeeNote": ""},
 "claim": {"rentMonthLabel": "", "rentDueDate": "MM-DD-YYYY", "daysInMonth": 0, "proratedDays": 0},
 "ledger": {"asOf": "", "balance": 0,
            "rows": [{"date": "MM-DD-YYYY", "item": "", "amount": 0,
                      "type": "charge|payment", "kind": "rent|fee|cost"}]},
 "courtCosts": [{"label": "", "amount": 0}],
 "demand": {"sentDate": "", "payByDate": "", "form": ""},
 "filing": {"filedDate": "", "complaintForm": "", "summonsForm": ""},
 "service": {"method": ""},
 "exhibits": [{"label": "A", "document": "", "why": ""}]
}

CRITICAL RULES:
- LEDGER: transcribe EVERY row. Mark each row "type":"charge" or "type":"payment". Payments/credits are
  "payment" (a negative amount also means a payment). Classify each charge "kind": "rent" for rent, "fee" for late/admin/
  waiver/pet fees, "cost" for court costs. Getting payments right is essential - the money ask depends on it.
- landlord.article: "the " if the landlord is a trust/entity ("the Smith Family Trust"); "" for an individual person.
- claim.rentDueDate: the due date of the rent month being sued on, as MM-DD-YYYY.
- claim.daysInMonth: calendar days in that rent month.
- claim.proratedDays: days from the rent due date THROUGH the hearing date, inclusive.
- courtCosts: this case's filing fee, legal/filing costs, sheriff service fee (from the ledger/complaint).
- service.method: read the sheriff's RETURN on the summons - state personal service vs. posting, with the
  date. This controls whether a money judgment is available. If unclear, say so plainly.
- Read documents visually; do not guess at checkbox selections or handwritten entries.
- Money values are plain numbers (1800.00), not strings with $ or commas.
Output ONLY the JSON object, no prose, no code fences."""

def _parse_json(raw):
    raw = (raw or "").strip()
    i = raw.find("{")
    if i > 0:
        raw = raw[i:]
    try:
        return json.loads(raw)
    except Exception:
        pass
    cut = max(raw.rfind("}"), raw.rfind("]"))
    frag = raw[:cut + 1] if cut > 0 else raw
    for _ in range(6):
        try:
            return json.loads(frag)
        except Exception:
            c = frag.rfind(",")
            frag = frag[:c] if c > 0 else frag
            frag += "]" * max(0, frag.count("[") - frag.count("]"))
            frag += "}" * max(0, frag.count("{") - frag.count("}"))
    return json.loads(raw)

def _img_block(fileobj):
    from PIL import Image, ImageOps
    im = Image.open(fileobj); im = ImageOps.exif_transpose(im); im.thumbnail((1600, 1600))
    if im.mode in ("RGBA", "P"): im = im.convert("RGB")
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode()}}

def _docx_text(path):
    from docx import Document as D
    d = D(path); out = []
    for p in d.paragraphs:
        if p.text.strip(): out.append(p.text)
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells): out.append(" | ".join(cells))
    return "\n".join(out)[:120000]

@bp.route("/")
def index():
    return render_template("eviction.html", firm=DEFAULT_FIRM)

@bp.route("/build", methods=["POST"])
def build():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "Server has no ANTHROPIC_API_KEY set."}), 500
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify({"error": "Please upload the case documents."}), 400
    media = []
    for f in files:
        name = f.filename.lower()
        try:
            if name.endswith(".pdf"):
                data = f.read()
                media.append({"type": "document", "source": {"type": "base64",
                    "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
                del data
            elif name.endswith(".docx"):
                tmp = os.path.join(JOBS, "u_" + uuid.uuid4().hex[:8] + ".docx"); f.save(tmp)
                txt = _docx_text(tmp)
                try: os.remove(tmp)
                except OSError: pass
                media.append({"type": "text", "text": "[Word document: %s]\n%s" % (f.filename, txt)})
            else:
                media.append(_img_block(f.stream))
        except Exception as e:
            return jsonify({"error": "Could not read %s: %s" % (f.filename, e)}), 400
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                      messages=[{"role": "user", "content": media + [
                                          {"type": "text", "text": "Extract the case facts as specified."}]}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
        case = _parse_json(raw)
    except Exception as e:
        return jsonify({"error": "Extraction failed: %s" % e}), 502
    media = None

    # firm details from the form (prefilled + editable)
    firm = dict(DEFAULT_FIRM)
    for k in ("name", "license", "managerName", "managerLicense", "phone", "email"):
        v = (request.form.get("firm_" + k) or "").strip()
        if v: firm[k] = v
    case["firm"] = firm
    bg = (request.form.get("background") or "").strip()
    if bg:
        case["background"] = bg[:1200]

    job = uuid.uuid4().hex[:12]
    jd = os.path.join(JOBS, job); os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "case.json"), "w") as fh:
        json.dump(case, fh)
    try:
        builder.build_quickref(case, os.path.join(jd, "Court QuickRef.docx"))
        builder.build_packet(case, os.path.join(jd, "Court Prep Packet.docx"))
    except Exception as e:
        return jsonify({"error": "Could not build the documents: %s" % e}), 500

    d = casecalc.compute(case)
    return jsonify({
        "job": job,
        "tenant": (case.get("tenant") or {}).get("name", ""),
        "property": (case.get("property") or {}).get("address", ""),
        "hearing": "%s %s" % ((case.get("court") or {}).get("hearingDate", ""),
                              (case.get("court") or {}).get("hearingTime", "")),
        "fileNo": (case.get("court") or {}).get("fileNo", ""),
        "service": (case.get("service") or {}).get("method", ""),
        "rent_ask": d["PRO"], "costs": d["COSTS"], "total": d["TOTAL"],
        "month_ask": d["MONTHASK"], "charged": d["CHARGED"],
        "accrued": d["ACCRUED"], "daily": d["D"], "prorated_days": d["prorated_days"],
        "paid_toward_rent": casecalc.money(d["current_paid"]) if d["current_paid"] else "",
        "prior_unpaid": casecalc.money(d["prior_rent_unpaid"]) if d["prior_rent_unpaid"] else "",
        "fees_excluded": casecalc.money(d["fees_outstanding"]) if d["fees_outstanding"] else "",
        "allocations": [{"date": a["payment_date"], "amount": casecalc.money(a["amount"]),
                         "to": a["applied_to"]} for a in d["allocations"]],
        "unapplied": casecalc.money(d["unapplied"]) if d["unapplied"] else "",
        "mismatch": d["mismatch"] or "",
    })

@bp.route("/download/<job>/<which>")
def download(job, which):
    job = secure_filename(job)
    jd = os.path.join(JOBS, job)
    if not os.path.isdir(jd): abort(404)
    fn = "Court QuickRef.docx" if which == "quickref" else "Court Prep Packet.docx"
    path = os.path.join(jd, fn)
    if not os.path.exists(path): abort(404)
    try:
        case = json.load(open(os.path.join(jd, "case.json")))
        who = (case.get("tenant") or {}).get("name", "") or "Case"
        last = str(who).split(" ")[-1]
        label = "Quick Reference" if which == "quickref" else "Prep Packet"
        nice = "Eviction %s - %s.docx" % (label, last)
        nice = re.sub(r'[\\/:*?"<>|\r\n]+', " ", nice)
    except Exception:
        nice = fn
    return send_file(path, as_attachment=True, download_name=nice)
