# Doss & Spaulding — Company Tools Hub

A single internal web app where employees access all company tools from one place,
organized by task. One URL, one login, consistent branding.

## What's here
- Home dashboard (`/`) — tool cards grouped by workflow (Maintenance, Marketing, ...).
- Unit Turn Punchlist tool (`/punchlist/`) — the first tool, fully working.
- Make-Ready Inspection (`/makeready/`) — guided walkthrough that produces the punchlist.
- Shared team login (optional).

## Add a new tool (e.g. Listing Description Generator)
1. Create `tools/<yourtool>/__init__.py` that defines a Flask Blueprint `bp`
   (see `tools/punchlist/__init__.py` as the template) and a `META` dict.
2. In `app.py`: `from tools.<yourtool> import bp as <x>_bp, META as <X>_META`,
   `app.register_blueprint(<x>_bp)`, and add `<X>_META` to the right group in `TOOL_GROUPS`.
3. Put the tool's page(s) in `tools/<yourtool>/templates/`.
That's it — it shows up as a card and runs under its own path. No other plumbing.

## Run locally
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # enables checklist cleanup/grouping + reading checklist photos
# export APP_PASSWORD=yourteampassword     # optional shared login; unset = open
python app.py                               # http://localhost:5000
```

## Deploy on Render
- New + -> Blueprint -> pick this repo (reads render.yaml -> free Python service).
- Set secrets: `ANTHROPIC_API_KEY` (required), `APP_PASSWORD` (optional team password).
- One service, one URL for all tools. Point a custom domain (e.g. tools.dspropertiesnc.com) at it in Render -> Settings -> Custom Domains.

## Notes
- Tools output Word (.docx); open and Save As PDF if a PDF is needed.
- Cost: free Render instance + ~a cent or two of Anthropic usage per generation.

## Listing generator model
The listing tool uses `ANTHROPIC_MODEL` (default `claude-sonnet-4-5-20250929`); override with `LISTING_MODEL` if needed.

## Email buttons (punchlist)
The punchlist "Email a copy" buttons send the generated .docx as an attachment. Configure SMTP:
- `SMTP_HOST` (e.g. smtp.gmail.com), `SMTP_PORT` (587), `SMTP_USER` (sending mailbox), `SMTP_PASS` (app password), optional `SMTP_FROM`.
- For Google Workspace (dspropertiesnc.com): enable 2-Step Verification on the sending account and create an App Password, then use it as `SMTP_PASS`.
- If SMTP isn't set, the buttons return a clear "email not configured" message; downloads still work.
Recipients are fixed: info@, admin@, and John+Alina.

## Eviction Prep Packet (/eviction/)
Upload NC summary ejectment case documents (lease, AOC-CVM-201 complaint, AOC-CVM-100 summons incl. the
sheriff's return, tenant ledger, demand notice, SCRA declaration). Produces two Word downloads: a 1-2 page
courtroom quick-reference card and the full prep binder.

Money math: payments are applied to the OLDEST outstanding charge first (as the ledger does), then
  rent ask = accrued rent through the hearing date - payments applied to that rent (+ any prior unpaid rent)
  total ask = rent ask + court costs        (late/add-on fees excluded)
Both figures are shown: the accrued-through-court-date ask (lead) and the full-month alternative
(rent charged - paid), so the rep can follow the magistrate. Payments may be entered either as
type="payment" or as a negative amount. `landlord.article` controls "the Smith Trust" vs "Bartola Lisbon".
The allocation is printed in the packet, the ledger is cross-checked against the stated balance, and any
partial payment is flagged prominently. Optional `EVICTION_MODEL` env var overrides the model.

## Listing Input Sheet (/listing-input/)
Field staff capture property details (built from the marked-up Triad MLS Residential Rental Input Form:
struck items omitted, highlighted-and-not-struck items required). Conditional fields: Pool Features appear
only when Pool = Yes; Fireplace Location when fireplaces > 0; Garage description when spaces > 0; Unit #/floor
for Condominium/Townhouse/Duplex. "Lock Box Info" is relabeled **ShowMojo Box Serial #**.
Produces a branded PDF and emails it from `LISTING_FROM` (default listing-input@dspropertiesnc.com) with
one-click buttons for admin@, support@, info@, plus a custom address. Entries are saved in the browser as
you type; a Clear-all button (with confirmation) resets the sheet.

## Make-Ready Inspection (/makeready/)
A guided walkthrough for a less-experienced staff member, built from the hard-copy
Turn/Make-Ready Checklist. Flow: setup (address, inspector, access info, property profile)
→ one area per screen, each item marked **OK / Needs attention / N/A** with a plain-English
hint → note + photos on anything flagged → review screen → punchlist.

- `checklist.py` — the master schema. 24 base areas, ~130 base items, every item carries a
  `hint`. Sections and individual items can be gated on a profile key (`when` / 3rd tuple
  element); `repeat` expands Bedroom 1..N and Bathroom 1..N. Item keys are stable strings so
  a walkthrough saved on someone's phone survives a deploy. **Edit this file to add, remove
  or reword checklist items** — the UI and the document both follow it.
- `structuring.py` — turns flags into repair instructions ("Toilet working & flappers good"
  + "runs constantly" → "Replace the toilet flapper and fill valve"). Without
  `ANTHROPIC_API_KEY` it falls back to listing items exactly as flagged, grouped by room —
  still a usable document.
- Output uses the shared punchlist builder, so the document is identical in style to
  `/punchlist/`. Photos attach per flagged item but print in the **end-of-section grid**
  (Interior photos after Interior, Exterior after Exterior) with a small caption naming the
  room and item they came from.
- Same email buttons as the punchlist tool (info@, admin@, john@, alina@, plus a custom
  address), sent from `PUNCHLIST_FROM`.
- Progress autosaves to the phone after every tap and photos upload one at a time, so the
  iOS camera page-reload can't lose a walkthrough. On return the setup screen offers
  "Pick up where I left off".

## IMPORTANT — the service must stay on a PAID Render instance
Render blocks outbound SMTP (ports 25 / 465 / 587) on **free** web services, so the email buttons
will hang ("Sending..." forever) if the service is on the Free instance. `render.yaml` pins
`plan: starter` for this reason — do not change it back to `free` while email is in use.
