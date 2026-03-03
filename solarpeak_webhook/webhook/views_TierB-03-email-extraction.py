import json
import re
import logging
from datetime import datetime, timezone
from django.conf import settings

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crm.models import Lead, Call
from .hubspot import upsert_contact

logger = logging.getLogger(__name__)

# ----------------------------------------
# Email Extraction
# ----------------------------------------

EMAIL_REGEX = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE
)

def extract_email_from_transcript(transcript: str):
    if not transcript:
        return None
    match = EMAIL_REGEX.search(transcript)
    return match.group(0).lower() if match else None


# ----------------------------------------
# Qualification Detection
# ----------------------------------------

def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"

    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    return "Qualified", ""


# ----------------------------------------
# Webhook Handler
# ----------------------------------------

@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))

        message = payload.get("message", {})
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        # ✅ Only process final call event
        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ok"})

        # ----------------------------------------
        # Extract Call Data
        # ----------------------------------------

        call = message.get("call", {})
        artifact = message.get("artifact", {})

        call_id = call.get("id")
        transcript = artifact.get("transcript", "") or ""
        duration_seconds = call.get("durationSeconds", 0) or 0
        ended_reason = call.get("endedReason", "")

        logger.info(f"call_id: {call_id!r}")
        logger.info(f"ended_reason: {ended_reason!r}, duration_seconds: {duration_seconds!r}")
        logger.info(f"transcript_len: {len(transcript)}")
        # logger.info(f"Processing end-of-call-report for call: {call_id}")

        # ----------------------------------------
        # Extract Email (Primary Identifier)
        # ----------------------------------------

        email = extract_email_from_transcript(transcript)

        if not email:
            email = f"unknown-{call_id}@noemail.local"

        # ----------------------------------------
        # Detect Qualification
        # ----------------------------------------

        qualification, reason = detect_qualification(transcript)

        # ----------------------------------------
        # Store Lead (SQLite)
        # ----------------------------------------

        lead, created = Lead.objects.get_or_create(
            email=email,
            defaults={
                "status": "new",
                "current_step": "homeownership",
            }
        )

        # Update lead state
        lead.qualification_result = qualification
        lead.disqualification_reason = reason

        if qualification == "Qualified":
            lead.status = "qualified"
            lead.is_completed = True
            lead.current_step = "completed"

        elif qualification == "Disqualified":
            lead.status = "disqualified"
            lead.is_completed = True
            lead.current_step = "completed"

        lead.save()

        # ----------------------------------------
        # Store Call (Idempotent)
        # ----------------------------------------
        
        logger.info(f"DB file: {settings.DATABASES['default']['NAME']}")
        try:
            obj, created = Call.objects.get_or_create(
                id=call_id,
                defaults={
                    "lead": lead,
                    "transcript": transcript,
                    "duration_seconds": duration_seconds,
                    "ended_reason": ended_reason,
                }
            )
            logger.info(f"Call get_or_create ok: created={created}, id={obj.id}")
        except Exception:
            logger.exception("Call save failed")

        # logger.info(f"Call stored successfully for {call_id}")

        # ----------------------------------------
        # Sync to HubSpot (ONLY if real email)
        # ----------------------------------------

        is_real_email = not email.endswith("@noemail.local")

        if is_real_email:
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

        return JsonResponse({"status": "stored"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)