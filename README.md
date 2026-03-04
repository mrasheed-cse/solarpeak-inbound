
# SolarPeak Inbound Qualification (Vapi + Django + HubSpot)

This project implements an AI-powered inbound call qualification system for SolarPeak Solutions. It uses Vapi.ai for real-time voice conversations and synchronizes qualified/disqualified leads into HubSpot via a secure middleware API abstraction layer.

### High-level flow

Caller
  ↓
Vapi Voice Agent
  ↓
Webhook Layer (crm/webhook/views.py)
  ↓
Service Layer (crm/services/*)
  ↓
Middleware API (crm/api/*)  [API key protected]
  ↓
HubSpot CRM

**Key design decisions**
Deterministic email capture (tool-only): Email is captured via a Vapi tool call and stored as ConfirmedEmail(call_id → email). The system does not parse email from transcripts to avoid STT corruption.
CRM abstraction: The webhook calls POST /api/leads (middleware). HubSpot integration is isolated in crm/services/hubspot.py.
Separation of concerns: Webhook ingestion, business logic, middleware API, and CRM adapter are separate modules.

**Requirements**
 - Python 3.11+ recommended
 - Django 4.x/5.x
 - HubSpot private app access token
 - Vapi assistant configured with Server URL and tools
 - ngrok for local development webhook testing (optional but recommended)

**Setup (Local)**
1) Create and activate a virtualenv

For (macOS/Linux)
  python -m venv .venv
  source .venv/bin/activate

Windows (PowerShell)
  python -m venv .venv
  .venv\Scripts\Activate.ps1

2) Install dependencies
  pip install -r requirements.txt

3) Configure environment variables
  Create a .env file (or set these in your shell). See Environment Variables below.

4) Run migrations
  python manage.py migrate

5) Start Django
  python manage.py runserver 8000

**Webhook Exposure (Local with ngrok)**
Vapi cannot call localhost. Use ngrok to expose your local server:
  ngrok http 8000

You’ll get a public URL like:
  https://abcd-1234.ngrok-free.app

Set your Vapi Assistant Server URL to:
  https://abcd-1234.ngrok-free.app/vapi/webhook/

In Vapi, enable Server Messages:
  end-of-call-report (required)

**Environment Variables** <br>
 <ins>Required:</ins> <br>
   - HUBSPOT_ACCESS_TOKEN <br>
     HubSpot Private App token used to create/update contacts. <br>
   - INTERNAL_API_KEY <br>
     API key used to protect internal wrapper API endpoints and authenticate webhook → middleware requests. <br>

 <ins>Recommended additional Django env vars:</ins> <br>
 - DJANGO_SECRET_KEY
 - DEBUG (true/false)
 - ALLOWED_HOSTS (in dev you can use *, in prod set your domain)

<ins>Example .env:</ins> <br>
&nbsp;&nbsp;&nbsp;&nbsp;HUBSPOT_ACCESS_TOKEN=pat-xxxxxxxxxxxxxxxxxxxxxxxx <br>
&nbsp;&nbsp;&nbsp;&nbsp;INTERNAL_API_KEY=solarpeak-internal-key <br>
&nbsp;&nbsp;&nbsp;&nbsp;DEBUG=true <br>
&nbsp;&nbsp;&nbsp;&nbsp;ALLOWED_HOSTS=* <br>

<H3>Wrapper API Endpoints (Middleware)</H3>

All endpoints require: X-API-KEY: <INTERNAL_API_KEY><br><br>
**Create/Update lead** <br>
POST /api/leads <br>
Example: <br>
curl -s -X POST http://localhost:8000/api/leads \ 
  -H "Content-Type: application/json" \
  -H "X-API-KEY: solarpeak-internal-key" \
  -d '{"email":"demo@example.com","qualification_result":"Qualified","current_step":"collecting_contact","ended_reason":"customer-ended-call"}' <br>

**List leads (with filtering)** <br>
GET /api/leads?status=qualified&qualification_result=Qualified&limit=50 <br>

**Retrieve lead** <br>
GET /api/leads/{id} <br>

**Update lead** <br>
PATCH /api/leads/{id} <br>

**Store call summary**
POST /api/calls/{call_id}/summary <br>
Example: <br>
curl -s -X POST http://localhost:8000/api/calls/<CALL_ID>/summary \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: solarpeak-internal-key" \
  -d '{"summary":{"short":"Qualified lead","callback":"tomorrow morning"}}' <br>

<H3>Vapi Tool Endpoints</H3>
The Django backend exposes tool endpoints (configured in Vapi tools): <br>
 - POST /vapi/tool/confirm-email/ <br>
 - POST /vapi/tool/lookup-lead-state/ <br>
These are invoked by the assistant during the call. <br>

</H3>Common Troubleshooting** </H3>
<ins>Webhook not firing</ins> <br>
 - Ensure ngrok is running <br>
 - Ensure Vapi Server URL is correct and includes /vapi/webhook/ <br>
 - Ensure end-of-call-report is enabled <br>
 - Ensure Django route matches exactly (trailing slash) <br>

<ins> Webhook 500 error </ins> <br>
 - Check Django traceback <br>
 - Ensure non-POST requests return 200 (health checks / browser hits) <br>
 - Ensure INTERNAL_API_KEY is set <br>
 - Ensure middleware endpoints are reachable locally <br>
 
<ins> Middleware 401 </ins> <br>
 - Ensure X-API-KEY header matches INTERNAL_API_KEY <br>
 - HubSpot not updating <br>
 - Confirm HubSpot token and scopes <br>
 - Verify property names exist in HubSpot <br>
 - Check HubSpot API responses/logs <br>
