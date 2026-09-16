"""Make-Ready Inspection — guided walkthrough that produces a repair punchlist.

The punchlist tool is for someone who already knows what needs doing. This one
prompts item by item, so a less-experienced staff member can walk a property,
mark each item OK / Needs attention / N/A, add a note and a photo where it
matters, and have the app write the punchlist from what they flagged.
"""
import os, re, uuid, json, tempfile
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from flask import Blueprint, request, jsonify, send_file, render_template, abort
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from .. import mailer
from . import checklist as CL
from . import structuring
from ..punchlist import builder as B

bp = Blueprint("makeready", __name__, url_prefix="/makeready", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))
JOBS = os.environ.get("MAKEREADY_TMP", os.path.join(tempfile.gettempdir(), "makeready_jobs"))
os.makedirs(JOBS, exist_ok=True)

META = {"name": "Make-Ready Inspection", "desc": "Walk the property item by item, flag what needs attention, and get a repair punchlist.",
        "url": "/makeready/", "group": "Maintenance & Turns", "icon": "\U0001F4CB", "ready": True}

HEX = "0123456789abcdef"


def _safe_id(s):
    s = (s or "").lower()
    return s if s and all(c in HEX for c in s) and len(s) <= 40 else None


def _job_dir(job):
    d = os.path.join(JOBS, job, "photos")
    os.makedirs(d, exist_ok=True)
    return d


def _resize_save(fileobj, dst, box=1400, q=82):
    im = Image.open(fileobj); im = ImageOps.exif_transpose(im); im.thumbnail((box, box))
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    im.save(dst, "JPEG", quality=q)


@bp.route("/")
def index():
    return render_template("makeready.html", profile=CL.PROFILE)


@bp.route("/sections", methods=["POST"])
def sections():
    """Given the property profile, return the concrete walkthrough."""
    data = request.get_json(silent=True) or {}
    secs = CL.build(data.get("profile") or {})
    return jsonify({"sections": secs, "total": CL.total_items(secs)})


@bp.route("/upload", methods=["POST"])
def upload():
    job = _safe_id(request.form.get("job"))
    if not job:
        return jsonify({"error": "bad job"}), 400
    f = request.files.get("photo")
    if not f or not f.filename:
        return jsonify({"error": "no file"}), 400
    pid = uuid.uuid4().hex[:12]
    dst = os.path.join(_job_dir(job), pid + ".jpg")
    try:
        _resize_save(f.stream, dst)
    except Exception as e:
        return jsonify({"error": "bad image: %s" % e}), 400
    return jsonify({"id": pid})


@bp.route("/photo/<job>/<pid>")
def photo(job, pid):
    job = _safe_id(job); pid = _safe_id(pid)
    if not job or not pid:
        abort(404)
    path = os.path.join(_job_dir(job), pid + ".jpg")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")


