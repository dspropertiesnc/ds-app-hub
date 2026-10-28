"""Owner-facing renewal proposal PDF + email draft.

Layout mirrors the Munish renewal handout: a summary page, then one page per property.
Nothing here names a data source (Zillow, RentRange, Rentometer): owners see ranges and comps only.
"""
import os, datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas as rl_canvas

W, H = letter                      # 612 x 792 pt
M = 48                             # side margin
CW = W - 2 * M                     # content width
INK = colors.HexColor("#1F1F1F")
MUTED = colors.HexColor("#5F5F5F")
BODY = colors.HexColor("#4A4A4A")
GOLD = colors.HexColor("#B08A4A")
GOLD_TEXT = colors.HexColor("#8A6A2F")
GOLD_LIGHT = colors.HexColor("#D9C29A")
RULE = colors.HexColor("#E6DCC8")
CREAM = colors.HexColor("#F8F4EC")
CREAM2 = colors.HexColor("#F1E9DA")
TRACK = colors.HexColor("#EFE8DA")
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))
PHONE_LINE = os.getenv("RENEWALS_CONTACT_LINE", "336-494-1710 · info@dspropertiesnc.com · dspropertiesnc.com")
NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


# ---------- numbers ----------
def num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def money(v, sign=False):
    v = num(v)
    if v is None:
        return "—"
    s = "${:,.0f}".format(abs(v))
    if v < 0:
        return "-" + s
    return ("+" + s) if sign else s


def rng(lo, hi, sep=" – "):
    return "%s%s%s" % (money(lo), sep, money(hi))


def word(n):
    return NUM_WORDS[n] if 0 <= n < len(NUM_WORDS) else str(n)


def fmt_baths(b):
    b = num(b)
    if b is None:
        return "—"
    return ("%d" % b) if b == int(b) else ("%g" % b)


def fmt_int(v, comma=True):
    v = num(v)
    if not v:
        return "—"
    return "{:,.0f}".format(v) if comma else "%d" % v


def calc(p):
    """Derived numbers for one property."""
    cur, ren = num(p.get("current_rent")), num(p.get("renewal_rent"))
    lo, hi = num(p.get("market_low")), num(p.get("market_high"))
    out = {"cur": cur, "ren": ren, "lo": lo, "hi": hi, "inc": None, "pct": None,
           "below_lo": None, "below_hi": None}
    if cur and ren:
        out["inc"] = ren - cur
        out["pct"] = (ren - cur) / cur * 100
    if ren and lo:
        out["below_lo"] = lo - ren
    if ren and hi:
        out["below_hi"] = hi - ren
    return out


def featured_comps(p, n=4):
    comps = [c for c in (p.get("comps") or []) if c.get("show") or c.get("featured")]
    return comps[:n]


def default_narrative(p):
    c = calc(p)
    comps = featured_comps(p)
    first = ""
    if len(comps) >= 2:
        a, b = comps[0], comps[1]
        dists = [num(x.get("distance_mi")) for x in (a, b) if num(x.get("distance_mi"))]
        near = ""
        if dists:
            md = max(dists)
            near = " are within a quarter mile and" if md <= 0.3 else (" are within half a mile and" if md <= 0.55 else " are nearby and")
        r = sorted([num(a.get("rent")) or 0, num(b.get("rent")) or 0])
        rent_txt = money(r[0]) if r[0] == r[1] else "%s and %s" % (money(r[0]), money(r[1]))
        first = "The closest comps, %s and %s,%s rent for %s. " % (a.get("address"), b.get("address"), near or "", rent_txt)
        first = first.replace(",, ", ", ").replace(", rent", " rent") if not near else first
    elif len(comps) == 1:
        first = "The closest comp, %s, rents for %s. " % (comps[0].get("address"), money(comps[0].get("rent")))
    if c["ren"] and c["below_lo"] is not None and c["below_hi"] is not None and c["below_lo"] > 0:
        second = "At %s the tenants still pay %s to %s less than comparable homes nearby." % (
            money(c["ren"]), money(c["below_lo"]), money(c["below_hi"]))
    elif c["ren"]:
        second = "At %s the rent is in line with comparable homes nearby." % money(c["ren"])
    else:
        second = ""
    return (first + second).strip()


