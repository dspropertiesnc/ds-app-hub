import os, uuid, shutil, tempfile
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from flask import Blueprint, request, jsonify, send_file, render_template
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
        "url": "/punchlist/", "group": "Maintenance & Turns", "icon": "🧰", "ready": True}

def _resize(src, dst, box=1100, q=82):
    im = Image.open(src); im = ImageOps.exif_transpose(im); im.thumbnail((box, box))
    if im.mode in ("RGBA", "P"): im = im.convert("RGB")
    im.save(dst, "JPEG", quality=q)

@bp.route("/")
def index():
    return render_template("punchlist.html")

@bp.route("/generate", methods=["POST"])
def generate():
    address = (request.form.get("address") or "Property").strip()
    checklist = (request.form.get("checklist") or "").strip()
    cl_files = [f for f in request.files.getlist("checklist_images") if f and f.filename]
    if not checklist and not cl_files:
        return jsonify({"error": "Type a checklist or add a photo of one."}), 400
    job = uuid.uuid4().hex[:10]; jd = os.path.join(JOBS, job)
    pdir = os.path.join(jd, "photos"); cdir = os.path.join(jd, "checklist")
    os.makedirs(pdir, exist_ok=True); os.makedirs(cdir, exist_ok=True)
    checklist_images = []
    for i, f in enumerate(cl_files):
        nm = secure_filename(f.filename) or f"cl_{i}.jpg"
        dst = os.path.join(cdir, nm); f.save(dst); checklist_images.append(dst)
    interior, exterior = [], []
    files = request.files.getlist("photos"); tags = request.form.getlist("tags")
    for i, f in enumerate(files):
        if not f or not f.filename: continue
        name = secure_filename(f.filename) or f"photo_{i}.jpg"
        raw = os.path.join(pdir, "_raw_" + name); f.save(raw)
        out = os.path.join(pdir, os.path.splitext(name)[0] + ".jpg")
        try: _resize(raw, out)
        except Exception: shutil.copy(raw, out)
        try: os.remove(raw)
        except OSError: pass
        tag = tags[i] if i < len(tags) else "interior"
        (exterior if tag == "exterior" else interior).append(os.path.basename(out))
    spec, mode = structuring.make_spec(address, checklist, interior, exterior, checklist_images=checklist_images)
    safe = secure_filename(address) or "punchlist"
    docx_path = os.path.join(jd, f"{safe} Punchlist.docx")
    B.build(spec, docx_path, photo_dir=pdir, logo_path=LOGO)
    return jsonify({"job": job, "mode": mode, "docx": True, "pdf": False,
                    "sections": [{"name": s["name"],
                                  "subs": [{"name": ss["name"], "count": len(ss.get("items", []))} for ss in s.get("subsections", [])],
                                  "photos": len(s.get("photos", []))} for s in spec["sections"]]})

@bp.route("/download/<job>/<fmt>")
def download(job, fmt):
    jd = os.path.join(JOBS, secure_filename(job))
    if not os.path.isdir(jd): return "Not found", 404
    for fn in os.listdir(jd):
        if fmt == "docx" and fn.endswith(".docx"):
            return send_file(os.path.join(jd, fn), as_attachment=True)
    return "Not found", 404
