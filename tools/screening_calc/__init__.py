import os
from flask import Blueprint, render_template, send_from_directory

bp = Blueprint("screening_calc", __name__, url_prefix="/screening-calc", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

META = {"name": "Screening Calculator",
        "desc": "Income-to-rent, asset depletion, guarantor check, Boom band, caps and knockouts. Gives the deposit, conditions and a Slack summary.",
        "url": "/screening-calc/", "group": "Leasing & Contracts", "icon": "\U0001F9EE", "ready": True}


@bp.route("/")
def index():
    return render_template("screening_calc.html")


@bp.route("/assets/<path:name>")
def assets(name):
    return send_from_directory(ASSETS, name, max_age=300)
