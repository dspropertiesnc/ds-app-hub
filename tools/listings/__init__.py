import os
from flask import Blueprint, request, jsonify, render_template, send_from_directory

bp = Blueprint("listings", __name__, url_prefix="/listings", template_folder="templates")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

META = {"name": "Listing Description Generator", "desc": "Turn property details into a polished listing headline + description.",
        "url": "/listings/", "group": "Marketing", "icon": "\U0001F3E0", "ready": True}

MODEL = os.getenv("LISTING_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"))

QUALIFICATIONS = (
    "\nQualification Requirements:\n"
    "Each occupant 18+ must submit a separate application and consent to credit, background, and rental history checks\n"
    "Combined gross income must be at least 3x the monthly rent\n"
    "Credit score of 650+ preferred (may consider lower with extra deposit)\n"
    "No prior evictions or unpaid landlord judgments\n"
    "Non-smoking only\n"
    "Max occupancy of 2 persons per bedroom\n"
    "Application fee is $70 per applicant and NON-REFUNDABLE, even if denied occupancy\n"
    "Properties that allow pets or housing vouchers will state this in the listing"
)
QUAL_LENGTH = len(QUALIFICATIONS)
MAX_TOTAL = 1200
MAX_DESC = MAX_TOTAL - QUAL_LENGTH

SYSTEM_PROMPT = f"""You write rental listing descriptions for Doss & Spaulding Properties, a property management company in Greensboro, NC.

Your job is to take raw property details and produce TWO things:
1. A short, punchy headline for the listing (max 80 characters)
2. A polished, natural-sounding listing description

It must sound like a real person wrote it - no corporate fluff, no AI cliches, no filler phrases like "nestled," "boasting," "featuring," "Don't miss this," "perfect for," "this stunning," "a must-see," or "ideal for." Just clear, honest, appealing copy.

CRITICAL - what NOT to mention in the description body:
- DO NOT state the number of bedrooms or bathrooms (e.g. "3-bedroom," "two bath," "3BR/2BA"). The listing platform displays these separately.
- DO NOT spell out the property type (e.g. do NOT write "single-family home," "townhome," "duplex," "condo"). The platform shows that separately too. You may use natural language like "the home" or "the place" when needed.
- DO NOT include the rent price or monthly cost anywhere.
- Treat the property_type / beds / baths inputs as context that informs your tone and word choices, but never restate them.

What TO do - use the freed-up character budget to maximize useful detail about:
- Neighborhood and location feel (what's nearby, the vibe of the street/area)
- Interior features, finishes, condition, and recent updates
- Exterior and outdoor details (yard, parking, porch, garage, etc.)
- Area highlights (walkability, proximity to UNCG / shops / dining / highways)
- Lease terms, utility responsibility, pet policy, and similar practical details from the user's Additional notes

Rules:
- The description body must be {MAX_DESC} characters or fewer (NOT counting the qualifications section). Pack it with substance.
- The headline must be 80 characters or fewer. It should highlight the most compelling aspect of the property - location, condition, a standout feature, or the general vibe. Keep it natural and specific, not generic.
- Write the description in flowing sentences - no bullet points or headers.
- Lead with neighborhood/location and the property's most compelling feature.
- Weave interior features, condition/updates, outdoor details, and area highlights naturally through the middle.
- The Additional notes field contains practical terms (lease length, utility responsibility, pet policy, included services, etc.) that MUST be incorporated at the end of the description body, as the final sentence or two. Do not omit this information - it is required practical detail. Phrase it naturally, not as a bullet list.
- If an availability date is provided, mention it near the end as well.
- Do not fabricate details that weren't given.
- Do not include any qualifications text - that will be appended separately.

Return your response in EXACTLY this format (no extra text):
HEADLINE: <your headline here>
DESCRIPTION: <your description here>"""

FIELDS = [("property_type","Property type"),("beds","Bedrooms"),("baths","Bathrooms"),
          ("available","Available"),("neighborhood","Neighborhood/location"),
          ("interior","Interior features"),("exterior","Exterior/outdoor features"),
          ("area","Area highlights"),("extras","Additional notes")]

@bp.route("/")
def index():
    return render_template("listings.html")

@bp.route("/<path:asset>")
def static_asset(asset):
    if asset in ("style.css","app.js","logo-light.svg","logo-dark.svg"):
        return send_from_directory(ASSETS, asset)
    return "Not found", 404

@bp.route("/generate", methods=["POST"])
def generate():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"detail": "Server has no ANTHROPIC_API_KEY set."}), 500
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    data = request.get_json(silent=True) or {}
    parts = []
    for key, label in FIELDS:
        val = (data.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    user_prompt = "\n".join(parts)
    try:
        message = client.messages.create(model=MODEL, max_tokens=512,
                                          system=SYSTEM_PROMPT,
                                          messages=[{"role": "user", "content": user_prompt}])
        raw = message.content[0].text.strip()
    except Exception as e:
        return jsonify({"detail": f"Generation failed: {e}"}), 502
    headline, description = "", raw
    if "HEADLINE:" in raw and "DESCRIPTION:" in raw:
        h = raw.index("HEADLINE:") + len("HEADLINE:")
        d = raw.index("DESCRIPTION:")
        headline = raw[h:d].strip()
        description = raw[d + len("DESCRIPTION:"):].strip()
    elif "HEADLINE:" in raw:
        headline = raw.split("HEADLINE:", 1)[1].strip(); description = ""
    if len(headline) > 80:
        headline = headline[:80].rsplit(" ", 1)[0]
    if len(description) > MAX_DESC:
        description = description[:MAX_DESC].rsplit(" ", 1)[0]
    full = description + QUALIFICATIONS
    return jsonify({"headline": headline, "headline_chars": len(headline),
                    "description": description, "qualifications": QUALIFICATIONS,
                    "full_listing": full, "desc_chars": len(description),
                    "qual_chars": QUAL_LENGTH, "total_chars": len(full)})
