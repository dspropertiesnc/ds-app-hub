"""Renders the completed listing input sheet as a branded PDF."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image as RLImage, KeepTogether)
from .fields import SECTIONS

ACCENT = colors.HexColor("#a78147"); SUB = colors.HexColor("#efe7d9")
DARK = colors.HexColor("#5c4522"); LINE = colors.HexColor("#e6e0d6")
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.normpath(os.path.join(HERE, "..", "..", "static", "logo.png"))

def address_line(v):
    parts = [v.get("street_no"), v.get("pre_dir"), v.get("street_name"), v.get("street_type"), v.get("post_dir")]
    line = " ".join(p for p in parts if p)
    if v.get("unit_no"):
        line += " #%s" % v["unit_no"]
    tail = ", ".join(p for p in [v.get("city"), v.get("zip")] if p)
    zip4 = ("-%s" % v["zip4"]) if v.get("zip4") else ""
    return ("%s, %s%s" % (line, tail, zip4)).strip(", ")

def _val(f, values):
    v = values.get(f["k"])
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if str(x).strip())
    return str(v).strip()

def build_pdf(values, out_path, missing_required=None):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=14, textColor=ACCENT,
                        alignment=0, spaceAfter=0, leading=16)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                         textColor=colors.HexColor("#666666"), spaceAfter=2)
    band = ParagraphStyle("band", parent=styles["Normal"], fontSize=9.5,
                          textColor=colors.white, fontName="Helvetica-Bold")
    lbl = ParagraphStyle("lbl", parent=styles["Normal"], fontSize=8.4, textColor=DARK,
                         fontName="Helvetica-Bold", leading=10)
    val = ParagraphStyle("val", parent=styles["Normal"], fontSize=8.4, leading=10)

    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.45*inch, bottomMargin=0.45*inch,
                            leftMargin=0.6*inch, rightMargin=0.6*inch, title="Listing Input Sheet")
    W = 7.3*inch
    el = []
    logo = ""
    if os.path.exists(LOGO):
        try: logo = RLImage(LOGO, width=1.5*inch, height=1.5*inch*303/1009)
        except Exception: logo = ""
    addr = address_line(values) or "New listing"
    head = Table([[Paragraph("Listing Input Sheet &mdash; %s" % addr, h1), logo]],
                 colWidths=[W-1.7*inch, 1.7*inch])
    head.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ALIGN", (1,0), (1,0), "RIGHT"),
                              ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0)]))
    el.append(head)
    meta = "Doss &amp; Spaulding Properties"
    if values.get("completed_by"):
        meta += " &nbsp;|&nbsp; completed by %s" % values["completed_by"]
    if values.get("_date"):
        meta += " &nbsp;|&nbsp; %s" % values["_date"]
    el.append(Paragraph(meta, sub)); el.append(Spacer(1, 5))

    if missing_required:
        warn = Table([[Paragraph("<b>Missing required fields:</b> " + ", ".join(missing_required), val)]],
                     colWidths=[W])
        warn.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#fbf3e2")),
                                  ("BOX",(0,0),(-1,-1),0.8,colors.HexColor("#e6cfa0")),
                                  ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                                  ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        el.append(warn); el.append(Spacer(1, 5))

    def band_row(txt):
        t = Table([[Paragraph(txt.upper(), band)]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),ACCENT), ("LEFTPADDING",(0,0),(-1,-1),6),
                               ("TOPPADDING",(0,0),(-1,-1),2), ("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        return t

    for sec in SECTIONS:
        rows = []
        for f in sec["fields"]:
            v = _val(f, values)
            if not v:
                continue
            rows.append([Paragraph(f["l"], lbl), Paragraph(v.replace("&", "&amp;"), val)])
        if not rows:
            continue
        t = Table(rows, colWidths=[2.15*inch, W-2.15*inch])
        t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                               ("LINEBELOW",(0,0),(-1,-2),0.3,LINE),
                               ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, colors.HexColor("#faf7f2")]),
                               ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
                               ("TOPPADDING",(0,0),(-1,-1),2), ("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        el.append(Spacer(1, 4))
        el.append(KeepTogether([band_row(sec["name"]), Spacer(1, 1), t]))

    el.append(Spacer(1, 12))
    el.append(Paragraph("Field-collected listing data for MLS / Rentvine entry. Verify anything marked "
                        "unclear before publishing.", ParagraphStyle(
                            "disc", parent=val, fontSize=7.5, textColor=colors.HexColor("#888888"),
                            fontName="Helvetica-Oblique")))
    doc.build(el)
    return out_path

def text_summary(values):
    """Compact plain-text version for the email body."""
    lines = ["Listing Input Sheet — %s" % (address_line(values) or "New listing")]
    if values.get("completed_by"):
        lines.append("Completed by: %s" % values["completed_by"])
    lines.append("")
    for sec in SECTIONS:
        block = []
        for f in sec["fields"]:
            v = _val(f, values)
            if v:
                block.append("  %s: %s" % (f["l"], v))
        if block:
            lines.append(sec["name"].upper())
            lines.extend(block)
            lines.append("")
    return "\n".join(lines)
