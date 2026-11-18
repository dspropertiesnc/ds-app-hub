"""1-page Tenant Screening Record PDF.

The browser runs the calculator (assets/calc.js) and posts its inputs, its result, and the
PM's decision here. This module only lays that out on one letter page; nothing is stored.
"""
import io, os, re, datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas as rl_canvas

W, H = letter
M = 40
CW = W - 2 * M
ACCENT = colors.HexColor("#a78147")
SUB = colors.HexColor("#efe7d9")
H2 = colors.HexColor("#6b4f22")
INK = colors.HexColor("#1f1f1f")
MUTED = colors.HexColor("#5f5f5f")
RULE = colors.HexColor("#e6dcc8")
OK = colors.HexColor("#2e7d32"); OK_BG = colors.HexColor("#e8f3e9")
BAD = colors.HexColor("#b3261e"); BAD_BG = colors.HexColor("#fbe9e7")
WARN = colors.HexColor("#7a5b1a"); WARN_BG = colors.HexColor("#fbf3e2")
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))

DECISIONS = ["Approved", "Approved with conditions", "Declined", "Applicant withdrew"]
NEEDS_AAN = {"Approved with conditions", "Declined"}
NOTES_MAX = 700
SOP_LINE = "SOP - Tenant Screening v1.3 · D&S weighted score"


class RecordError(ValueError):
    pass


def _num(v, default=0.0):
    try:
        n = float(str(v).replace(",", "").replace("$", "").strip())
        return n if n == n and abs(n) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _s(v, limit=200):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def money(v):
    return "${:,.0f}".format(_num(v))


def validate(payload):
    """Check the parts a person must fill in. Returns cleaned (inp, r, dec)."""
    if not isinstance(payload, dict):
        raise RecordError("Bad request.")
    inp, r, dec = payload.get("inp") or {}, payload.get("r") or {}, payload.get("decision") or {}
    if not all(isinstance(x, dict) for x in (inp, r, dec)):
        raise RecordError("Bad request.")
    if not r.get("complete"):
        raise RecordError("Fill in rent, income, credit score and rental history first.")
    if not _s(inp.get("property")):
        raise RecordError("Enter the property address.")
    if not _s(inp.get("applicantNames")):
        raise RecordError("Enter the applicant name(s).")
    if not _s(dec.get("by")):
        raise RecordError("Enter who processed the application.")
    decision = _s(dec.get("decision"))
    if decision not in DECISIONS:
        raise RecordError("Pick the final decision.")
    notes = str(dec.get("notes") or "").strip()
    if len(notes) > NOTES_MAX:
        raise RecordError("Keep the notes under %d characters so the record fits on 1 page." % NOTES_MAX)
    rec = r.get("recommendation")
    override = decision != "Applicant withdrew" and (rec is None or decision != rec)
    if override and not notes:
        raise RecordError("Explain the decision in the notes: it differs from the calculator, or the file needs PM judgment.")
    aan = _s(dec.get("aan"))
    if decision in NEEDS_AAN and aan not in ("sent", "pending"):
        raise RecordError("Mark whether the adverse action notice was sent.")
    if decision in NEEDS_AAN and aan == "sent" and not _s(dec.get("aanDate")):
        raise RecordError("Enter the date the adverse action notice was sent.")
    dec = {"by": _s(dec.get("by"), 60), "decision": decision, "notes": notes, "override": override,
           "aan": aan if decision in NEEDS_AAN else "na", "aanDate": _s(dec.get("aanDate"), 20),
           "date": _s(dec.get("date"), 20)}
    return inp, r, dec


# ---------- drawing helpers ----------
def _style(size=8.5, color=INK, bold=False, lead=None, align=0):
    return ParagraphStyle("s", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=lead or size * 1.3, textColor=color, alignment=align)


def _para(cv, text, x, y_top, w, style):
    p = Paragraph(text, style)
    _, h = p.wrap(w, 1000)
    p.drawOn(cv, x, y_top - h)
    return h


