import json
import logging
from datetime import datetime, timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .hubspot import upsert_contact

logger = logging.getLogger(__name__)


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

        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ignored"})

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