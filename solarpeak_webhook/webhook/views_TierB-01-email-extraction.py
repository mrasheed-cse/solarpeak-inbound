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


def detect_qualification(transcript):
    transcript_lower = transcript.lower()

    if "require homeowner approval" in transcript_lower:
        return "Disqualified", "Not homeowner"

    if "higher energy usage" in transcript_lower:
        return "Disqualified", "Low electricity bill"

    if "ready to install within a year" in transcript_lower:
        return "Disqualified", "Timeline beyond 12 months"

    return "Qualified", ""

    
def extract_basic_info(transcript):
    """
    Very simple extraction placeholder.
    You can improve with regex later.
    """

    # This is intentionally basic for now.
    # Replace with structured extraction later.
    return {
        "firstname": "SolarPeak",
        "lastname": "Lead",
        "email": "",
        "phone": "",
        "address": ""
    }


@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        #event_type = payload.get("type")

        message = payload.get("message", {})
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        if event_type == "end-of-call-report":

            # transcript = artifact.get("transcript", "")
            transcript = artifact.get("transcript", "") or ""
            email = extract_email_from_transcript(transcript)
            call_id = call.get("id")
            ended_reason = call.get("endedReason", "")
            duration = call.get("durationSeconds", 0)

            # Extract email (placeholder for now)
            # email = "test@example.com"

            # Qualification detection (reuse your function)
            qualification, reason = detect_qualification(transcript)

            if not email:
                # tie it to call id to avoid overwriting a single "test@example.com"
                email = f"unknown-{call_id}@noemail.local"

            # Put this RIGHT HERE, before HubSpot sync
            is_real_email = not email.endswith("@noemail.local")
            if is_real_email:
                # sync to HubSpot here (call your hubspot upsert function)
                pass

            # Upsert Lead
            lead, created = Lead.objects.get_or_create(
                email=email,
                defaults={
                    "qualification_result": qualification,
                    "disqualification_reason": reason,
                    "status": "qualified" if qualification == "Qualified" else "disqualified"
                }
            )

            # Save Call
            Call.objects.create(
                id=call_id,
                lead=lead,
                transcript=transcript,
                duration_seconds=duration,
                ended_reason=ended_reason
            )

            # Optional: Sync to HubSpot
            # sync_lead_to_hubspot(lead)

            return JsonResponse({"status": "stored"})

        #call = payload.get("call", {})
        #artifact = payload.get("artifact", {})
        #analysis = payload.get("analysis", {})

        call = message.get("call", {})
        artifact = message.get("artifact", {})
        analysis = message.get("analysis", {})

        transcript = artifact.get("transcript", "")
        duration = call.get("duration", 0)

        qualification, reason = detect_qualification(transcript)

        basic_info = extract_basic_info(transcript)

        solarpeak_last_call_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        properties = {
            "firstname": basic_info.get("firstname"),
            "lastname": basic_info.get("lastname"),
            "email": basic_info.get("email"),
            "phone": basic_info.get("phone"),
            "address": basic_info.get("address"),
            "lead_qualification_result": qualification,
            "disqualification_reason": reason,
            "solarpeak_last_call_timestamp": solarpeak_last_call_ts_ms,
            "solarpeak_last_call_duration_seconds": duration,
            "last_call_transcript": transcript[:5000]  # avoid huge payload
        }

        status, response_data = upsert_contact(properties)

        logger.info(f"HubSpot response status: {status}")
        logger.info(response_data)

        return JsonResponse({"status": "processed"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)