def _section(cv, title, y):
    cv.setFillColor(SUB); cv.rect(M, y - 15, CW, 15, stroke=0, fill=1)
    cv.setFillColor(ACCENT); cv.rect(M, y - 15, 3, 15, stroke=0, fill=1)
    cv.setFillColor(H2); cv.setFont("Helvetica-Bold", 8.5)
    cv.drawString(M + 8, y - 11, title.upper())
    return y - 21


def _fmt_date(s):
    try:
        return datetime.date.fromisoformat(s).strftime("%m/%d/%Y")
    except (TypeError, ValueError):
        return s or ""


def build(payload, now=None, fit_check=True):
    """Render the page; if it runs long, retry with tighter text before giving up."""
    inp, r, dec = validate(payload)
    for fs in (8.5, 7.8, 7.2, 6.8):
        pdf, fits = _render(inp, r, dec, now, fs)
        if fits:
            return pdf
    if fit_check:
        raise RecordError("Too much text to fit on 1 page. Shorten the notes.")
    return pdf


def _render(inp, r, dec, now, fs):
    lead = fs * 1.3
    rowh = 15 if fs >= 8.5 else 13 if fs >= 7.8 else 12
    now = now or datetime.datetime.now()
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=letter)
    cv.setTitle("Screening Record - %s" % _s(inp.get("property")))
    cv.setAuthor("Doss & Spaulding Properties")

    # ---- header ----
    y = H - M
    if os.path.exists(LOGO):
        lw = 130; lh = lw * 303 / 1009
        cv.drawImage(LOGO, W - M - lw, y - lh, lw, lh, mask="auto")
    cv.setFillColor(INK); cv.setFont("Helvetica-Bold", 17)
    cv.drawString(M, y - 16, "Tenant Screening Record")
    cv.setFillColor(MUTED); cv.setFont("Helvetica", 8.5)
    cv.drawString(M, y - 30, "Doss & Spaulding Properties LLC · " + SOP_LINE)
    y -= 46
    cv.setStrokeColor(ACCENT); cv.setLineWidth(1.5); cv.line(M, y, W - M, y)
    y -= 8

    # ---- application facts ----
    i = r.get("income") or {}
    rent_txt = money(i.get("rent"))
    if _num(i.get("voucher")) > 0:
        rent_txt += " (voucher %s, tenant %s)" % (money(i.get("voucher")), money(i.get("tenantPortion")))
    facts = [
        ("Property", _s(inp.get("property"), 90)), ("Applicant(s)", _s(inp.get("applicantNames"), 90)),
        ("Monthly rent", rent_txt), ("Decision date", _fmt_date(dec["date"]) or now.strftime("%m/%d/%Y")),
        ("Processed by", dec["by"]),
        ("Boom score", ("%g (reference only)" % _num(r.get("boomScore"))) if r.get("boomScore") is not None else "Not entered"),
    ]
    colw = CW / 3
    for row in range(2):
        hmax = 0
        for col in range(3):
            k, v = facts[row * 3 + col]
            x = M + col * colw
            cv.setFillColor(MUTED); cv.setFont("Helvetica", 7.5); cv.drawString(x, y - 8, k.upper())
            h = _para(cv, escape(v), x, y - 11, colw - 10, _style(9.5, INK, True, 11.5))
            hmax = max(hmax, h)
        y -= 14 + hmax
    y -= 4

    # ---- decision banner ----
    d = dec["decision"]
    fg, bg = {"Approved": (OK, OK_BG), "Approved with conditions": (WARN, WARN_BG),
              "Declined": (BAD, BAD_BG)}.get(d, (MUTED, SUB))
    bh = 58
    cv.setFillColor(bg); cv.setStrokeColor(fg); cv.setLineWidth(0.8)
    cv.roundRect(M, y - bh, CW, bh, 5, stroke=1, fill=1)
    cv.setFillColor(fg); cv.setFont("Helvetica-Bold", 8); cv.drawString(M + 10, y - 14, "FINAL DECISION")
    cv.setFont("Helvetica-Bold", 15); cv.drawString(M + 10, y - 32, d)
    differs = dec["override"] and r.get("recommendation")
    cv.setFillColor(INK); cv.setFont("Helvetica", 8)
    cv.drawString(M + 10, y - 48, "Calculator: %s%s" % (_s(r.get("flag")), "  ·  differs, see notes" if differs else ""))
    score = _num(r.get("score"))
    # score bar on the right half of the banner
    bx0 = M + CW * 0.47
    cv.setFillColor(fg); cv.setFont("Helvetica-Bold", 8)
    cv.drawString(bx0, y - 14, "SCORE")
    cv.setFillColor(INK); cv.setFont("Helvetica-Bold", 10)
    cv.drawRightString(W - M - 10, y - 14, "%.1f / 10  ·  %s" % (score, _s(r.get("bandLabel"))))
    _meter(cv, score, bx0, W - M - 12, y - 30)
    y -= bh + 10

    # ---- score table ----
    y = _section(cv, "How the score was calculated", y)
    cols = [("Factor", 0, "l"), ("Applicant result", 168, "l"), ("Tier", 300, "l"),
            ("Points", 418, "r"), ("Weight", 466, "r"), ("Weighted", CW, "r")]

    def row(vals, yy, bold=False, color=INK, size=8.5):
        cv.setFillColor(color); cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        for (_, x, al), v in zip(cols, vals):
            v = _s(v, 46)
            if al == "l":
                cv.drawString(M + x + 4, yy, v)
            else:
                cv.drawRightString(M + x - 4, yy, v)

    row([c[0] for c in cols], y - 9, True, MUTED, 7.5)
    y -= 13
    for f in (r.get("factors") or [])[:8]:
        cv.setStrokeColor(RULE); cv.setLineWidth(0.5); cv.line(M, y, W - M, y)
        row([f.get("label"), f.get("result"), f.get("tier"), "%g / 10" % _num(f.get("points")),
             "%g%%" % _num(f.get("weight")), "%.2f" % _num(f.get("weighted"))], y - rowh + 4)
        y -= rowh
    cv.setStrokeColor(ACCENT); cv.setLineWidth(0.8); cv.line(M, y, W - M, y)
    row(["Weighted score", "Starting band: " + _s(r.get("startBandLabel")), "", "", "100%", "%.1f" % score], y - 12, True)
    y -= 18
    if fs >= 8.5:   # the banner's bar already shows the edges; drop this line when space is tight
        cv.setFillColor(MUTED); cv.setFont("Helvetica", 7.5)
        cv.drawString(M + 4, y - 7, "Bands: 0 to 4.0 Decline · 4.1 to 5.4 Lower Conditional · 5.5 to 7.0 Upper Conditional · 7.1 to 10 Approve. "
                      "Caps and knockouts can only lower the band.")
        y -= 16
    else:
        y -= 6

    # ---- two columns: income | rules ----
    top = y
    half = (CW - 14) / 2
    yl = _section_col(cv, "Income (gross monthly)", M, top, half)
    lines = []
    credits = r.get("credit") or {}
    raw = list(inp.get("credits") or [])
    for n, v in enumerate((i.get("incomes") or [])[:6]):
        c = _s(raw[n], 4) if n < len(raw) else ""
        if _num(v) > 0 or c:
            lines.append(("Adult %d" % (n + 1), money(v) + ("  ·  credit %s" % c if c else "  ·  no credit score" if raw else "")))
    if credits.get("average") is not None and len(credits.get("scores") or []) > 1:
        lines.append(("Average credit score", "%d" % _num(credits.get("average"))))
    if _num(i.get("eligibleAssets")) > 0:
        lines.append(("Liquid assets", "%s eligible ÷ 12 = %s" % (money(i.get("eligibleAssets")), money(i.get("assetIncome")))))
    if i.get("voucherFull"):
        lines.append(("3x test", "Voucher covers full rent"))
    else:
        lines.append(("Total qualifying", money(i.get("total"))))
        lines.append(("Required (3x %s)" % ("tenant portion" if _num(i.get("voucher")) > 0 else "rent"), money(i.get("required"))))
        ratio = _num(i.get("ratio"))
        lines.append(("Ratio", "%.2fx · %s" % (ratio, "meets 3x" if i.get("meets") else "short %s/mo" % money(i.get("shortfall")))))
    for k, v in lines:
        cv.setFillColor(MUTED); cv.setFont("Helvetica", 8.5); cv.drawString(M + 4, yl - 9, k)
        cv.setFillColor(INK); cv.setFont("Helvetica-Bold", 8.5); cv.drawRightString(M + half - 4, yl - 9, v)
        yl -= 13 if fs >= 8.5 else 11.5

    xr = M + half + 14
    yr = _section_col(cv, "Rules applied", xr, top, half)
    items = ([("Knockout", k, BAD) for k in (r.get("knockouts") or [])] +
             [("Cap", c, WARN) for c in (r.get("caps") or [])] +
             [("PM review", p, H2) for p in (r.get("pm") or [])])
    if not items:
        yr -= _para(cv, "No knockouts, caps or PM review items.", xr + 4, yr - 2, half - 8, _style(8.5, MUTED)) + 4
    for tag, text, col in items[:12]:
        h = _para(cv, '<font name="Helvetica-Bold" color="%s">%s:</font> %s' % (col.hexval().replace("0x", "#"), tag, escape(_s(text, 160))),
                  xr + 4, yr - 2, half - 8, _style(fs, INK, False, lead * 0.95))
        yr -= h + 3
    y = min(yl, yr) - 8

    # ---- conditions ----
    y = _section(cv, "Conditions of approval", y)
    g = r.get("guarantee") or {}
    conds = []
    if d in ("Declined", "Applicant withdrew"):
        conds.append("None: %s." % ("application declined" if d == "Declined" else "applicant withdrew"))
    elif d == "Approved":
        conds.append("None beyond the standard lease and 1-month security deposit (%s)." % money(i.get("rent")))
    else:
        dep = r.get("deposit") or {}
        if dep and _num(dep.get("months")) <= 1:
            dep = {}
        if dep:
            conds.append("Security deposit: %g months' rent = %s%s" % (_num(dep.get("months")),
                         money(dep.get("total")), (" (%s above the standard 1 month)" % money(dep.get("additional"))) if _num(dep.get("additional")) > 0 else ""))
        if g.get("required"):
            t = g.get("type")
            if t == "guarantor":
                gs = "qualified guarantor, %s/mo vs %s needed (4x rent): %s; NC resident: %s" % (
                    money(g.get("guarantorIncome")), money(g.get("guarantorRequiredIncome")),
                    "meets" if g.get("guarantorIncomeOk") else "SHORT", "yes" if g.get("guarantorNcOk") else "NO")
            elif t == "theguarantors":
                gs = "TheGuarantors (subject to their approval)"
            else:
                gs = "required, not yet provided (qualified guarantor or TheGuarantors)"
            conds.append("Lease guarantee: " + gs)
        if not conds:
            conds.append("Set by the PM; see the notes below.")
    for c in conds:
        y -= _para(cv, "• " + escape(c), M + 4, y, CW - 8, _style(fs, INK, False, lead)) + 2
    y -= 6

    # ---- why ----
    y = _section(cv, "Why this decision was made", y)
    for w in (r.get("why") or [])[:6]:
        if d in ("Declined", "Applicant withdrew") and str(w).startswith("Security deposit"):
            continue
        y -= _para(cv, "• " + escape(_s(w, 400)), M + 4, y, CW - 8, _style(fs, INK, False, lead)) + 2
    if dec["notes"]:
        y -= 3
        label = "PM notes" + (" (decision differs from the calculator)" if dec["override"] and r.get("recommendation") else "")
        y -= _para(cv, '<font name="Helvetica-Bold">%s:</font> %s' % (label, escape(dec["notes"]).replace("\n", "<br/>")),
                   M + 4, y, CW - 8, _style(fs, INK, False, lead)) + 2
    y -= 6

    # ---- verification + adverse action ----
    y = _section(cv, "Verification and notices", y)
    pre = r.get("prechecks") or []
    x = M + 4
    cv.setFont("Helvetica", 8)
    for p in pre[:4]:
        ok = bool(p.get("ok"))
        cv.setFillColor(OK if ok else BAD); cv.setFont("Helvetica-Bold", 8)
        mark = "YES" if ok else "NO"
        cv.drawString(x, y - 9, mark)
        cv.setFillColor(INK); cv.setFont("Helvetica", 8)
        cv.drawString(x + 18, y - 9, _s(p.get("label"), 60))
        x += CW / 2
        if x > M + CW - 10:
            x = M + 4; y -= 12
    if x != M + 4:
        y -= 12
    if dec["aan"] == "sent":
        aan, col = "Sent%s." % (" on " + _fmt_date(dec["aanDate"]) if dec["aanDate"] else ""), OK
    elif dec["aan"] == "pending":
        aan, col = "REQUIRED, NOT YET SENT.", BAD
    else:
        aan, col = "Not required for this decision.", MUTED
    y -= _para(cv, '<font name="Helvetica-Bold">Adverse action notice (FCRA):</font> <font color="%s">%s</font>' % (col.hexval().replace("0x", "#"), aan),
               M + 4, y - 2, CW - 8, _style(8.5, INK)) + 2

    # ---- footer ----
    cv.setStrokeColor(RULE); cv.setLineWidth(0.5); cv.line(M, M + 14, W - M, M + 14)
    cv.setFillColor(MUTED); cv.setFont("Helvetica", 7)
    cv.drawString(M, M + 4, "Internal record. Criteria applied the same way to every applicant. Generated %s by the D&S Screening Calculator."
                  % now.strftime("%m/%d/%Y %I:%M %p"))
    cv.drawRightString(W - M, M + 4, "Page 1 of 1")
    fits = y >= M + 20
    _render.last_y = y
    cv.showPage(); cv.save()
    return buf.getvalue(), fits