# ---------- drawing helpers ----------
def _spaced(cv, x, y, text, font, size, color, space=1.4):
    t = cv.beginText(x, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(space)
    t.textOut(text)
    t.setCharSpace(0)
    cv.drawText(t)


def _para(cv, text, x, y_top, width, size=10.5, color=BODY, font="Helvetica", leading=None, italic=False):
    st = ParagraphStyle("p", fontName="Helvetica-Oblique" if italic else font, fontSize=size,
                        leading=leading or size * 1.5, textColor=color, alignment=TA_LEFT)
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    p = Paragraph(text, st)
    _, h = p.wrap(width, 1000)
    p.drawOn(cv, x, y_top - h)
    return h


def _fit(cv, text, font, size, max_w, min_size=18):
    while size > min_size and cv.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def _header(cv, doc):
    y = H - 36
    if os.path.exists(LOGO):
        lw, lh = 160, 160 * 303 / 1009
        cv.drawImage(LOGO, M, y - lh, width=lw, height=lh, mask="auto")
    else:
        lh = 48
        cv.setFont("Helvetica-Bold", 14); cv.setFillColor(INK)
        cv.drawString(M, y - 30, "Doss & Spaulding Properties")
    cv.setFont("Helvetica", 9); cv.setFillColor(MUTED)
    who = doc.get("owner_name") or "Owner"
    cv.drawRightString(W - M, y - lh / 2 - 3, "Renewal Analysis · Prepared for %s" % who)
    ry = y - lh - 10
    cv.setStrokeColor(GOLD); cv.setLineWidth(1.5)
    cv.line(M, ry, W - M, ry)
    return ry


def _footer(cv, doc):
    y = 30
    cv.setStrokeColor(RULE); cv.setLineWidth(0.75)
    cv.line(M, y + 14, W - M, y + 14)
    cv.setFont("Helvetica", 9); cv.setFillColor(MUTED)
    cv.drawString(M, y, PHONE_LINE)
    cv.drawRightString(W - M, y, "Market data as of %s" % doc.get("data_date_label", ""))


def _dark(cv, x, y_top, w, h):
    cv.setFillColor(INK)
    cv.roundRect(x, y_top - h, w, h, 9, stroke=0, fill=1)


def _table(cv, y, cols, header, rows, total=None, row_h=26, first_bold=False, sub=None):
    """cols: list of (width, align). Returns new y."""
    x0 = M
    cv.setFont("Helvetica-Bold", 8); cv.setFillColor(MUTED)
    x = x0
    for (wd, al), h in zip(cols, header):
        _ty = y - 14
        if al == "R":
            tw = cv.stringWidth(h, "Helvetica-Bold", 8) + 0.9 * len(h)
            _spaced(cv, x + wd - 6 - tw, _ty, h, "Helvetica-Bold", 8, MUTED, 0.9)
        else:
            _spaced(cv, x + 6, _ty, h, "Helvetica-Bold", 8, MUTED, 0.9)
        x += wd
    y -= 22
    cv.setStrokeColor(GOLD); cv.setLineWidth(1.5); cv.line(x0, y, x0 + CW, y)
    for i, r in enumerate(rows):
        rh = row_h + (10 if sub and sub[i] else 0)
        if i % 2 == 1:
            cv.setFillColor(CREAM); cv.rect(x0, y - rh, CW, rh, stroke=0, fill=1)
        x = x0
        for j, ((wd, al), val) in enumerate(zip(cols, r)):
            bold = (j == len(cols) - 1) or (first_bold and j == 0)
            font = "Helvetica-Bold" if bold else "Helvetica"
            size = 10.5
            cv.setFont(font, size); cv.setFillColor(INK)
            ty = y - (row_h / 2) - 4 if not (sub and sub[i]) else y - 15
            if al == "R":
                cv.drawRightString(x + wd - 6, ty, str(val))
            else:
                cv.drawString(x + 6, ty, str(val))
            if j == 0 and sub and sub[i]:
                cv.setFont("Helvetica", 9); cv.setFillColor(MUTED)
                cv.drawString(x + 6, ty - 13, sub[i])
            x += wd
        y -= rh
        cv.setStrokeColor(RULE); cv.setLineWidth(0.75); cv.line(x0, y, x0 + CW, y)
    if total:
        cv.setFillColor(CREAM2); cv.rect(x0, y - row_h, CW, row_h, stroke=0, fill=1)
        x = x0
        for (wd, al), val in zip(cols, total):
            cv.setFont("Helvetica-Bold", 10.5); cv.setFillColor(INK)
            ty = y - row_h / 2 - 4
            if al == "R":
                cv.drawRightString(x + wd - 6, ty, str(val))
            else:
                cv.drawString(x + 6, ty, str(val))
            x += wd
        y -= row_h
    return y


# ---------- pages ----------
def _summary_page(cv, doc):
    props = doc["properties"]
    n = len(props)
    y = _header(cv, doc) - 26
    _spaced(cv, M, y, "RENEWAL SUMMARY", "Helvetica-Bold", 9, GOLD_TEXT, 1.6)
    y -= 34
    title = "Your renewal at a glance" if n == 1 else "Your %s renewals at a glance" % word(n)
    fs = _fit(cv, title, "Helvetica-Bold", 30, CW)
    cv.setFont("Helvetica-Bold", fs); cv.setFillColor(INK); cv.drawString(M, y, title)
    y -= 14
    intro = doc.get("intro") or (
        "We compared each home to similar homes renting nearby right now. "
        + ("Your tenants are paying well below market. " if n > 1 else "Your tenant is paying well below market. ")
        + "Our recommended renewal rents close part of that gap while keeping each home priced under "
        "anything comparable, so your tenants have every reason to stay.")
    y -= _para(cv, intro, M, y, CW * 0.86, size=11, leading=16.5)
    y -= 20

    cur = sum(num(p.get("current_rent")) or 0 for p in props)
    ren = sum(num(p.get("renewal_rent")) or 0 for p in props)
    lo = sum(num(p.get("market_low")) or 0 for p in props)
    hi = sum(num(p.get("market_high")) or 0 for p in props)
    card_h = 88
    _dark(cv, M, y, CW, card_h)
    colw = CW / 3
    cells = [("CURRENT MONTHLY RENT", money(cur), ""),
             ("RECOMMENDED RENEWAL", money(ren), "%s a month" % money(ren - cur, sign=True)),
             ("ADDED YEARLY INCOME", money((ren - cur) * 12, sign=True), "over a 12-month term")]
    for i, (lab, big, small) in enumerate(cells):
        x = M + 22 + i * colw
        if i:
            cv.setStrokeColor(colors.HexColor("#555555")); cv.setLineWidth(0.75)
            cv.line(M + i * colw + 6, y - 18, M + i * colw + 6, y - card_h + 18)
        _spaced(cv, x, y - 26, lab, "Helvetica-Bold", 8, GOLD_LIGHT, 1.1)
        cv.setFont("Helvetica-Bold", 24); cv.setFillColor(colors.white); cv.drawString(x, y - 54, big)
        if small:
            cv.setFont("Helvetica", 9.5); cv.setFillColor(colors.HexColor("#CFCFCF")); cv.drawString(x, y - 70, small)
    y -= card_h + 20

    cols = [(CW * 0.34, "L"), (CW * 0.13, "L"), (CW * 0.14, "R"), (CW * 0.24, "R"), (CW * 0.15, "R")]
    rows, sub = [], []
    for p in props:
        rows.append([p.get("address", ""), "%s / %s" % (fmt_int(p.get("beds"), False), fmt_baths(p.get("baths"))),
                     money(p.get("current_rent")), rng(p.get("market_low"), p.get("market_high")),
                     money(p.get("renewal_rent"))])
        sub.append((p.get("city_line") or "").split(",")[0])
    total = ["Total", "", money(cur), rng(lo, hi), money(ren)] if n > 1 else None
    y = _table(cv, y, cols, ["PROPERTY", "BED / BATH", "CURRENT", "MARKET RANGE", "RENEWAL"], rows,
               total=total, row_h=28, first_bold=True, sub=sub)

    # callouts, if there's room
    gaps_lo = [calc(p)["below_lo"] for p in props if calc(p)["below_lo"] is not None]
    gaps_hi = [calc(p)["below_hi"] for p in props if calc(p)["below_hi"] is not None]
    if gaps_lo and min(gaps_lo) > 0:
        stay = "Each renewal stays %s to %s under market, so moving would cost your tenants more, not less." % (
            money(min(gaps_lo)), money(max(gaps_hi)))
        if n == 1:
            stay = "The renewal stays %s to %s under market, so moving would cost your tenant more, not less." % (
                money(min(gaps_lo)), money(max(gaps_hi)))
    else:
        stay = "Renewal rents stay at or below comparable homes nearby, so a move wouldn't save your tenants money."
    callouts = [("Tenants stay put", stay),
                ("Real comps", "Every range is backed by similar homes renting nearby right now, many within half a mile."),
                ("12 months of stability", "Month-to-month tenants can leave on short notice. A 12-month term locks in steady income for the year.")]
    if y - 150 > 60:
        y -= 26
        cw3 = (CW - 30) / 3
        hmax = 0
        for i, (t, b) in enumerate(callouts):
            x = M + i * (cw3 + 15)
            cv.setStrokeColor(GOLD); cv.setLineWidth(2.2); cv.line(x, y, x + cw3, y)
            cv.setFont("Helvetica-Bold", 11); cv.setFillColor(INK); cv.drawString(x, y - 18, t)
            hmax = max(hmax, _para(cv, b, x, y - 25, cw3, size=9.5, leading=14))
        y -= 25 + hmax + 16
    note = ("Market ranges assume average condition and are based on data as of %s. Renewal rents are our "
            "recommendation; final terms are your decision. Detailed comps for each property follow."
            % doc.get("data_date_label", ""))
    if y - 40 > 50:
        _para(cv, note, M, y, CW, size=9, color=MUTED, leading=13.5, italic=True)
    _footer(cv, doc)


def _scale(cv, y, p):
    c = calc(p)
    pts = [v for v in (c["cur"], c["ren"], c["lo"], c["hi"]) if v]
    if len(pts) < 2:
        return y
    lo_v, hi_v = min(pts), max(pts)
    pad = (hi_v - lo_v) * 0.14 or 100
    a, b = lo_v - pad, hi_v + pad
    X = lambda v: M + (v - a) / (b - a) * CW
    line_y = y - 26
    cv.setFillColor(TRACK); cv.roundRect(M, line_y - 2.25, CW, 4.5, 2.25, stroke=0, fill=1)
    if c["lo"] and c["hi"]:
        x1, x2 = X(c["lo"]), X(c["hi"])
        cv.setFillColor(GOLD_LIGHT); cv.roundRect(x1, line_y - 5.25, max(x2 - x1, 8), 10.5, 5.25, stroke=0, fill=1)
        lab = "Market %s" % rng(c["lo"], c["hi"])
        cv.setFont("Helvetica-Bold", 9); cv.setFillColor(INK)
        mid = (x1 + x2) / 2
        tw = cv.stringWidth(lab, "Helvetica-Bold", 9)
        mid = min(max(mid, M + tw / 2), W - M - tw / 2)
        cv.drawCentredString(mid, y - 6, lab)
    labels = []
    if c["cur"]:
        xc = X(c["cur"])
        cv.setFillColor(colors.white); cv.setStrokeColor(colors.HexColor("#767676")); cv.setLineWidth(2.2)
        cv.circle(xc, line_y, 5.5, stroke=1, fill=1)
        labels.append([xc, "Current ", money(c["cur"])])
    if c["ren"]:
        xr = X(c["ren"])
        cv.setFillColor(INK); cv.setStrokeColor(GOLD); cv.setLineWidth(3)
        cv.circle(xr, line_y, 6.5, stroke=1, fill=1)
        labels.append([xr, "Renewal ", money(c["ren"])])
    # keep the two labels apart
    widths = [cv.stringWidth(l[1], "Helvetica", 9) + cv.stringWidth(l[2], "Helvetica-Bold", 9) for l in labels]
    if len(labels) == 2:
        need = (widths[0] + widths[1]) / 2 + 14
        gap = labels[1][0] - labels[0][0]
        if abs(gap) < need:
            push = (need - abs(gap)) / 2 * (1 if gap >= 0 else -1)
            labels[0][0] -= push; labels[1][0] += push
    for (x, t1, t2), wdt in zip(labels, widths):
        x = min(max(x, M + wdt / 2), W - M - wdt / 2)
        sx = x - wdt / 2
        cv.setFont("Helvetica", 9); cv.setFillColor(MUTED); cv.drawString(sx, line_y - 22, t1)
        cv.setFont("Helvetica-Bold", 9); cv.setFillColor(INK)
        cv.drawString(sx + cv.stringWidth(t1, "Helvetica", 9), line_y - 22, t2)
    return line_y - 34


def _property_page(cv, doc, p, i, n):
    c = calc(p)
    y = _header(cv, doc) - 24
    _spaced(cv, M, y, "PROPERTY %d OF %d" % (i, n), "Helvetica-Bold", 9, GOLD_TEXT, 1.6)
    y -= 32
    title = p.get("address") or "Property"
    fs = _fit(cv, title, "Helvetica-Bold", 30, CW)
    cv.setFont("Helvetica-Bold", fs); cv.setFillColor(INK); cv.drawString(M, y, title)
    y -= 18
    cv.setFont("Helvetica", 12); cv.setFillColor(MUTED); cv.drawString(M, y, p.get("city_line") or "")
    y -= 16

    facts = [(fmt_int(p.get("beds"), False), "Bedrooms"), (fmt_baths(p.get("baths")), "Bathrooms"),
             (fmt_int(p.get("sqft")), "Square feet"), (fmt_int(p.get("year_built"), False), "Year built"),
             (p.get("home_type") or "—", "Home type")]
    fh = 46
    cv.setStrokeColor(RULE); cv.setLineWidth(0.75)
    cv.roundRect(M, y - fh, CW, fh, 7, stroke=1, fill=0)
    fw = CW / 5
    for k, (v, lab) in enumerate(facts):
        x = M + k * fw
        if k:
            cv.line(x, y, x, y - fh)
        fsz = _fit(cv, str(v), "Helvetica-Bold", 15, fw - 18, 10)
        cv.setFont("Helvetica-Bold", fsz); cv.setFillColor(INK); cv.drawString(x + 10, y - 20, str(v))
        cv.setFont("Helvetica", 9); cv.setFillColor(MUTED); cv.drawString(x + 10, y - 35, lab)
    y -= fh + 16

    narrative = (p.get("narrative") or "").strip() or default_narrative(p)
    left_w = 177
    text_w = CW - left_w - 42 - 21
    st = ParagraphStyle("n", fontName="Helvetica", fontSize=10.5, leading=16)
    nh = Paragraph(narrative.replace("&", "&amp;"), st).wrap(text_w, 1000)[1]
    card_h = max(100, nh + 36)
    _dark(cv, M, y, CW, card_h)
    _spaced(cv, M + 21, y - 26, "RECOMMENDED RENEWAL", "Helvetica-Bold", 8, GOLD_LIGHT, 1.1)
    cv.setFont("Helvetica-Bold", 33); cv.setFillColor(colors.white); cv.drawString(M + 21, y - 60, money(c["ren"]))
    if c["inc"] is not None:
        verb = "Up" if c["inc"] >= 0 else "Down"
        cv.setFont("Helvetica", 9.5); cv.setFillColor(colors.HexColor("#CFCFCF"))
        cv.drawString(M + 21, y - 78, "%s %s from %s (%d%%)" % (verb, money(abs(c["inc"])), money(c["cur"]), round(abs(c["pct"]))))
    cv.setStrokeColor(colors.HexColor("#555555")); cv.setLineWidth(0.75)
    cv.line(M + 21 + left_w, y - 16, M + 21 + left_w, y - card_h + 16)
    _para(cv, narrative, M + 21 + left_w + 21, y - (card_h - nh) / 2, text_w, size=10.5,
          color=colors.HexColor("#E8E8E8"), leading=16)
    y -= card_h + 22

    _spaced(cv, M, y, "WHERE THE RENEWAL LANDS", "Helvetica-Bold", 9, GOLD_TEXT, 1.2)
    y = _scale(cv, y - 10, p) - 18

    comps = featured_comps(p)
    if comps:
        _spaced(cv, M, y, "CLOSEST COMPARABLE RENTALS", "Helvetica-Bold", 9, GOLD_TEXT, 1.2)
        cols = [(CW * 0.40, "L"), (CW * 0.16, "L"), (CW * 0.13, "R"), (CW * 0.15, "R"), (CW * 0.16, "R")]
        rows = []
        for cp in comps:
            bb = "%s / %s" % (fmt_int(cp.get("beds"), False), fmt_baths(cp.get("baths")))
            d = num(cp.get("distance_mi"))
            rows.append([cp.get("address", ""), bb, fmt_int(cp.get("sqft")),
                         ("%.2f mi" % d) if d is not None else "—", money(cp.get("rent"))])
        _table(cv, y - 4, cols, ["ADDRESS", "BED / BATH", "SQ FT", "DISTANCE", "RENT"], rows, row_h=30)
    _footer(cv, doc)


def build_pdf(doc, out_path):
    props = [p for p in doc.get("properties", []) if p.get("address")]
    if not props:
        raise ValueError("Add at least one property.")
    doc = dict(doc, properties=props)
    d = doc.get("data_date") or datetime.date.today().isoformat()
    try:
        doc["data_date_label"] = datetime.date.fromisoformat(d[:10]).strftime("%B %-d, %Y")
    except ValueError:
        doc["data_date_label"] = d
    cv = rl_canvas.Canvas(out_path, pagesize=letter)
    cv.setTitle("Renewal Analysis - %s" % (doc.get("owner_name") or "Owner"))
    cv.setAuthor("Doss & Spaulding Properties")
    _summary_page(cv, doc)
    for i, p in enumerate(props, 1):
        cv.showPage()
        _property_page(cv, doc, p, i, len(props))
    cv.save()
    return out_path


# ---------- email ----------
def email_draft(doc):
    props = [p for p in doc.get("properties", []) if p.get("address")]
    first = (doc.get("owner_name") or "").split(" ")[0] or "there"
    n = len(props)
    if n <= 3:
        subj = "12-Month Renewal Recommendations: " + ", ".join(p["address"] for p in props)
        if n == 1:
            subj = "12-Month Renewal Recommendation: " + props[0]["address"]
    else:
        subj = "12-Month Renewal Recommendations for %d of Your Properties" % n
    lines = ["Hi %s," % first, ""]
    if n == 1:
        lines.append("We pulled updated market rent data for %s, which is currently month-to-month. "
                     "It's renting well below market, and we'd like to offer the tenant a 12-month renewal at a higher rate." % props[0]["address"])
    else:
        lines.append("We pulled updated market rent data for your %d properties that are currently month-to-month. "
                     "All %d are renting well below market, and we'd like to offer each tenant a 12-month renewal at a higher rate."
                     % (n, n))
    lines += ["",
              "We know your goal is to keep %s in place for as long as possible, so we're not recommending a jump to full market rent. "
              "Instead, we suggest a moderate increase that closes part of the gap while keeping %s priced below anything comparable nearby. "
              "That way %s every reason to sign and stay, because %s find a similar home for less."
              % ("these tenants" if n > 1 else "this tenant", "each home" if n > 1 else "the home",
                 "the tenants have" if n > 1 else "the tenant has", "they won't"),
              "", "Based on comparable rentals near each property:" if n > 1 else "Based on comparable rentals nearby:", ""]
    cur_t = ren_t = 0
    for p in props:
        c = calc(p)
        cur_t += c["cur"] or 0; ren_t += c["ren"] or 0
        city = (p.get("city_line") or "").split(",")[0]
        head = "%s, %s" % (p["address"], city) if city else p["address"]
        s = "%s: Current rent is %s. Market range is %s. We recommend renewing at %s" % (
            head, money(c["cur"]), rng(c["lo"], c["hi"], " to "), money(c["ren"]))
        if c["below_lo"] is not None and c["below_lo"] > 0:
            s += ", still %s to %s below market." % (money(c["below_lo"]), money(c["below_hi"]))
        else:
            s += "."
        lines += [s, ""]
    diff = ren_t - cur_t
    if n > 1:
        lines.append("Together, these renewals would add %s a month, or %s a year. " % (money(diff), money(diff * 12)) +
                     "A 12-month term also gives you more stability, since on month-to-month any of these tenants could leave on short notice.")
    else:
        lines.append("This renewal would add %s a month, or %s a year. " % (money(diff), money(diff * 12)) +
                     "A 12-month term also gives you more stability, since on month-to-month the tenant could leave on short notice.")
    lines += ["",
              "Let us know if you're comfortable with %s or want to adjust %s. Once we have your approval, "
              "we'll send the renewal %s to the %s. The full comparable rent analysis is attached for your reference."
              % ("these numbers" if n > 1 else "this number", "any of them" if n > 1 else "it",
                 "offers" if n > 1 else "offer", "tenants" if n > 1 else "tenant"),
              "", "Best,", doc.get("prepared_by") or "Doss & Spaulding Properties"]
    return {"subject": subj, "body": "\n".join(lines)}
