# AI Usage Documentation (AI_USAGE.md)

## Summary
I used AI coding assistance (ChatGPT) as a development accelerator for:
- Architecture planning and refactoring strategy
- Debugging integration issues between Vapi webhooks/tools and Django
- Generating boilerplate for the middleware wrapper API endpoints
- Drafting documentation (README, integration guide, troubleshooting)

I did **not** blindly copy/paste outputs into production. All changes were applied incrementally and validated by manual testing (curl, Vapi test calls, Django logs, HubSpot updates).

---

## Tools Used
- **ChatGPT** (AI assistant) for code suggestions, architecture discussion, and documentation drafting.
- Manual verification tools:
  - `curl` for endpoint testing (`/api/leads`, `/api/calls/{call_id}/summary`)
  - Vapi Dashboard call logs + webhook logs for delivery validation
  - Django server logs/tracebacks for error diagnosis
  - HubSpot contact record inspection for CRM sync validation
  - ngrok to expose localhost for Vapi webhook delivery

---

## Where AI Was Used (Concrete Examples)

### 1) Architecture and Refactor Plan
AI was used to propose a layered architecture and migration path:
- `crm/webhook/` → event ingestion only
- `crm/services/` → business rules (qualification, persistence)
- `crm/api/` → wrapper API layer (abstraction + auth)
- `crm/services/hubspot.py` → HubSpot adapter

**Human decisions:**  
I chose to implement a stepwise migration (instead of a big-bang rewrite) to reduce regression risk and keep a working system at each stage.

---

### 2) Debugging Vapi Tool Call / Email Capture Issues
AI helped identify root causes and propose fixes. Key issues included:
- **Call ID mismatch**: Tool calls used a stale/hardcoded `callId` (e.g., `"12345"`) instead of the Vapi call UUID.
- **Untrusted model arguments**: The model should never be trusted to provide call identifiers; call ID must come from webhook metadata.
- **Transcript fallback corruption**: Regex extraction from transcripts can silently produce incorrect emails (e.g., `n@gmail.com`).

**Resulting actions taken:**
- Ensured confirmed email is stored as `ConfirmedEmail(call_id → email)` from tool calls.
- Removed transcript-based email fallback to prevent data corruption.
- Verified tool call payload and persistence via logs and Django ORM queries.

---

### 3) Webhook Reliability Fixes
AI suggested defensive webhook handling patterns:
- Return 200 for non-POST requests (health checks / browser hits)
- Safely parse JSON payloads:
  - `json.loads(request.body.decode("utf-8") or "{}")`

**Manual verification:**
- Confirmed Vapi webhook logs returned `200` after fix.
- Confirmed Django logs show `end-of-call-report` ingestion.

---

### 4) Middleware Wrapper API Endpoints
AI generated initial boilerplate for the wrapper API required by the assignment:
- `POST /api/leads`
- `GET /api/leads/{id}`
- `PATCH /api/leads/{id}`
- `GET /api/leads` with filters
- `POST /api/calls/{call_id}/summary`

**Human review & adjustments:**
- Ensured API key auth (`X-API-KEY`) is enforced
- Ensured database constraints are respected (e.g., `disqualification_reason` cannot be `None`)
- Ensured call summary is safe for TextField (dict → JSON string)

**Manual verification:**
- `curl` tests for each endpoint
- Confirmed DB writes and HubSpot updates

---

### 5) Documentation
AI was used to draft:
- README structure and setup instructions
- Troubleshooting guide
- Customer integration guide
- Executive summary
- Vapi assistant configuration export text

**Human review:**
- Updated text to match the actual implemented endpoints and observed logs.

---

## What Was NOT Delegated to AI
- Final architecture choice and sequencing of migration
- Validation of webhook delivery (ngrok/Vapi logs)
- Real integration testing with HubSpot
- Verification of database persistence and constraints
- Final decision to remove transcript fallback for identity fields
- Security decisions (API key boundaries, where to enforce auth)

---

## Validation / Testing Performed
- Manual `curl` tests:
  - `POST /api/leads` (success + auth failure)
  - `GET /api/leads` with filters
  - `PATCH /api/leads/{id}`
  - `POST /api/calls/{call_id}/summary` (string + dict summary)
- Vapi test calls verifying:
  - Tool endpoint hit (`confirm_email_tool`)
  - `ConfirmedEmail` record created with correct call UUID
  - Webhook ingested `end-of-call-report`
  - Middleware endpoint called from webhook (`POST /api/leads`)
  - HubSpot contact created/updated accordingly
- Django ORM checks:
  - `ConfirmedEmail.objects.order_by("-created_at").first()`
  - `Call.objects.order_by("-created_at").first()`
  - `Lead.objects.filter(email=...).first()`

---

## Notes on Responsible Use
AI assistance was used as a productivity tool for:
- generating scaffolding
- exploring alternatives
- catching common integration edge cases

All AI output was treated as a draft. I validated functionality using live calls, logs, and database checks to ensure correctness.

---

## Contact
If you have questions about how AI was used or how to reproduce tests, please reach out and I can provide exact call IDs, logs, and sample payloads used during validation.
