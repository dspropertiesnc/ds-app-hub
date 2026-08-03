# Doss & Spaulding — Company Tools Hub

A single internal web app where employees access all company tools from one place,
organized by task. One URL, one login, consistent branding.

## What's here
- Home dashboard (`/`) — tool cards grouped by workflow (Maintenance, Marketing, ...).
- Unit Turn Punchlist tool (`/punchlist/`) — the first tool, fully working.
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
