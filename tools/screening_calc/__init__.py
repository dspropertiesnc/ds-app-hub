import os
from flask import Blueprint, render_template, send_from_directory, request, jsonify, Response
from . import record

bp = Blueprint("screening_calc", __name__, url_prefix="/screening-calc", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

META = {"name": "Screening Calculator",
        "desc": "Weighted 0-10 score from the Boom results, caps and knockouts, deposit and guarantee. Produces a 1-page screening record for the file.",
        "url": "/screening-calc/", "group": "Leasing & Contracts", "icon": "\U0001F9EE", "ready": True}


@bp.route("/")
def index():
    return render_template("screening_calc.html")


@bp.route("/assets/<path:name>")
def assets(name):
    return send_from_directory(ASSETS, name, max_age=300)


@bp.route("/record", methods=["POST"])
def record_pdf():
    payload = request.get_json(silent=True)
    try:
        pdf = record.build(payload)
    except record.RecordError as e:
        return jsonify(error=str(e)), 400
    fn = record.filename(payload).replace('"', "")
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % fn,
                             "Cache-Control": "no-store"})
