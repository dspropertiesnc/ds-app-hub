"""Draws the invoice PDF (page 1: invoice; following pages: job photos, 4 per page)."""
import os, datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image as RLImage, PageBreak, Flowable)
from PIL import Image as PILImage, ImageOps

GOLD = colors.HexColor("#444444")   # neutral accent: the PDF carries the vendor's name, not D&S branding
INK = colors.HexColor("#1a1a1a")
LINE = colors.HexColor("#dddddd"); GRAY = colors.HexColor("#555555")
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))
W = 7.3 * inch

S = {
    "title": ParagraphStyle("t", fontName="Times-Bold", fontSize=24, leading=28, textColor=INK),
    "co": ParagraphStyle("co", fontName="Times-Roman", fontSize=9.5, leading=12.5, alignment=2),
    "lbl": ParagraphStyle("lbl", fontName="Helvetica", fontSize=7.5, leading=10, textColor=GOLD),
    "v": ParagraphStyle("v", fontName="Times-Roman", fontSize=10.5, leading=13.5),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white),
    "thr": ParagraphStyle("thr", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, alignment=2),
    "td": ParagraphStyle("td", fontName="Times-Roman", fontSize=10.5, leading=13.5),
    "tdr": ParagraphStyle("tdr", fontName="Times-Roman", fontSize=10.5, leading=13.5, alignment=2),
    "tot": ParagraphStyle("tot", fontName="Times-Bold", fontSize=10.5, leading=13.5, alignment=2),
    "note": ParagraphStyle("note", fontName="Times-Roman", fontSize=9, leading=12, textColor=GRAY),
}


def esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def money(n):
    n = float(n or 0)
    s = "${:,.2f}".format(abs(n))
    return "(%s)" % s if n < 0 else s


def phone(p):
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    return "(%s) %s-%s" % (d[:3], d[3:6], d[6:]) if len(d) == 10 else str(p or "")


