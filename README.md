
# SolarPeak Inbound Qualification (Vapi + Django + HubSpot)

This project implements an AI-powered inbound call qualification system for SolarPeak Solutions. It uses Vapi.ai for real-time voice conversations and synchronizes qualified/disqualified leads into HubSpot via a secure middleware API abstraction layer.

---

## Architecture Overview

### High-level flow

```text
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
