import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import requests

from crm.models import Lead, ConfirmedEmail
from crm.services.qualification import detect_qualification, detect_current_step
from crm.services.email_capture import get_confirmed_email
from crm.services.lead_service import upsert_lead, store_call

logger = logging.getLogger(__name__)


# =========================================================
# TOOL ENDPOINT: confirm_email
# =========================================================

@csrf_exempt
def confirm_email_tool(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        logger.exception("Invalid JSON in confirm_email_tool")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message = payload.get("message", {}) or {}

    call_id = (
        payload.get("call", {}).get("id")
        or message.get("call", {}).get("id")
        or ""
    )

    tool_calls = message.get("toolCallList") or message.get("toolCalls") or []

    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("toolCallId") or tc.get("id")
        fn = tc.get("function") or {}
        args = fn.get("arguments") or {}

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        email = (args.get("email") or "").strip().lower()

        if not tool_call_id:
            continue

        if not email:
            results.append({
                "toolCallId": tool_call_id,
                "result": {"ok": False, "error": "Missing email"}
            })
            continue

        if not call_id:
            results.append({
                "toolCallId": tool_call_id,
                "result": {"ok": False, "error": "Missing callId"}
            })
            continue

        ConfirmedEmail.objects.update_or_create(
            call_id=call_id,
            defaults={"email": email},
        )

        Lead.objects.get_or_create(
            email=email,
            defaults={
                "status": "in_progress",
                "current_step": "homeownership",
                "is_completed": False
            },
        )

        results.append({
            "toolCallId": tool_call_id,
            "result": {
                "ok": True,
                "email": email,
                "callId": call_id,
            }
        })

    return JsonResponse({"results": results})


# =========================================================
# TOOL ENDPOINT: lookup_lead_state
# =========================================================

@csrf_exempt
def lookup_lead_state_tool(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    payload = json.loads(request.body.decode("utf-8"))
    message = payload.get("message", {}) or {}
    tool_calls = message.get("toolCallList") or message.get("toolCalls") or []

    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("toolCallId") or tc.get("id")
        fn = tc.get("function") or {}
        args = fn.get("arguments") or {}

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}

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

        results.append({
            "toolCallId": tool_call_id,
            "result": result
        })

    return JsonResponse({"results": results})


# =========================================================
# MAIN VAPI WEBHOOK
# =========================================================

@csrf_exempt
def vapi_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        message = payload.get("message", {}) or {}
        event_type = message.get("type")

        logger.info(f"Received Vapi event: {event_type}")

        if event_type != "end-of-call-report":
            return JsonResponse({"status": "ok"})

        artifact = message.get("artifact", {}) or {}
        call_obj = message.get("call", {}) or {}

        call_id = call_obj.get("id")
        transcript = artifact.get("transcript") or ""

        ended_reason = payload.get("endedReason", "")
        duration_seconds = payload.get("durationSeconds", 0)

        # ✅ Get confirmed email only (no transcript fallback)
        email = get_confirmed_email(call_id)
        if not email:
            logger.error(f"No confirmed email found for call {call_id}")
            return JsonResponse({"status": "no_confirmed_email"})

        # ✅ Qualification logic
        qualification, reason = detect_qualification(transcript)
        current_step = detect_current_step(transcript)

        # ✅ Persist lead + call
        lead = upsert_lead(
            email=email,
            qualification=qualification,
            reason=reason,
            current_step=current_step,
            ended_reason=ended_reason,
        )

        store_call(
            call_id=call_id,
            transcript=transcript,
            duration_seconds=duration_seconds,
            ended_reason=ended_reason,
            lead=lead,
        )

        # ✅ Call middleware API (CRM abstraction layer)
        try:
            requests.post(
                "http://localhost:8000/api/leads",
                headers={
                    "X-API-KEY": settings.INTERNAL_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "qualification_result": qualification,
                    "reason": reason,
                    "current_step": current_step,
                    "ended_reason": ended_reason,
                },
                timeout=10,
            )
        except Exception:
            logger.exception("Failed to call middleware API")

        return JsonResponse({"status": "processed"})

    except Exception:
        logger.exception("Webhook processing failed")
        return JsonResponse({"error": "internal_error"}, status=500)