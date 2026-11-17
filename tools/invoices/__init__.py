"""Invoice Generator (/invoices/).

Makes a branded invoice PDF to upload to a Rentvine bill, mainly for vendors who can't send us one.
Type a Rentvine bill # to fill in the vendor, line items, work order, service address, tenant, owner
and paid date; fix or add anything by hand. Also works with no bill at all (manual entry) for work
outside Rentvine. Every invoice is saved and can be reopened, edited and re-downloaded.
"""
import os, re, json, shutil, datetime, tempfile
from flask import Blueprint, request, jsonify, render_template, send_file, abort
from werkzeug.utils import secure_filename
from . import rv, store, builder

try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass

bp = Blueprint("invoices", __name__, url_prefix="/invoices", template_folder="templates")

META = {"name": "Invoice Generator",
        "desc": "Pull a bill from Rentvine (or type it in) and make a PAID or open invoice PDF to upload to the bill.",
        "url": "/invoices/", "group": "Accounting", "icon": "\U0001F9FE", "ready": True}

PHOTOS = os.path.join(os.path.dirname(store.DB_PATH) or tempfile.gettempdir(), "invoice_photos")
TMP = os.path.join(tempfile.gettempdir(), "invoice_pdfs")
os.makedirs(TMP, exist_ok=True)
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp")
METHODS = ("", "ACH", "Check", "Cash", "Card", "Zelle", "Rentvine payout")

store.init()


def _num(v):
    try:
        return round(float(str(v).replace(",", "").replace("$", "")), 2)
    except (TypeError, ValueError):
        return None


def _date(v):
    v = (v or "").strip()[:10]
    try:
        datetime.date.fromisoformat(v)
        return v
    except ValueError:
        return ""


def _s(d, k, n=200):
    return str(d.get(k) or "").strip()[:n]


def _clean(d):
    """Keep only expected fields; returns (doc, errors)."""
    errs = []
    v = d.get("vendor") or {}
    s = d.get("service") or {}
    items = []
    for i in (d.get("items") or [])[:40]:
        desc, rate = _s(i, "description", 500), _num(i.get("rate"))
        qty = _num(i.get("qty")) or 1
        if not desc and rate is None:
            continue
        if rate is None:
            errs.append("Every line needs an amount.")
            continue
        items.append({"description": desc, "qty": qty, "rate": rate})
    doc = {
        "id": _s(d, "id", 20) or None,
        "number": _s(d, "number", 40),
        "bill_id": re.sub(r"\D", "", str(d.get("bill_id") or ""))[:12],
        "wo_number": re.sub(r"\D", "", str(d.get("wo_number") or ""))[:12],
        "service_date": _date(d.get("service_date")),
        "due_date": _date(d.get("due_date")),
        "paid": bool(d.get("paid")),
        "paid_date": _date(d.get("paid_date")),
        "paid_method": _s(d, "paid_method", 40),
        "notes": _s(d, "notes", 1000),
        "vendor": dict({k: _s(v, k) for k in ("name", "address", "city_line", "phone", "email", "rentvine_id")},
                       authorized=bool(v.get("authorized"))),
        "service": {k: _s(s, k) for k in ("address", "city_line", "tenant", "owner")},
        "items": items,
        "keep_photos": [secure_filename(x) for x in (d.get("keep_photos") or []) if isinstance(x, str)],
    }
    doc["total"] = round(sum(i["qty"] * i["rate"] for i in items), 2)
    if not doc["vendor"]["name"]:
        errs.append("Enter the vendor's name.")
    if not items:
        errs.append("Add at least one line item.")
    if not doc["vendor"]["authorized"]:
        errs.append("Confirm the vendor has asked us to prepare their invoices (checkbox under Vendor). "
                    "If they haven't, ask them for their own invoice instead.")
    if doc["paid"] and not doc["paid_date"]:
        errs.append("Enter the date it was paid (or switch to Unpaid).")
    if not doc["number"]:
        doc["number"] = store.next_number(doc["wo_number"], doc["service"]["address"], doc["id"])
    elif not store.number_free(doc["number"], doc["id"]):
        errs.append("Invoice # %s is already used. Clear it to get the next number." % doc["number"])
    return doc, sorted(set(errs), key=errs.index)


def _photo_dir(iid):
    return os.path.join(PHOTOS, secure_filename(iid))


def _photos(iid):
    d = _photo_dir(iid)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.lower().endswith(PHOTO_EXT))


# ---------- pages ----------
@bp.route("/")
def index():
    q = request.args.get("q", "")
    return render_template("invoices_list.html", rows=store.listing(q), q=q, persistent=store.persistent())


