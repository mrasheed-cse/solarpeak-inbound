import json
import re
import logging
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from solarpeak_webhook.crm.models import Call, Lead
from .hubspot import upsert_contact

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

def extract_email_from_transcript(transcript: str) -> str | None:
    if not transcript:
        return None
    m = EMAIL_REGEX.search(transcript)
    return m.group(0).lower() if m else None

def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"

    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    return "Qualified", ""

def extract_basic_info(transcript: str):
    # Placeholder; improve later with regex/structured output
    return {
        "firstname": "SolarPeak",
        "lastname": "Lead",
        "phone": "",
        "address": "",
    }

@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))

        message = payload.get("message", {}) or {}
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        # Only do heavy work on end-of-call-report
        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ok"})

        call = message.get("call", {}) or {}
        artifact = message.get("artifact", {}) or {}

        call_id = call.get("id")
        transcript = artifact.get("transcript", "") or ""
        ended_reason = call.get("endedReason", "")
        duration_seconds = call.get("durationSeconds", 0) or 0

        logger.info(f"Creating Call with ID: {call_id}")

        # Email extraction + fallback
        email = extract_email_from_transcript(transcript)
        if not email:
            email = f"unknown-{call_id}@noemail.local"

        qualification, reason = detect_qualification(transcript)

        # ✅ Store state locally (SQLite)
        lead, created = Lead.objects.get_or_create(
            email=email,
            defaults={
                "status": "new",
                "current_step": "homeownership",
            }
        )

      #  lead.qualification_result = qualification
      #  lead.disqualification_reason = reason
      #  lead.status = "qualified" if qualification == "Qualified" else "disqualified"
      #  lead.is_completed = qualification in ["Qualified", "Disqualified"]
      #  lead.current_step = "completed" if lead.is_completed else (lead.current_step or "unknown")

        # Only update qualification fields if they are determined
        if qualification:
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

        # If call ended early (silence timeout), preserve partial progress
        if not lead.is_completed:
            if "homeowner" in transcript.lower():
                lead.current_step = "bill"
            elif "electricity bill" in transcript.lower():
                lead.current_step = "timeline"
            elif "install within" in transcript.lower():
                lead.current_step = "collecting_contact"

        lead.save()

        # Call.objects.create(
         #   id=call_id,
          #  lead=lead,
           # transcript=transcript,
           # duration_seconds=duration_seconds,
           # ended_reason=ended_reason,
        # )

        Call.objects.get_or_create(
            id=call_id,
            defaults={
                "lead": lead,
                "transcript": transcript,
                "duration_seconds": duration_seconds,
                "ended_reason": ended_reason,
            }
        )

        # ✅ HubSpot sync ONLY if email is real
        is_real_email = not email.endswith("@noemail.local")
        if is_real_email:
            basic = extract_basic_info(transcript)

            solarpeak_last_call_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            properties = {
                "firstname": basic.get("firstname"),
                "lastname": basic.get("lastname"),
                "email": email,  # IMPORTANT: use extracted email
                "phone": basic.get("phone"),
                "address": basic.get("address"),
                "lead_qualification_result": "Disqualified" if qualification != "Qualified" else "Qualified",
                "disqualification_reason": reason,
                "solarpeak_last_call_timestamp": solarpeak_last_call_ts_ms,
                "solarpeak_last_call_duration_seconds": duration_seconds,
                "last_call_transcript": transcript[:5000],
            }

            status, response_data = upsert_contact(properties)
            logger.info(f"HubSpot response status: {status}")
            logger.info(response_data)

        return JsonResponse({"status": "stored"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)