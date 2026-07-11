import os
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from tools.punchlist import bp as punchlist_bp, META as PUNCHLIST_META
from tools.listings import bp as listings_bp, META as LISTINGS_META
from tools.contracts import bp as contracts_bp, META as CONTRACTS_META

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
APP_PASSWORD = os.environ.get("APP_PASSWORD")  # unset = open (local/dev)

app.register_blueprint(punchlist_bp)
app.register_blueprint(listings_bp)
app.register_blueprint(contracts_bp)

# ---- Tool registry, grouped by workflow. Add a card here for each new tool. ----
TOOL_GROUPS = [
    {"group": "Maintenance & Turns", "items": [PUNCHLIST_META]},
    {"group": "Marketing", "items": [LISTINGS_META]},
    {"group": "Leasing & Contracts", "items": [CONTRACTS_META]},
]

@app.before_request
def gate():
    if not APP_PASSWORD:
        return
    if session.get("auth"):
        return
    p = request.path
    if p.startswith("/static") or p.startswith("/login"):
        return
    if request.method == "POST" or "/generate" in p or "/download" in p:
        return jsonify({"error": "Session expired. Please sign in again."}), 401
    return redirect(url_for("login", next=p))

@app.route("/")
def home():
    return render_template("home.html", groups=TOOL_GROUPS, has_login=bool(APP_PASSWORD))

@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("home"))
    error = ""
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect(request.args.get("next") or url_for("home"))
        error = "Incorrect password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login") if APP_PASSWORD else url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
