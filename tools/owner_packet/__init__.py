"""Owner Packet Builder (/owner-packet/).

Builds the rental analysis + management proposal packet for a prospective owner client:
upload each home's rent reports and let Claude draft the analysis (or skip it for homes that
already have tenants), pull the owner's homes from Rentvine, review, then download the PDF.
Every packet saves automatically so the team can reopen it later. Pricing & settings are
shared by everyone.
"""
import os, re
from flask import Blueprint, request, jsonify, render_template, send_from_directory, abort
from . import store, analyze, lookup

bp = Blueprint("owner_packet", __name__, url_prefix="/owner-packet", template_folder="templates")

META = {"name": "Owner Packet Builder",
        "desc": "Rental analysis and management proposal for prospective owners, with Rentvine lookup and saved packets.",
        "url": "/owner-packet/", "group": "New Business", "icon": "\U0001F4D1", "ready": True}

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
MAX_UPLOAD = 30 * 1024 * 1024
MAX_STATE = 3 * 1024 * 1024

store.init()


def _config(pid="", state=None):
    return {"pid": pid, "state": state, "ai": bool(os.getenv("ANTHROPIC_API_KEY")),
            "rv": lookup.configured(), "persistent": store.persistent()}


# ---------- pages ----------
@bp.route("/")
def index():
    q = request.args.get("q", "")
    return render_template("owner_packet_list.html", rows=store.listing(q), q=q, persistent=store.persistent())


@bp.route("/new")
def new():
    return render_template("owner_packet.html", config=_config())


@bp.route("/p/<pid>")
def edit(pid):
    doc = store.get(pid)
    if not doc:
        abort(404)
    return render_template("owner_packet.html", config=_config(pid, doc["state"]))


@bp.route("/assets/<path:name>")
def assets(name):
    return send_from_directory(ASSETS, name, max_age=86400)


# ---------- saved packets ----------
@bp.route("/api/packets", methods=["POST"])
def api_save():
    if request.content_length and request.content_length > MAX_STATE:
        return jsonify({"error": "This packet is too large to save."}), 400
    body = request.get_json(force=True, silent=True) or {}
    state = body.get("state")
    if not isinstance(state, dict):
        return jsonify({"error": "Nothing to save."}), 400
    pid = re.sub(r"[^a-f0-9]", "", str(body.get("id") or ""))[:10]
    return jsonify(store.save(pid or None, state))


@bp.route("/api/packets/<pid>", methods=["DELETE"])
def api_delete(pid):
    store.delete(pid)
    return jsonify({"ok": True})


# ---------- shared pricing & settings ----------
@bp.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        vals = request.get_json(force=True, silent=True) or {}
        if not isinstance(vals, dict):
            return jsonify({"error": "Bad settings."}), 400
        clean = {str(k)[:40]: v for k, v in vals.items() if isinstance(v, (int, float, str))}
        store.set_settings(clean)
        return jsonify({"ok": True})
    return jsonify(store.get_settings())


# ---------- Claude ----------
@bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify({"error": "Add the report PDFs for this property."}), 400
    data, total = [], 0
    for f in files:
        if not re.search(r"\.(pdf|png|jpe?g)$", f.filename, re.I):
            return jsonify({"error": "%s isn't a PDF or image." % f.filename}), 400
        b = f.read(); total += len(b)
        if total > MAX_UPLOAD:
            return jsonify({"error": "These reports are over 30 MB together. Try fewer files."}), 400
        data.append((f.filename, b))
    try:
        return jsonify(analyze.analyze(data, hint=request.form.get("hint", "")))
    except Exception as e:
        return jsonify({"error": "Couldn't read the reports: %s" % e}), 502


@bp.route("/api/redraft", methods=["POST"])
def api_redraft():
    try:
        return jsonify({"text": analyze.redraft(request.get_json(force=True, silent=True) or {})})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ---------- Rentvine ----------
@bp.route("/api/rentvine/owners")
def rv_owners():
    try:
        return jsonify({"results": lookup.owners(request.args.get("q", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/api/rentvine/homes")
def rv_homes():
    try:
        return jsonify({"results": lookup.homes(request.args.get("portfolio_id"), request.args.get("owner", ""))})
    except Exception as e:
        return jsonify({"error": str(e)}), 502
