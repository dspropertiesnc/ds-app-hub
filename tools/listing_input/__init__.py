import os, re, json, uuid, tempfile, datetime
from flask import Blueprint, request, jsonify, render_template, send_file, abort
from werkzeug.utils import secure_filename
from .fields import SECTIONS, all_fields, required_keys
from . import builder
from .. import mailer

bp = Blueprint("listing_input", __name__, url_prefix="/listing-input", template_folder="templates")

JOBS = os.environ.get("LISTING_TMP", os.path.join(tempfile.gettempdir(), "listing_input_jobs"))
os.makedirs(JOBS, exist_ok=True)
FROM_ADDR = os.getenv("LISTING_FROM", "listing-input@dspropertiesnc.com")

META = {"name": "Listing Input Sheet",
        "desc": "Capture property details in the field and send them to admin for MLS / Rentvine entry.",
        "url": "/listing-input/", "group": "Marketing", "icon": "\U0001F4CB", "ready": True}

EMAIL_TARGETS = {
    "admin": ["admin@dspropertiesnc.com"],
    "support": ["support@dspropertiesnc.com"],
    "info": ["info@dspropertiesnc.com"],
}

def _valid_email(e):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (e or "").strip()))

def _collect(form):
    values, missing = {}, []
    for _, f in all_fields():
        k = f["k"]
        if f["t"] == "multi":
            v = [x for x in form.getlist(k) if str(x).strip()]
        else:
            v = (form.get(k) or "").strip()
        if v:
            values[k] = v
        elif f.get("req"):
            missing.append(f["l"])
    # drop values for fields whose condition isn't met (mirrors the form's show/hide)
    for _, f in all_fields():
        dep = f.get("dep")
        if not dep:
            continue
        parent = values.get(dep["f"])
        if isinstance(parent, list):
            parent = parent[0] if parent else ""
        parent = str(parent or "")
        ok = True
        if "eq" in dep:
            ok = (parent == dep["eq"])
        elif "in" in dep:
            ok = (parent in dep["in"])
        elif "gt" in dep:
            try: ok = float(parent or 0) > dep["gt"]
            except ValueError: ok = False
        if not ok:
            values.pop(f["k"], None)

    # normalize the ShowMojo serial to ###-##-###; flag it if it doesn't fit
    sm = values.get("showmojo")
    if sm:
        digits = re.sub(r"\D", "", sm)
        if len(digits) == 8:
            values["showmojo"] = "%s-%s-%s" % (digits[:3], digits[3:5], digits[5:])
        else:
            values["showmojo"] = "%s  (check format — expected ###-##-###)" % sm
    values["_date"] = datetime.date.today().strftime("%B %d, %Y")
    return values, missing

@bp.route("/")
def index():
    return render_template("listing_input.html", sections=SECTIONS)

@bp.route("/submit", methods=["POST"])
def submit():
    values, missing = _collect(request.form)
    if not (values.get("street_no") or values.get("street_name")):
        return jsonify({"error": "Enter at least the street number and name."}), 400
    job = uuid.uuid4().hex[:12]
    jd = os.path.join(JOBS, job); os.makedirs(jd, exist_ok=True)
    addr = builder.address_line(values) or "New listing"
    safe = re.sub(r'[\\/:*?"<>|\r\n]+', " ", addr)[:80].strip()
    pdf_path = os.path.join(jd, "Listing Input Sheet - %s.pdf" % safe)
    try:
        builder.build_pdf(values, pdf_path, missing_required=missing)
    except Exception as e:
        return jsonify({"error": "Could not build the sheet: %s" % e}), 500
    with open(os.path.join(jd, "values.json"), "w") as fh:
        json.dump(values, fh)
    return jsonify({"job": job, "address": addr, "missing": missing,
                    "filled": sum(1 for k in values if not k.startswith("_"))})

@bp.route("/download/<job>")
def download(job):
    jd = os.path.join(JOBS, secure_filename(job))
    if not os.path.isdir(jd): abort(404)
    pdf = next((os.path.join(jd, f) for f in os.listdir(jd) if f.endswith(".pdf")), None)
    if not pdf: abort(404)
    return send_file(pdf, as_attachment=True, download_name=os.path.basename(pdf))

@bp.route("/email", methods=["POST"])
def email():
    job = secure_filename(request.form.get("job") or "")
    target = request.form.get("target")
    if target == "custom":
        to = (request.form.get("to") or "").strip()
        if not _valid_email(to):
            return jsonify({"error": "Enter a valid email address."}), 400
        recipients = [to]
    else:
        recipients = EMAIL_TARGETS.get(target)
    jd = os.path.join(JOBS, job)
    if not job or not recipients or not os.path.isdir(jd):
        return jsonify({"error": "Bad request."}), 400
    pdf = next((os.path.join(jd, f) for f in os.listdir(jd) if f.endswith(".pdf")), None)
    if not pdf:
        return jsonify({"error": "Sheet not found. Please submit it again."}), 404
    try:
        values = json.load(open(os.path.join(jd, "values.json")))
    except Exception:
        values = {}
    addr = builder.address_line(values) or "New listing"
    body = builder.text_summary(values) + \
        "\n\nSent from the Doss & Spaulding Listing Input Sheet tool. PDF attached."
    try:
        mailer.send(recipients, "Listing Input Sheet — %s" % addr, body, pdf,
                    from_addr=FROM_ADDR, mime=("application", "pdf"))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "sent_to": recipients, "from": FROM_ADDR})
