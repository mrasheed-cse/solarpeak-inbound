import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .hubspot import upsert_contact, create_note

logger = logging.getLogger(__name__)


@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body)
        event_type = payload.get("type")

        logger.info(f"Vapi event: {event_type}")

        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ignored"})

        call = payload.get("call", {})
        analysis = payload.get("analysis", {})
        artifact = payload.get("artifact", {})

        transcript = artifact.get("transcript", "")
        duration = call.get("duration", 0)

        # VERY BASIC qualification detection (can improve later)
        qualified = "specialist will contact you" in transcript.lower()

        # Example extraction placeholders
        email = "test@example.com"   # Later parse from transcript
        phone = call.get("customer", {}).get("number")

        contact = upsert_contact(
            email=email,
            properties={
                "phone": phone,
                "lifecyclestage": "lead",
                "lead_status": "Qualified" if qualified else "Disqualified",
            }
        )

        note_body = f"""
SolarPeak Call Summary

Qualified: {qualified}
Duration: {duration} seconds
Transcript: {transcript}
"""

        create_note(contact["id"], note_body)

        logger.info("HubSpot contact + note created")

        return JsonResponse({"status": "processed"})

    except Exception as e:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": str(e)}, status=500)