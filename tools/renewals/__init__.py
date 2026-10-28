"""Rent Renewal Proposals (/renewals/).

Team flow: pick the owner's month-to-month leases from Rentvine (current rent fills in),
upload each property's comp reports (PDF) and let Claude pull the comps and a market range,
set the renewal rent, then download the branded owner PDF and copy the owner email.
Every proposal is saved so it can be reopened and edited later.
"""
import os, re, uuid, tempfile, datetime
from flask import Blueprint, request, jsonify, render_template, send_file, abort
from . import rentvine, store, extract, builder

bp = Blueprint("renewals", __name__, url_prefix="/renewals", template_folder="templates")

META = {"name": "Rent Renewal Proposals",
        "desc": "Pull current rent from Rentvine, read the comp reports, and build the owner's renewal PDF and email.",
        "url": "/renewals/", "group": "Leasing & Contracts", "icon": "\U0001F4C8", "ready": True}

TMP = os.path.join(tempfile.gettempdir(), "renewal_pdfs")
os.makedirs(TMP, exist_ok=True)
MAX_UPLOAD = 25 * 1024 * 1024

store.init()


def _clean_doc(d):
    """Keep only the fields we expect, with numbers as numbers."""
    def n(v):
        v = builder.num(v)
        return None if v is None else (int(v) if v == int(v) else v)
    props = []
    for p in (d.get("properties") or [])[:20]:
        comps = []
        for c in (p.get("comps") or [])[:60]:
            comps.append({k: c.get(k) for k in ("address", "type", "last_seen", "source")} |
                         {k: n(c.get(k)) for k in ("beds", "baths", "sqft", "distance_mi", "rent", "year_built")} |
                         {"show": bool(c.get("show")), "outlier": bool(c.get("outlier"))})
        props.append({
            "address": (p.get("address") or "").strip(), "city_line": (p.get("city_line") or "").strip(),
            "home_type": (p.get("home_type") or "").strip(), "narrative": (p.get("narrative") or "").strip(),
            "narrative_custom": bool(p.get("narrative_custom")),
            "section8": bool(p.get("section8")),
            **{k: n(p.get(k)) for k in ("beds", "baths", "sqft", "year_built", "current_rent",
                                        "market_low", "market_high", "renewal_rent")},
            "rentvine": p.get("rentvine") if isinstance(p.get("rentvine"), dict) else None,
            "estimates": p.get("estimates") if isinstance(p.get("estimates"), list) else [],
            "notes": [x for x in (p.get("notes") or []) if isinstance(x, str)][:10],
            "files": [x for x in (p.get("files") or []) if isinstance(x, str)][:20],
            "comps": comps,
        })
    return {
        "id": (d.get("id") or "").strip() or None,
        "owner_name": (d.get("owner_name") or "").strip(),
        "owner_email": (d.get("owner_email") or "").strip(),
        "prepared_by": (d.get("prepared_by") or "").strip(),
        "data_date": (d.get("data_date") or datetime.date.today().isoformat())[:10],
        "status": d.get("status") if d.get("status") in ("draft", "sent", "accepted", "declined") else "draft",
        "email_subject": d.get("email_subject") or "", "email_body": d.get("email_body") or "",
        "email_custom": bool(d.get("email_custom")),
        "properties": props,
    }


# ---------- pages ----------
@bp.route("/")
def index():
    return render_template("renewals_list.html", rows=store.listing(request.args.get("q", "")),
                           q=request.args.get("q", ""), persistent=store.persistent())


@bp.route("/new")
def new():
    return render_template("renewals_edit.html", pid="", rv=rentvine.configured(),
                           ai=bool(os.getenv("ANTHROPIC_API_KEY")))


@bp.route("/p/<pid>")
def edit(pid):
    if not store.get(pid):
        abort(404)
    return render_template("renewals_edit.html", pid=pid, rv=rentvine.configured(),
                           ai=bool(os.getenv("ANTHROPIC_API_KEY")))


# ---------- Rentvine ----------
@bp.route("/api/rentvine/search")
def rv_search():
    try:
        return jsonify({"results": rentvine.search(request.args.get("q", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/owner")
def rv_owner():
    try:
        return jsonify({"results": rentvine.by_owner(request.args.get("q", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/lease/<int:lease_id>/fields")
def rv_fields(lease_id):
    """Setup check: which fields Rentvine returns for a lease (names only, no values)."""
    try:
        return jsonify(rentvine.lease_fields(lease_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ---------- comps ----------
@bp.route("/api/extract", methods=["POST"])
def api_extract():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify({"error": "Upload at least one comp report (PDF)."}), 400
    data, total = [], 0
    for f in files:
        b = f.read(); total += len(b)
        if total > MAX_UPLOAD:
            return jsonify({"error": "Those files are over 25 MB together. Upload fewer at a time."}), 400
        if not re.search(r"\.(pdf|png|jpe?g)$", f.filename, re.I):
            return jsonify({"error": "%s isn't a PDF or image." % f.filename}), 400
        data.append((f.filename, b))
    try:
        out = extract.extract(data, hint=request.form.get("address", ""))
    except Exception as e:
        return jsonify({"error": "Couldn't read the reports: %s" % e}), 502
    out["files"] = [f.filename for f in files]
    return jsonify(out)


# ---------- proposals ----------
@bp.route("/api/proposals", methods=["POST"])
def api_save():
    doc = _clean_doc(request.get_json(force=True) or {})
    if not doc["owner_name"] and not doc["properties"]:
        return jsonify({"error": "Add an owner or a property first."}), 400
    if not doc["id"]:
        doc.pop("id")
    saved = store.save(doc, user=doc.get("prepared_by", ""))
    return jsonify({"id": saved["id"], "updated_at": saved["updated_at"]})


@bp.route("/api/proposals/<pid>")
def api_get(pid):
    d = store.get(pid)
    if not d:
        return jsonify({"error": "Not found."}), 404
    return jsonify(d)


@bp.route("/api/proposals/<pid>", methods=["DELETE"])
def api_delete(pid):
    store.delete(pid)
    return jsonify({"ok": True})


@bp.route("/api/email", methods=["POST"])
def api_email():
    return jsonify(builder.email_draft(_clean_doc(request.get_json(force=True) or {})))


@bp.route("/api/narrative", methods=["POST"])
def api_narrative():
    p = (_clean_doc({"properties": [request.get_json(force=True) or {}]})["properties"] or [{}])[0]
    return jsonify({"narrative": builder.default_narrative(p)})


def _pdf_for(doc):
    owner = re.sub(r'[\\/:*?"<>|\r\n]+', " ", doc.get("owner_name") or "Owner").strip()[:60]
    path = os.path.join(TMP, uuid.uuid4().hex[:12] + ".pdf")
    builder.build_pdf(doc, path)
    return path, "Renewal Analysis - %s.pdf" % owner


@bp.route("/api/pdf", methods=["POST"])
def api_pdf():
    """PDF straight from the editor's current state (no save needed)."""
    doc = _clean_doc(request.get_json(force=True) or {})
    try:
        path, name = _pdf_for(doc)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return send_file(path, as_attachment=True, download_name=name, mimetype="application/pdf")


@bp.route("/p/<pid>/pdf")
def saved_pdf(pid):
    doc = store.get(pid)
    if not doc:
        abort(404)
    path, name = _pdf_for(doc)
    return send_file(path, as_attachment=request.args.get("view") != "1",
                     download_name=name, mimetype="application/pdf")
