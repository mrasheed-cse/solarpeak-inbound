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

@csrf_exempt
def vapi_webhook(request):
    print("=== WEBHOOK ENTERED ===", flush=True)

    payload = json.loads(request.body.decode("utf-8"))
    print("RAW PAYLOAD:", payload, flush=True)

    message = payload.get("message", {})
    event_type = message.get("type")

    print("EVENT TYPE VALUE:", event_type, flush=True)

    return JsonResponse({"debug": "done"})