@bp.route("/new")
def new():
    return render_template("invoices_edit.html", iid="", rv=rv.configured(), methods=METHODS)


@bp.route("/i/<iid>")
def edit(iid):
    if not store.get(iid):
        abort(404)
    return render_template("invoices_edit.html", iid=iid, rv=rv.configured(), methods=METHODS)


# ---------- api ----------
@bp.route("/api/invoice/<iid>")
def api_get(iid):
    doc = store.get(iid)
    if not doc:
        abort(404)
    doc["photos"] = _photos(iid)
    return jsonify(doc)


@bp.route("/api/rentvine/bill/<int:bill_id>")
def api_bill(bill_id):
    try:
        return jsonify(rv.bill(bill_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/wo/<int:wo_id>")
def api_wo(wo_id):
    try:
        return jsonify(rv.work_order(wo_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/find")
def api_find():
    try:
        return jsonify({"results": rv.find(request.args.get("q", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/bill/<int:bill_id>/fields")
def api_bill_fields(bill_id):
    try:
        return jsonify(rv.bill_fields(bill_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/probe")
def api_probe():
    """Field names (no values) for a read-only Rentvine path, for setup checks."""
    params = {k: v for k, v in request.args.items() if k != "path"}
    try:
        return jsonify(rv.probe(request.args.get("path", ""), params))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/vendors")
def api_vendors():
    return jsonify(store.vendors())


@bp.route("/api/vendors/<vid>", methods=["DELETE"])
def api_vendor_delete(vid):
    store.delete_vendor(secure_filename(vid))
    return jsonify({"ok": True})


@bp.route("/api/next-number")
def api_next_number():
    return jsonify({"number": store.next_number(request.args.get("wo", ""), request.args.get("addr", ""),
                                                request.args.get("id") or None)})


@bp.route("/photo/<iid>/<name>")
def photo(iid, name):
    p = os.path.join(_photo_dir(iid), secure_filename(name))
    if not os.path.isfile(p):
        abort(404)
    return send_file(p, max_age=300)


@bp.route("/save", methods=["POST"])
def save():
    try:
        raw = json.loads(request.form.get("doc") or "{}")
    except ValueError:
        return jsonify({"error": "Bad request."}), 400
    doc, errs = _clean(raw)
    if errs:
        return jsonify({"error": " ".join(errs)}), 400
    keep = set(doc.pop("keep_photos"))
    doc = store.save(doc)
    iid = doc["id"]

    # photos: drop the ones removed in the editor, add the new uploads
    pdir = _photo_dir(iid)
    os.makedirs(pdir, exist_ok=True)
    for f in _photos(iid):
        if f not in keep:
            os.remove(os.path.join(pdir, f))
    n = len(_photos(iid))
    for up in request.files.getlist("photos")[:24]:
        ext = os.path.splitext(up.filename or "")[1].lower()
        if ext not in PHOTO_EXT:
            continue
        n += 1
        up.save(os.path.join(pdir, "%02d-%s" % (n, secure_filename(up.filename))))

    store.upsert_vendor(doc["vendor"])
    return jsonify({"ok": True, "id": iid, "number": doc["number"], "download": "/invoices/download/%s" % iid})


@bp.route("/download/<iid>")
def download(iid):
    doc = store.get(iid)
    if not doc:
        abort(404)
    pdir = _photo_dir(iid)
    photos = [os.path.join(pdir, f) for f in _photos(iid)]
    tmpdir = tempfile.mkdtemp(dir=TMP)
    try:
        # copy photos so the resized JPEGs the builder writes don't land in the saved folder
        work = []
        for p in photos:
            dst = os.path.join(tmpdir, os.path.basename(p))
            shutil.copy(p, dst)
            work.append(dst)
        name = "Invoice %s - %s" % (doc["number"], doc["vendor"]["name"])
        if doc["service"].get("address"):
            name += " - %s" % doc["service"]["address"]
        name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", name)[:120].strip() + ".pdf"
        out = os.path.join(tmpdir, name)
        builder.build_pdf(doc, work, out)
        return send_file(out, as_attachment=request.args.get("inline") != "1", download_name=name,
                         mimetype="application/pdf")
    finally:
        pass   # tmpdir is under the OS temp folder; cleaned with the instance


@bp.route("/delete/<iid>", methods=["POST"])
def delete(iid):
    store.delete(iid)
    shutil.rmtree(_photo_dir(iid), ignore_errors=True)
    return jsonify({"ok": True})