@bp.route("/generate", methods=["POST"])
def generate():
    job = _safe_id(request.form.get("job"))
    if not job:
        return jsonify({"error": "bad job"}), 400
    address = (request.form.get("address") or "Property").strip()[:75]
    access = (request.form.get("access") or "").strip()[:100]
    inspector = (request.form.get("inspector") or "").strip()[:60]
    extra = (request.form.get("notes") or "").strip()[:2000]
    try:
        flags = json.loads(request.form.get("flags") or "[]")
    except Exception:
        flags = []
    if not isinstance(flags, list) or not flags:
        return jsonify({"error": "Nothing was flagged, so there is no punchlist to build. "
                                 "If the property really is ready, no document is needed."}), 400

    pdir = _job_dir(job)
    clean, interior_photos, exterior_photos = [], [], []
    for f in flags:
        if not isinstance(f, dict):
            continue
        zone = "Exterior" if f.get("zone") == "Exterior" else "Interior"
        room = (f.get("room") or "General").strip()[:80]
        label = (f.get("label") or "").strip()[:160]
        note = (f.get("note") or "").strip()[:600]
        if not label:
            continue
        clean.append({"zone": zone, "room": room, "label": label, "note": note})
        for pid in (f.get("photos") or [])[:8]:
            pid = _safe_id(pid)
            if not pid:
                continue
            path = os.path.join(pdir, pid + ".jpg")
            if not os.path.exists(path):
                continue
            caption = "%s — %s" % (room, label)
            (exterior_photos if zone == "Exterior" else interior_photos).append((path, caption))

    if not clean:
        return jsonify({"error": "Nothing was flagged, so there is no punchlist to build."}), 400

    spec, mode = structuring.make_spec(address, clean, interior_photos, exterior_photos,
                                       extra_notes=extra, inspector=inspector, access=access)
    jd = os.path.join(JOBS, job)
    safe = secure_filename(address) or "punchlist"
    docx_path = os.path.join(jd, "%s Punchlist.docx" % safe)
    B.build(spec, docx_path, photo_dir=pdir, logo_path=LOGO)
    try:
        with open(os.path.join(jd, "meta.json"), "w") as fh:
            json.dump({"address": address}, fh)
    except Exception:
        pass
    return jsonify({"job": job, "mode": mode,
                    "flagged": len(clean),
                    "photos": len(interior_photos) + len(exterior_photos),
                    "sections": [{"name": s["name"],
                                  "subs": [{"name": ss["name"], "count": len(ss.get("items", []))}
                                           for ss in s.get("subsections", [])],
                                  "photos": len(s.get("photos", []))} for s in spec["sections"]]})


def _valid_email(e):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (e or "").strip()))


EMAIL_TARGETS = {
    "info": ["info@dspropertiesnc.com"],
    "admin": ["admin@dspropertiesnc.com"],
    "john": ["john@dspropertiesnc.com"],
    "alina": ["alina@dspropertiesnc.com"],
}


@bp.route("/email", methods=["POST"])
def email():
    job = _safe_id(request.form.get("job"))
    target = request.form.get("target")
    if target == "custom":
        to = (request.form.get("to") or "").strip()
        if not _valid_email(to):
            return jsonify({"error": "Enter a valid email address."}), 400
        recipients = [to]
    else:
        recipients = EMAIL_TARGETS.get(target)
    if not job or not recipients:
        return jsonify({"error": "Bad request."}), 400
    jd = os.path.join(JOBS, job)
    if not os.path.isdir(jd):
        return jsonify({"error": "Punchlist not found. Generate it again."}), 404
    docx = next((os.path.join(jd, fn) for fn in os.listdir(jd) if fn.endswith(".docx")), None)
    if not docx:
        return jsonify({"error": "Punchlist file not found."}), 404
    address = (request.form.get("address") or "").strip()[:75]
    if not address:
        try:
            address = json.load(open(os.path.join(jd, "meta.json"))).get("address") or ""
        except Exception:
            address = ""
    address = address or "the property"
    inspector = (request.form.get("inspector") or "").strip()[:60]
    body = "Attached is the unit turn punchlist for %s, built from a make-ready inspection%s.\n\n" \
           "Generated via the Doss & Spaulding tools hub." % (
               address, (" by %s" % inspector) if inspector else "")
    try:
        mailer.send(recipients, "Unit Turn Punchlist — %s" % address, body, docx,
                    from_addr=os.getenv("PUNCHLIST_FROM") or os.getenv("SMTP_FROM"))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "sent_to": recipients})


@bp.route("/download/<job>/<fmt>")
def download(job, fmt):
    job = _safe_id(job)
    if not job:
        return "Not found", 404
    jd = os.path.join(JOBS, job)
    if not os.path.isdir(jd):
        return "Not found", 404
    for fn in os.listdir(jd):
        if fmt == "docx" and fn.endswith(".docx"):
            return send_file(os.path.join(jd, fn), as_attachment=True)
    return "Not found", 404