ZONES = [("decline", 0.0, 4.0, "0 to 4.0", "Decline", colors.HexColor("#e5483f")),
         ("lower", 4.0, 5.5, "4.1 to 5.4", "Lower Conditional", colors.HexColor("#f08a24")),
         ("upper", 5.5, 7.0, "5.5 to 7.0", "Upper Conditional", colors.HexColor("#f2b72b")),
         ("approve", 7.0, 10.0, "7.1 to 10", "Approve", colors.HexColor("#4cbf4a"))]   # mirrors ZONES in calc.js


def _meter(cv, score, x0, x1, ty):
    """0-10 bar with the band zones and a marker at the score; ty is the bar's top edge."""
    w = x1 - x0
    bx = lambda v: x0 + w * max(0.0, min(10.0, v)) / 10.0
    for key, a, b, _, _, col in ZONES:
        cv.setFillColor(col); cv.rect(bx(a), ty - 7, bx(b) - bx(a), 7, stroke=0, fill=1)
    mx = bx(score)
    cv.setFillColor(colors.white); cv.setStrokeColor(INK); cv.setLineWidth(1.2)
    cv.roundRect(mx - 3.5, ty - 10, 7, 13, 2, stroke=1, fill=1)
    cv.setFillColor(MUTED); cv.setFont("Helvetica", 7)
    for v in (0, 4.0, 5.5, 7.0, 10):
        t = "%g" % v if v in (0, 10) else "%.1f" % v
        if v == 0:
            cv.drawString(bx(v), ty - 18, t)
        elif v == 10:
            cv.drawRightString(bx(v), ty - 18, t)
        else:
            cv.drawCentredString(bx(v), ty - 18, t)


def _section_col(cv, title, x, y, w):
    cv.setFillColor(SUB); cv.rect(x, y - 15, w, 15, stroke=0, fill=1)
    cv.setFillColor(ACCENT); cv.rect(x, y - 15, 3, 15, stroke=0, fill=1)
    cv.setFillColor(H2); cv.setFont("Helvetica-Bold", 8.5)
    cv.drawString(x + 8, y - 11, title.upper())
    return y - 20


def filename(payload):
    inp = (payload or {}).get("inp") or {}
    prop = re.sub(r"[^\w .#-]", "", _s(inp.get("property"), 60)).strip() or "Property"
    who = re.sub(r"[^\w .-]", "", _s(inp.get("applicantNames"), 40).replace("/", "-")).strip()
    return "Screening Record - %s%s.pdf" % (prop, (" - " + who) if who else "")
