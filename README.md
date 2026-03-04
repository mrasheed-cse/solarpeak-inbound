
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

**Environment Variables**
 Required:
 - HUBSPOT_ACCESS_TOKEN
   HubSpot Private App token used to create/update contacts.

 - INTERNAL_API_KEY
  API key used to protect internal wrapper API endpoints and authenticate webhook → middleware requests.

 Recommended additional Django env vars:
 - DJANGO_SECRET_KEY
 - DEBUG (true/false)
 - ALLOWED_HOSTS (in dev you can use *, in prod set your domain)

Example .env:
  HUBSPOT_ACCESS_TOKEN=pat-xxxxxxxxxxxxxxxxxxxxxxxx
  INTERNAL_API_KEY=solarpeak-internal-key
  DEBUG=true
  ALLOWED_HOSTS=*
