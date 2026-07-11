import os, json, base64, io, uuid, tempfile
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from flask import Blueprint, request, jsonify, render_template, send_file, abort
from werkzeug.utils import secure_filename

bp = Blueprint("contracts", __name__, url_prefix="/contracts", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))
JOBS = os.environ.get("CONTRACT_TMP", os.path.join(tempfile.gettempdir(), "contract_jobs"))
os.makedirs(JOBS, exist_ok=True)
MODEL = os.getenv("CONTRACT_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

META = {"name": "Contract Term Extractor", "desc": "Upload a lease or management agreement; pull out fees, dates, and filled-in terms.",
        "url": "/contracts/", "group": "Leasing & Contracts", "icon": "\U0001F4C4", "ready": True}

SYSTEM = """You are a contract analyst for Doss & Spaulding Properties, a property management company.
You receive a property management agreement (PMA) or a residential lease, possibly as a PDF, Word text, or photos/scans.
Extract the key terms. Pay SPECIAL attention to:
1) Values written or typed into blank fields (names, amounts, dates, checkboxes, hand-filled entries).
2) All fees and money amounts (management fee %, leasing/placement fee, monthly rent, deposits, late fees, NSF fees, pet fees, renewal fees, admin fees, maintenance markups, early-termination fees, etc.).
3) All dates and deadlines (effective date, term start/end, renewal date, notice periods expressed as day counts, move-in, etc.).

Return STRICT JSON only, matching:
{
  "doc_type": "Property Management Agreement | Residential Lease | Other",
  "parties": [{"role": "", "name": ""}],
  "property": "",
  "term": "",
  "key_dates": [{"label": "", "date": "", "note": ""}],
  "fees": [{"label": "", "amount": "", "note": ""}],
  "filled_blanks": [{"field": "", "value": ""}],
  "other_terms": [{"label": "", "detail": ""}],
  "summary": ""
}
Rules:
- Only include information actually present. Do NOT invent or assume.
- If a value is unclear or illegible, still list it and add "(unclear)" in the note/value.
- Capture percentages, dollar amounts, and day counts exactly as written.
- "filled_blanks" is for anything entered into an otherwise blank line/field of a template.
- Keep "summary" to 2-4 plain sentences.
- Output ONLY the JSON object, no prose, no code fences."""

def _docx_text(path):
    from docx import Document
    d = Document(path); out = []
    for p in d.paragraphs:
        if p.text.strip(): out.append(p.text)
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells): out.append(" | ".join(cells))
    return "\n".join(out)[:120000]

def _img_block(fileobj):
    from PIL import Image, ImageOps
    im = Image.open(fileobj); im = ImageOps.exif_transpose(im); im.thumbnail((1600, 1600))
    if im.mode in ("RGBA", "P"): im = im.convert("RGB")
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode()}}

def _parse_json(raw):
    import json as _j
    raw = raw.strip()
    start = raw.find("{")
    if start > 0: raw = raw[start:]
    try:
        return _j.loads(raw)
    except Exception:
        pass
    # attempt to close a truncated object: cut at last complete item, balance braces/brackets
    cut = max(raw.rfind("}"), raw.rfind("]"))
    frag = raw[:cut+1] if cut > 0 else raw
    for _ in range(6):
        try:
            return _j.loads(frag)
        except Exception:
            # drop trailing incomplete fragment after the last comma, then re-balance
            c = frag.rfind(",")
            frag = frag[:c] if c > 0 else frag
            opens = frag.count("{") - frag.count("}")
            openb = frag.count("[") - frag.count("]")
            frag = frag + "]" * max(0, openb) + "}" * max(0, opens)
    return _j.loads(raw)  # re-raise original if unrecoverable

@bp.route("/")
def index():
    return render_template("contracts.html")

