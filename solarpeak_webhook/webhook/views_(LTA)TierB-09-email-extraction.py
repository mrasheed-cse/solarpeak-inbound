import json
import re
import logging
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crm.models import Lead, Call, ConfirmedEmail

logger = logging.getLogger(__name__)

# =========================================================
# EMAIL EXTRACTION (fallback only; primary is ConfirmedEmail)
# =========================================================

EMAIL_REGEX = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

def extract_email_from_transcript(transcript: str):
    """
    Fallback email extraction from transcript.
    We keep it, but prefer callId->confirmed email via ConfirmedEmail model.
    """
    if not transcript:
        return None

    text = transcript.lower()
    text = text.replace(" at ", "@")
    text = text.replace(" dot ", ".")
    text = text.replace(" g mail ", " gmail ")
    text = re.sub(r"[^a-z0-9@._+\- ]", " ", text)

    match = EMAIL_REGEX.search(text)
    return match.group(0).lower() if match else None


# =========================================================
# QUALIFICATION + STEP DETECTION
# =========================================================

def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"
    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"
    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    # Explicit qualified closing signals only
    if "specialist will contact you" in t or "we look forward to helping you go solar" in t:
        return "Qualified", ""

    return "Unknown", ""


def detect_current_step(transcript: str) -> str:
    t = (transcript or "").lower()

    if "homeowner" not in t:
        return "homeownership"
    if "electricity bill" not in t:
        return "bill"
    if "within the next 12 months" not in t:
        return "timeline"
    if "full name" in t or "phone number" in t or "property address" in t or "email" in t:
        return "collecting_contact"

    return "unknown"


# =========================================================
# HUBSPOT UPSERT (Create then PATCH on 409)
# =========================================================

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {getattr(settings, 'HUBSPOT_ACCESS_TOKEN', '')}",
    "Content-Type": "application/json",
}