def us_date(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%m/%d/%Y")
    except ValueError:
        return str(iso or "")


class Stamp(Flowable):
    """Tilted outlined stamp, e.g. PAID 10/08/2026."""
    def __init__(self, text, color=GOLD):
        super().__init__()
        self.text, self.color = text, color
        self.width, self.height = 2.4 * inch, 0.55 * inch

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(4, 6)
        c.rotate(5)
        c.setStrokeColor(self.color); c.setFillColor(self.color); c.setLineWidth(2.2)
        tw = c.stringWidth(self.text, "Helvetica-Bold", 15)
        c.rect(0, 0, tw + 22, 26, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(11, 8, self.text)
        c.restoreState()


def _block(label, lines):
    body = "<br/>".join(esc(x) for x in lines if x)
    return [Paragraph(label.upper(), S["lbl"]), Paragraph(body or "&nbsp;", S["v"])]


def _photo(path, w, h):
    """Photo scaled to fit a w x h box, rotated per EXIF, saved as a temp JPEG."""
    try:
        im = ImageOps.exif_transpose(PILImage.open(path)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((1400, 1400))
    out = path + ".pdf.jpg"
    im.save(out, "JPEG", quality=82)
    r = min(w / im.width, h / im.height)
    return RLImage(out, width=im.width * r, height=im.height * r)


def build_pdf(doc, photo_paths, out_path):
    pdf = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            title="Invoice %s" % doc["number"], author="")
    el = []
    paid = doc["paid"]

    # ---- header ----
    left = [Paragraph("PAID INVOICE" if paid else "INVOICE", S["title"])]
    if paid:
        left.append(Stamp("PAID %s" % us_date(doc["paid_date"]) if doc.get("paid_date") else "PAID"))
    # vendor letterhead (no D&S logo): the vendor issues the invoice, D&S is the customer
    v = doc["vendor"]
    vend = ["<b>%s</b>" % esc(v.get("name"))] + [esc(x) for x in (v.get("address"), v.get("city_line"),
                                                                   phone(v.get("phone"))) if x]
    right = [Paragraph("<br/>".join(vend), S["co"])]
    head = Table([[left, right]], colWidths=[W * 0.55, W * 0.45])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                              ("LINEBELOW", (0, 0), (-1, 0), 2.5, GOLD)]))
    el += [head, Spacer(1, 16)]

    # ---- vendor / service / details ----
    s = doc["service"]
    customer = ["Doss & Spaulding Properties LLC"]
    if s.get("owner"):
        customer += ["Property Manager for", s["owner"]]
    details = ["Invoice #: %s" % doc["number"]]
    if doc.get("wo_number"):
        details.append("Work Order: #%s" % doc["wo_number"])
    if doc.get("bill_id"):
        details.append("Reference: Bill #%s" % doc["bill_id"])
    if doc.get("service_date"):
        details.append("Service Date: %s" % us_date(doc["service_date"]))
    if paid and doc.get("paid_date"):
        details.append("Paid: %s" % us_date(doc["paid_date"]))
        if doc.get("paid_method"):
            details.append("Method: %s" % doc["paid_method"])
    elif not paid and doc.get("due_date"):
        details.append("Due: %s" % us_date(doc["due_date"]))
    svc = [s.get("address"), s.get("city_line")]
    if s.get("tenant"):
        svc.append("Tenant: %s" % s["tenant"])
    grid = Table([[_block("Paid By" if paid else "Bill To", customer),
                   _block("Service Location", svc),
                   _block("Details", details)]], colWidths=[W / 3] * 3)
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
    el += [grid, Spacer(1, 20)]

    # ---- line items ----
    show_qty = any(float(i.get("qty") or 1) != 1 for i in doc["items"])
    if show_qty:
        rows = [[Paragraph("Description", S["th"]), Paragraph("Qty", S["thr"]),
                 Paragraph("Rate", S["thr"]), Paragraph("Amount", S["thr"])]]
        cw = [W - 3.0 * inch, 0.7 * inch, 1.1 * inch, 1.2 * inch]
    else:
        rows = [[Paragraph("Description", S["th"]), Paragraph("Amount", S["thr"])]]
        cw = [W - 1.4 * inch, 1.4 * inch]
    for i in doc["items"]:
        amt = float(i.get("qty") or 1) * float(i.get("rate") or 0)
        r = [Paragraph(esc(i.get("description")), S["td"])]
        if show_qty:
            q = float(i.get("qty") or 1)
            r += [Paragraph(("%g" % q), S["tdr"]), Paragraph(money(i.get("rate")), S["tdr"])]
        r.append(Paragraph(money(amt), S["tdr"]))
        rows.append(r)
    n_items = len(rows)
    pad = [""] * (len(cw) - 2)   # label sits in column 0 and spans to the amount column
    rows.append([Paragraph("Total", S["tot"])] + pad + [Paragraph(money(doc["total"]), S["tot"])])
    if paid:
        lab = "Amount Paid (%s)" % us_date(doc["paid_date"]) if doc.get("paid_date") else "Amount Paid"
        rows.append([Paragraph(lab, S["tot"])] + pad + [Paragraph(money(-doc["total"]), S["tot"])])
        rows.append([Paragraph("Balance Due", S["tot"])] + pad + [Paragraph(money(0), S["tot"])])
    else:
        rows.append([Paragraph("Balance Due", S["tot"])] + pad + [Paragraph(money(doc["total"]), S["tot"])])
    t = Table(rows, colWidths=cw)
    style = [("BACKGROUND", (0, 0), (-1, 0), INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
             ("LINEBELOW", (0, 1), (-1, n_items - 1), 0.5, LINE)]
    if len(cw) > 2:   # total labels span the description/qty/rate columns
        for r in range(n_items, len(rows)):
            style.append(("SPAN", (0, r), (len(cw) - 2, r)))
    t.setStyle(TableStyle(style))
    el.append(t)

    # ---- notes ----
    note = (doc.get("notes") or "").strip()
    if paid and doc.get("paid_date") and not note:
        note = "Paid in full on %s." % us_date(doc["paid_date"])
    if photo_paths:
        note = (note + " Job photos attached.").strip()
    if note:
        nt = Table([[Paragraph(esc(note).replace("\n", "<br/>"), S["note"])]], colWidths=[W])
        nt.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 8)]))
        el += [Spacer(1, 26), nt]

    # ---- photos, 4 per page ----
    imgs = [im for im in (_photo(p, 3.55 * inch, 4.2 * inch) for p in photo_paths) if im]
    for start in range(0, len(imgs), 4):
        el.append(PageBreak())
        label = "Job Photos" + (": Work Order #%s" % doc["wo_number"] if doc.get("wo_number") else "")
        el += [Paragraph(label.upper(), S["lbl"]), Spacer(1, 6)]
        chunk = imgs[start:start + 4]
        cells = [chunk[i:i + 2] + [""] * (2 - len(chunk[i:i + 2])) for i in range(0, len(chunk), 2)]
        g = Table(cells, colWidths=[W / 2] * 2, rowHeights=[4.4 * inch] * len(cells))
        g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el.append(g)

    pdf.build(el)
    return out_path
