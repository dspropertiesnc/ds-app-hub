import os, uuid, shutil, tempfile, json
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from flask import Blueprint, request, jsonify, send_file, render_template, abort
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from . import structuring
from . import builder as B

bp = Blueprint("punchlist", __name__, url_prefix="/punchlist", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))
JOBS = os.environ.get("PUNCHLIST_TMP", os.path.join(tempfile.gettempdir(), "punchlist_jobs"))
os.makedirs(JOBS, exist_ok=True)

META = {"name": "Unit Turn Punchlist", "desc": "Turn a rough checklist + photos into a formatted punchlist (Word).",
        "url": "/punchlist/", "group": "Maintenance & Turns", "icon": "\U0001F9F0", "ready": True}

HEX = "0123456789abcdef"
def _safe_id(s):
    s = (s or "").lower()
    return s if s and all(c in HEX for c in s) and len(s) <= 40 else None

def _kind_dir(job, kind):
    kind = "checklist" if kind == "checklist" else "property"
    d = os.path.join(JOBS, job, kind); os.makedirs(d, exist_ok=True); return d

def _resize_save(fileobj, dst, box=1400, q=82):
    im = Image.open(fileobj); im = ImageOps.exif_transpose(im); im.thumbnail((box, box))
    if im.mode in ("RGBA", "P"): im = im.convert("RGB")
    im.save(dst, "JPEG", quality=q)

@bp.route("/")
def index():
    return render_template("punchlist.html")

@bp.route("/upload", methods=["POST"])
def upload():
    job = _safe_id(request.form.get("job"))
    kind = request.form.get("kind", "property")
    if not job: return jsonify({"error": "bad job"}), 400
    f = request.files.get("photo")
    if not f or not f.filename: return jsonify({"error": "no file"}), 400
    pid = uuid.uuid4().hex[:12]
    dst = os.path.join(_kind_dir(job, kind), pid + ".jpg")
    try: _resize_save(f.stream, dst)
    except Exception as e: return jsonify({"error": "bad image: %s" % e}), 400
    return jsonify({"id": pid})

@bp.route("/photo/<job>/<kind>/<pid>")
def photo(job, kind, pid):
    job = _safe_id(job); pid = _safe_id(pid)
    if not job or not pid: abort(404)
    path = os.path.join(_kind_dir(job, kind), pid + ".jpg")
    if not os.path.exists(path): abort(404)
    return send_file(path, mimetype="image/jpeg")

@bp.route("/generate", methods=["POST"])
def generate():
    job = _safe_id(request.form.get("job"))
    if not job: return jsonify({"error": "bad job"}), 400
    address = (request.form.get("address") or "Property").strip()
    checklist = (request.form.get("checklist") or "").strip()
    try:
        manifest = json.loads(request.form.get("manifest") or "{}")
    except Exception:
        manifest = {}
    prop = manifest.get("property", [])          # [{id, tag}]
    cl = manifest.get("checklist", [])           # [id]
    if not checklist and not cl:
        return jsonify({"error": "Type a checklist or add a photo of one."}), 400
    pdir = _kind_dir(job, "property"); cdir = _kind_dir(job, "checklist")
    interior, exterior = [], []
    for it in prop:
        pid = _safe_id(it.get("id")); tag = it.get("tag")
        if not pid: continue
        fn = pid + ".jpg"
        if not os.path.exists(os.path.join(pdir, fn)): continue
        (exterior if tag == "exterior" else interior).append(fn)
    checklist_images = []
    for cid in cl:
        cid = _safe_id(cid)
        if not cid: continue
        p = os.path.join(cdir, cid + ".jpg")
        if os.path.exists(p): checklist_images.append(p)
    spec, mode = structuring.make_spec(address, checklist, interior, exterior, checklist_images=checklist_images)
    safe = secure_filename(address) or "punchlist"
    docx_path = os.path.join(JOBS, job, f"{safe} Punchlist.docx")
    B.build(spec, docx_path, photo_dir=pdir, logo_path=LOGO)
    return jsonify({"job": job, "mode": mode, "docx": True, "pdf": False,
                    "sections": [{"name": s["name"],
                                  "subs": [{"name": ss["name"], "count": len(ss.get("items", []))} for ss in s.get("subsections", [])],
                                  "photos": len(s.get("photos", []))} for s in spec["sections"]]})

@bp.route("/download/<job>/<fmt>")
def download(job, fmt):
    job = _safe_id(job)
    if not job: return "Not found", 404
    jd = os.path.join(JOBS, job)
    if not os.path.isdir(jd): return "Not found", 404
    for fn in os.listdir(jd):
        if fmt == "docx" and fn.endswith(".docx"):
            return send_file(os.path.join(jd, fn), as_attachment=True)
    return "Not found", 404