def hubspot_create_contact(properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts"
    r = requests.post(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def hubspot_update_contact(contact_id: str, properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}"
    r = requests.patch(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def parse_existing_contact_id(conflict_body: dict) -> str | None:
    msg = (conflict_body or {}).get("message", "") or ""
    m = re.search(r"Existing ID:\s*(\d+)", msg)
    return m.group(1) if m else None

def hubspot_upsert_contact(properties: dict):
    status, body = hubspot_create_contact(properties)
    if status == 409:
        existing_id = parse_existing_contact_id(body)
        if existing_id:
            status2, body2 = hubspot_update_contact(existing_id, properties)
            return status2, body2
    return status, body


# =========================================================
# TOOL HELPERS (parse arguments & tool call id)
# =========================================================

def _get_tool_calls(message: dict):
    return message.get("toolCallList") or message.get("toolCalls") or []

def _parse_tool_args(args):
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            return json.loads(args)
        except Exception:
            return {}
    return {}


# =========================================================
# TOOL ENDPOINT: confirm_email (email + callId)
# =========================================================

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from crm.models import Lead, ConfirmedEmail

logger = logging.getLogger(__name__)

@csrf_exempt
def confirm_email_tool(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        logger.exception("confirm_email_tool: invalid JSON")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message = payload.get("message", {}) or {}

    # ✅ Real call id from payload (source of truth)
    call_id_from_payload = (message.get("call") or {}).get("id") or ""

    # ✅ Vapi may send either toolCallList or toolCalls
    tool_calls = message.get("toolCallList") or message.get("toolCalls") or []

    results = []

    for tc in tool_calls:
        # ✅ Vapi uses `id` as the tool call id
        tool_call_id = tc.get("toolCallId") or tc.get("id")
        fn = tc.get("function") or {}
        args = fn.get("arguments") or {}

        # ✅ arguments might be JSON string
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        email = (args.get("email") or "").strip().lower()
        call_id_arg = (args.get("callId") or "").strip()

        # ✅ compute final call_id safely
        call_id = call_id_arg
        if (not call_id) or (call_id == "current_call_id"):
            call_id = call_id_from_payload

        if not tool_call_id:
            continue

        if not email:
            results.append({"toolCallId": tool_call_id, "result": {"ok": False, "error": "Missing email"}})
            continue

        if not call_id:
            results.append({"toolCallId": tool_call_id, "result": {"ok": False, "error": "Missing callId"}})
            continue

        # ✅ persist mapping for end-of-call-report use
        ConfirmedEmail.objects.update_or_create(
            call_id=call_id,
            defaults={"email": email},
        )

        # ✅ ensure lead exists (resume key)
        lead, _ = Lead.objects.get_or_create(
            email=email,
            defaults={"status": "in_progress", "current_step": "homeownership", "is_completed": False},
        )

        results.append({
            "toolCallId": tool_call_id,
            "result": {
                "ok": True,
                "email": email,
                "callId": call_id,
                "leadId": str(lead.id),
            }
        })

    return JsonResponse({"results": results})


# =========================================================
# TOOL ENDPOINT: lookup_lead_state(email)
# =========================================================

@csrf_exempt
def lookup_lead_state_tool(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    payload = json.loads(request.body.decode("utf-8"))
    message = payload.get("message", {}) or {}
    tool_calls = _get_tool_calls(message)

    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("toolCallId") or tc.get("id")
        fn = tc.get("function") or {}
        args = _parse_tool_args(fn.get("arguments"))
        email = (args.get("email") or "").strip().lower()

        if not tool_call_id:
            continue

        lead = Lead.objects.filter(email=email).first()

        if lead:
            result = {
                "found": True,
                "email": lead.email,
                "status": lead.status,
                "current_step": lead.current_step,
                "is_completed": lead.is_completed,
            }
        else:
            result = {"found": False}

        results.append({"toolCallId": tool_call_id, "result": result})

    return JsonResponse({"results": results})


# =========================================================
# MAIN VAPI WEBHOOK (end-of-call-report)
# =========================================================

import json
import re
import logging
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crm.models import Lead, Call, ConfirmedEmail

logger = logging.getLogger(__name__)

# -------------------------
# Email extraction fallback
# -------------------------

EMAIL_REGEX = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

def extract_email_from_transcript(transcript: str):
    if not transcript:
        return None
    text = transcript.lower()
    text = text.replace(" at ", "@").replace(" dot ", ".").replace(" g mail ", " gmail ")
    text = re.sub(r"[^a-z0-9@._+\- ]", " ", text)
    m = EMAIL_REGEX.search(text)
    return m.group(0).lower() if m else None

# -------------------------
# Qualification + step
# -------------------------

def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"
    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"
    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    # Only treat as Qualified if explicit closing is present
    if "specialist will contact you" in t or "we look forward to helping you go solar" in t:
        return "Qualified", ""

    return "Unknown", ""

def detect_current_step(transcript: str) -> str:
    t = (transcript or "").lower()
    if "homeowner" not in t:
        return "homeownership"
    if "electricity bill" not in t:
        return "bill"
    if "within the next 12 months" not in t:
        return "timeline"
    if "full name" in t or "phone number" in t or "property address" in t or "email" in t:
        return "collecting_contact"
    return "unknown"

# -------------------------
# HubSpot upsert (create then PATCH on 409)
# -------------------------

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {getattr(settings, 'HUBSPOT_ACCESS_TOKEN', '')}",
    "Content-Type": "application/json",
}

def hubspot_create_contact(properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts"
    r = requests.post(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def hubspot_update_contact(contact_id: str, properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}"
    r = requests.patch(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def parse_existing_contact_id(conflict_body: dict):
    msg = (conflict_body or {}).get("message", "") or ""
    m = re.search(r"Existing ID:\s*(\d+)", msg)
    return m.group(1) if m else None

def hubspot_upsert_contact(properties: dict):
    status, body = hubspot_create_contact(properties)
    if status == 409:
        existing_id = parse_existing_contact_id(body)
        if existing_id:
            return hubspot_update_contact(existing_id, properties)
    return status, body

# -------------------------
# FINAL: vapi_webhook handler
# -------------------------

@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        message = payload.get("message", {}) or {}
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        # Only process end-of-call-report here
        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ok"})

        artifact = message.get("artifact", {}) or {}
        call_obj = message.get("call", {}) or {}

        call_id = (
            call_obj.get("id")
            or (artifact.get("call") or {}).get("id")
            or ""
        )

        transcript = (
            artifact.get("transcript")
            or payload.get("transcript")
            or ""
        )

        # IMPORTANT: these are top-level on end-of-call-report payload
        ended_reason = payload.get("endedReason", "") or ""
        duration_seconds = payload.get("durationSeconds", 0) or 0

        qualification, reason = detect_qualification(transcript)
        current_step = detect_current_step(transcript)

        # -------------------------
        # Email source of truth:
        # 1) ConfirmedEmail by call_id
        # 2) transcript fallback
        # 3) unknown fallback
        # -------------------------
        email = None

        if call_id:
            rec = ConfirmedEmail.objects.filter(call_id=str(call_id)).first()
            if rec:
                email = rec.email

        if not email:
            email = extract_email_from_transcript(transcript)

        if not email:
            email = f"unknown-{call_id}@noemail.local"

        # -------------------------
        # Save / update Lead
        # -------------------------
        lead, _ = Lead.objects.get_or_create(
            email=email,
            defaults={"status": "new", "current_step": "homeownership"},
        )

        lead.current_step = current_step
        lead.qualification_result = qualification
        lead.disqualification_reason = reason

        if qualification == "Disqualified":
            lead.status = "disqualified"
            lead.is_completed = True
            lead.current_step = "completed"
        elif qualification == "Qualified":
            # If ended by timeout/hangup, keep incomplete
            if ended_reason in ["silence-timed-out", "customer-ended-call"]:
                lead.status = "in_progress"
                lead.is_completed = False
            else:
                lead.status = "qualified"
                lead.is_completed = True
                lead.current_step = "completed"
        else:
            lead.status = "in_progress"
            lead.is_completed = False

        lead.save()

        # -------------------------
        # Save Call (idempotent)
        # -------------------------
        if call_id:
            Call.objects.get_or_create(
                id=str(call_id),
                defaults={
                    "lead": lead,
                    "transcript": transcript,
                    "duration_seconds": int(duration_seconds or 0),
                    "ended_reason": ended_reason,
                },
            )

        # -------------------------
        # HubSpot sync (partial allowed)
        # - skip only for fake email
        # - omit lead_qualification_result if Unknown
        # -------------------------
        if not email.endswith("@noemail.local"):
            solarpeak_last_call_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            properties = {
                "email": email,
                "disqualification_reason": (reason or None),
                "solarpeak_last_call_timestamp": solarpeak_last_call_ts_ms,
                "solarpeak_last_call_duration_seconds": int(duration_seconds or 0),
                "last_call_transcript": transcript[:5000],
            }

            if qualification in ["Qualified", "Disqualified"]:
                properties["lead_qualification_result"] = qualification

            hs_status, hs_body = hubspot_upsert_contact(properties)
            logger.info(f"HubSpot response status: {hs_status}")
            logger.info(f"HubSpot response body: {hs_body}")

        return JsonResponse({"status": "stored"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)