import json
import logging
from datetime import datetime
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from crm.models import Lead, Call
from crm.services.lead_service import upsert_lead
from crm.services.hubspot import hubspot_upsert_contact
from .auth import api_key_required

logger = logging.getLogger(__name__)


def _json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}"), None
    except Exception:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)


def _lead_to_dict(lead: Lead):
    return {
        "id": str(lead.id),
        "email": lead.email,
        "status": getattr(lead, "status", None),
        "current_step": getattr(lead, "current_step", None),
        "is_completed": getattr(lead, "is_completed", None),
        "qualification_result": getattr(lead, "qualification_result", None),
        "disqualification_reason": getattr(lead, "disqualification_reason", None),
        "created_at": lead.created_at.isoformat() if hasattr(lead, "created_at") and lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if hasattr(lead, "updated_at") and lead.updated_at else None,
    }


def _call_to_dict(call: Call):
    return {
        "id": str(call.id),
        "lead_id": str(call.lead_id) if getattr(call, "lead_id", None) else None,
        "duration_seconds": getattr(call, "duration_seconds", None),
        "ended_reason": getattr(call, "ended_reason", None),
        "summary": getattr(call, "summary", None),
        "created_at": call.created_at.isoformat() if hasattr(call, "created_at") and call.created_at else None,
        "updated_at": call.updated_at.isoformat() if hasattr(call, "updated_at") and call.updated_at else None,
    }


# =========================================================
# 1) POST /api/leads  + 4) GET /api/leads
# =========================================================

@csrf_exempt
@api_key_required
def leads_collection(request):
    if request.method == "POST":
        data, err = _json(request)
        if err:
            return err

        email = (data.get("email") or "").strip().lower()
        if not email:
            return JsonResponse({"error": "email is required"}, status=400)

        qualification = data.get("qualification_result")
        reason = data.get("reason") or data.get("disqualification_reason")  # accept either
        current_step = data.get("current_step") or "homeownership"
        ended_reason = data.get("ended_reason") or ""

        lead = upsert_lead(
            email=email,
            qualification=qualification,
            reason=reason,
            current_step=current_step,
            ended_reason=ended_reason,
        )

        # CRM sync (optional but recommended for your assignment)
        try:
            props = {
                "email": lead.email,
                "lead_qualification_result": lead.qualification_result,
                "disqualification_reason": lead.disqualification_reason,
            }
            hubspot_upsert_contact(props)
        except Exception:
            logger.exception("HubSpot sync failed in POST /api/leads")

        return JsonResponse({"lead": _lead_to_dict(lead)}, status=201)

    if request.method == "GET":
        qs = Lead.objects.all().order_by("-created_at") if hasattr(Lead, "created_at") else Lead.objects.all()

        # Filters
        status = request.GET.get("status")
        qualification = request.GET.get("qualification_result")
        created_at_gte = request.GET.get("created_at_gte")
        created_at_lte = request.GET.get("created_at_lte")

        if status:
            qs = qs.filter(status=status)

        if qualification:
            qs = qs.filter(qualification_result=qualification)

        # Date range (ISO 8601 datetimes)
        if created_at_gte:
            dt = parse_datetime(created_at_gte)
            if not dt:
                return JsonResponse({"error": "created_at_gte must be ISO datetime"}, status=400)
            qs = qs.filter(created_at__gte=dt)

        if created_at_lte:
            dt = parse_datetime(created_at_lte)
            if not dt:
                return JsonResponse({"error": "created_at_lte must be ISO datetime"}, status=400)
            qs = qs.filter(created_at__lte=dt)

        # Pagination (simple)
        limit = int(request.GET.get("limit", 50))
        limit = max(1, min(limit, 200))
        leads = [_lead_to_dict(l) for l in qs[:limit]]

        return JsonResponse({"results": leads, "limit": limit})

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# 2) GET /api/leads/{id}  + 3) PATCH /api/leads/{id}
# =========================================================

@csrf_exempt
@api_key_required
def lead_detail(request, lead_id):
    try:
        lead = Lead.objects.get(id=lead_id)
    except Lead.DoesNotExist:
        return JsonResponse({"error": "Lead not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({"lead": _lead_to_dict(lead)})

    if request.method == "PATCH":
        data, err = _json(request)
        if err:
            return err

        # Allow updates
        updatable = [
            "status",
            "current_step",
            "is_completed",
            "qualification_result",
            "disqualification_reason",
        ]
        for k in updatable:
            if k in data:
                setattr(lead, k, data[k])

        lead.save()

        # Optional HubSpot sync on updates
        try:
            props = {
                "email": lead.email,
                "lead_qualification_result": lead.qualification_result,
                "disqualification_reason": lead.disqualification_reason,
            }
            hubspot_upsert_contact(props)
        except Exception:
            logger.exception("HubSpot sync failed in PATCH /api/leads/{id}")

        return JsonResponse({"lead": _lead_to_dict(lead)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# 5) POST /api/calls/{call_id}/summary
# =========================================================

@csrf_exempt
@api_key_required
def call_summary(request, call_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    data, err = _json(request)
    if err:
        return err

    summary = data.get("summary")
    lead_id = data.get("lead_id")  # optional explicit link

    if summary is None:
        return JsonResponse({"error": "summary is required"}, status=400)

    try:
        call = Call.objects.get(id=str(call_id))
    except Call.DoesNotExist:
        return JsonResponse({"error": "Call not found"}, status=404)

    # Optionally link call to lead
    if lead_id:
        try:
            lead = Lead.objects.get(id=lead_id)
            call.lead = lead
        except Lead.DoesNotExist:
            return JsonResponse({"error": "lead_id not found"}, status=404)

    # Store summary (string or dict)
    call.summary = summary
    call.save()

    return JsonResponse({"call": _call_to_dict(call)})