@bp.route("/extract", methods=["POST"])
def extract():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "Server has no ANTHROPIC_API_KEY set."}), 500
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify({"error": "Please upload a contract file."}), 400
    content = []
    for f in files:
        name = f.filename.lower()
        try:
            if name.endswith(".pdf"):
                data = f.read()
                content.append({"type": "document", "source": {"type": "base64",
                    "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
            elif name.endswith(".docx"):
                tmp = os.path.join(JOBS, "u_" + uuid.uuid4().hex[:8] + ".docx"); f.save(tmp)
                txt = _docx_text(tmp)
                try: os.remove(tmp)
                except OSError: pass
                content.append({"type": "text", "text": "[Word document contents]\n" + txt})
            else:  # image / scan / photo
                content.append(_img_block(f.stream))
        except Exception as e:
            return jsonify({"error": f"Could not read {f.filename}: {e}"}), 400
    content.append({"type": "text", "text": "Extract the terms from the contract above as specified."})
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                      messages=[{"role": "user", "content": content}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
        data = _parse_json(raw)
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {e}"}), 502
    job = uuid.uuid4().hex[:12]
    with open(os.path.join(JOBS, job + ".json"), "w") as fh:
        json.dump(data, fh)
    data["job"] = job
    return jsonify(data)

@bp.route("/download/<job>")
def download(job):
    job = secure_filename(job)
    jp = os.path.join(JOBS, job + ".json")
    if not os.path.exists(jp): abort(404)
    data = json.load(open(jp))
    pdf_path = os.path.join(JOBS, job + ".pdf")
    _build_pdf(data, pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name="Contract Summary.pdf")

def _build_pdf(data, out_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image as RLImage)
    ACCENT = colors.HexColor("#a78147"); SUB = colors.HexColor("#efe7d9"); DARK = colors.HexColor("#6b4f22")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, textColor=ACCENT, spaceAfter=2, alignment=0)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#666666"), spaceAfter=10)
    band = ParagraphStyle("band", parent=styles["Normal"], fontSize=11.5, textColor=colors.white, leftIndent=4, spaceBefore=4, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13)
    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6*inch, bottomMargin=0.6*inch,
                            leftMargin=0.7*inch, rightMargin=0.7*inch)
    el = []
    header_bits = []
    if os.path.exists(LOGO):
        try:
            img = RLImage(LOGO, width=1.7*inch, height=1.7*inch*303/1009)
            header_bits.append(img)
        except Exception: pass
    title_tbl = Table([[Paragraph("Contract Summary", h1), header_bits[0] if header_bits else ""]],
                      colWidths=[4.7*inch, 2.3*inch])
    title_tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("ALIGN", (1,0), (1,0), "RIGHT")]))
    el.append(title_tbl)
    el.append(Paragraph(f"Doss &amp; Spaulding Properties &nbsp;|&nbsp; {data.get('doc_type','Contract')}", sub))

    def band_row(txt):
        t = Table([[Paragraph(txt.upper(), band)]], colWidths=[7.1*inch])
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), ACCENT), ("LEFTPADDING",(0,0),(-1,-1),6),
                               ("TOPPADDING",(0,0),(-1,-1),3), ("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        return t

    def kv_table(rows, c0="Item", c1="Detail", w0=2.4):
        head = ParagraphStyle("th", parent=body, textColor=DARK, fontName="Helvetica-Bold", fontSize=9.5)
        d = [[Paragraph(c0, head), Paragraph(c1, head)]]
        for a, b in rows:
            d.append([Paragraph(str(a or ""), body), Paragraph(str(b or ""), body)])
        t = Table(d, colWidths=[w0*inch, (7.1-w0)*inch])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),SUB), ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#e6e0d6")),
                               ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),6),
                               ("RIGHTPADDING",(0,0),(-1,-1),6), ("TOPPADDING",(0,0),(-1,-1),3), ("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        return t

    def sp(h=8): return Spacer(1, h)

    if data.get("summary"):
        el += [sp(6), band_row("Summary"), sp(4), Paragraph(data["summary"], body)]
    if data.get("parties"):
        el += [sp(8), band_row("Parties"), sp(4), kv_table([(p.get("role"), p.get("name")) for p in data["parties"]], "Role", "Name")]
    prop_term = []
    if data.get("property"): prop_term.append(("Property", data["property"]))
    if data.get("term"): prop_term.append(("Term", data["term"]))
    if prop_term:
        el += [sp(8), band_row("Property & Term"), sp(4), kv_table(prop_term)]
    if data.get("key_dates"):
        el += [sp(8), band_row("Key Dates"), sp(4),
               kv_table([(d.get("label"), " ".join(x for x in [d.get("date"), ("— "+d["note"]) if d.get("note") else ""] if x)) for d in data["key_dates"]], "Date", "When / Note")]
    if data.get("fees"):
        el += [sp(8), band_row("Fees & Money"), sp(4),
               kv_table([(f.get("label"), " ".join(x for x in [str(f.get("amount") or ""), ("— "+f["note"]) if f.get("note") else ""] if x)) for f in data["fees"]], "Fee", "Amount / Note")]
    if data.get("filled_blanks"):
        el += [sp(8), band_row("Terms Filled Into Blanks"), sp(4),
               kv_table([(b.get("field"), b.get("value")) for b in data["filled_blanks"]], "Field", "Filled-in value")]
    if data.get("other_terms"):
        el += [sp(8), band_row("Other Key Terms"), sp(4),
               kv_table([(o.get("label"), o.get("detail")) for o in data["other_terms"]], "Term", "Detail")]
    el += [sp(14), Paragraph("<i>Auto-extracted for internal reference. Verify against the signed agreement before relying on any term.</i>",
                             ParagraphStyle("disc", parent=body, fontSize=8, textColor=colors.HexColor("#888888")))]
    doc.build(el)
    return out_path
