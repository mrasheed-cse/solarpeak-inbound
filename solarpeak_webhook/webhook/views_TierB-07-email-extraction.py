import json
import re
import logging
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crm.models import Lead, Call
from .hubspot import upsert_contact

logger = logging.getLogger(__name__)

# =========================================================
# EMAIL NORMALIZATION + EXTRACTION
# =========================================================

EMAIL_REGEX = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE
)

def normalize_spoken_email(text: str) -> str:
    if not text:
        return ""

    t = text.lower()

    # normalize common speech patterns
    t = t.replace(" at ", "@")
    t = t.replace(" dot ", ".")
    t = t.replace(" underscore ", "_")
    t = t.replace(" dash ", "-")

    # remove extra spaces
    t = re.sub(r"\s+", "", t)

    return t

def extract_email_from_transcript(transcript: str):
    if not transcript:
        return None

    # Normalize common spoken patterns first
    text = transcript.lower()
    text = text.replace(" at ", "@")
    text = text.replace(" dot ", ".")
    text = text.replace(" g mail ", " gmail ")

    # Remove extra punctuation except @ and .
    text = re.sub(r"[^a-z0-9@._\- ]", " ", text)

    # Now search for email pattern
    match = EMAIL_REGEX.search(text)

    if match:
        return match.group(0).lower()

    return None


# =========================================================
# QUALIFICATION DETECTION
# =========================================================

def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"

    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"

    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    # Explicit qualified closing signals
    if "specialist will contact you" in t or "we look forward to helping you go solar" in t:
        return "Qualified", ""

    return "Unknown", ""


# =========================================================
# STEP DETECTOR (for resume logic)
# =========================================================

def detect_current_step(transcript: str) -> str:
    t = (transcript or "").lower()

    if "homeowner" not in t:
        return "homeownership"

    if "electricity bill" not in t:
        return "bill"

    if "within the next 12 months" not in t:
        return "timeline"

    if "email" in t or "phone number" in t or "full name" in t:
        return "collecting_contact"

    return "unknown"


# =========================================================
# MAIN VAPI WEBHOOK
# =========================================================

@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))

        message = payload.get("message", {})
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        # Only process final event
        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ok"})

        call = message.get("call", {}) or {}
        artifact = message.get("artifact", {}) or {}

        call_id = call.get("id")
        transcript = artifact.get("transcript", "") or ""

        # ✅ FIX: endedReason & duration are at top-level payload
        ended_reason = payload.get("endedReason", "")
        duration_seconds = payload.get("durationSeconds", 0) or 0

        logger.info(f"Processing call_id: {call_id}")
        logger.info(f"Ended reason: {ended_reason}")

        # =========================================================
        # EMAIL EXTRACTION
        # =========================================================

        email = extract_email_from_transcript(transcript)

        if not email:
            email = f"unknown-{call_id}@noemail.local"

        # =========================================================
        # QUALIFICATION + STEP DETECTION
        # =========================================================

        qualification, reason = detect_qualification(transcript)
        current_step = detect_current_step(transcript)

        # =========================================================
        # STORE / UPDATE LEAD
        # =========================================================

        lead, created = Lead.objects.get_or_create(
            email=email,
            defaults={
                "status": "new",
                "current_step": "homeownership",
            }
        )

        lead.current_step = current_step
        lead.qualification_result = qualification
        lead.disqualification_reason = reason

        # ==============================
        # COMPLETION LOGIC
        # ==============================

        if qualification == "Disqualified":
            lead.status = "disqualified"
            lead.is_completed = True
            lead.current_step = "completed"

        elif qualification == "Qualified":
            # ✅ If timeout/hangup → incomplete
            if ended_reason in ["silence-timed-out", "customer-ended-call"]:
                lead.status = "in_progress"
                lead.is_completed = False
            else:
                lead.status = "qualified"
                lead.is_completed = True
                lead.current_step = "completed"

        else:
            # Unknown → incomplete
            lead.status = "in_progress"
            lead.is_completed = False

        lead.save()

        # =========================================================
        # STORE CALL (IDEMPOTENT)
        # =========================================================

        if call_id:
            Call.objects.get_or_create(
                id=call_id,
                defaults={
                    "lead": lead,
                    "transcript": transcript,
                    "duration_seconds": duration_seconds,
                    "ended_reason": ended_reason,
                }
            )

        # =========================================================
        # HUBSPOT SYNC (ONLY IF REAL EMAIL)
        # =========================================================

        if not email.endswith("@noemail.local"):
            solarpeak_last_call_ts_ms = int(
                datetime.now(timezone.utc).timestamp() * 1000
            )

            properties = {
                "email": email,
                "lead_qualification_result": qualification,
                "disqualification_reason": reason,
                "solarpeak_last_call_timestamp": solarpeak_last_call_ts_ms,
                "solarpeak_last_call_duration_seconds": duration_seconds,
                "last_call_transcript": transcript[:5000],
            }

            status, response_data = upsert_contact(properties)
            logger.info(f"HubSpot response status: {status}")
            logger.info(f"HubSpot response body: {response_data}")

        return JsonResponse({"status": "stored"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)


# =========================================================
# TOOL ENDPOINT FOR RESUME LOGIC
# =========================================================

@csrf_exempt
def lookup_lead_state_tool(request):
    payload = json.loads(request.body.decode("utf-8"))
    message = payload.get("message", {}) or {}
    tool_calls = message.get("toolCallList", []) or []

    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("toolCallId")
        fn = (tc.get("function") or {})
        args = fn.get("arguments") or {}
        email = (args.get("email") or "").strip().lower()

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

        results.append({
            "toolCallId": tool_call_id,
            "result": result
        })

    return JsonResponse({"results": results})