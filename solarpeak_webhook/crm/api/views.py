import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils.dateparse import parse_datetime

from crm.models import Lead, Call
from crm.services.lead_service import upsert_lead
from crm.services.hubspot import hubspot_upsert_contact

logger = logging.getLogger(__name__)


# =========================================================
# INTERNAL API KEY AUTH
# =========================================================

def api_key_required(view_func):
    def wrapper(request, *args, **kwargs):
        api_key = request.headers.get("X-API-KEY")
        if api_key != getattr(settings, "INTERNAL_API_KEY", None):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


# =========================================================
# HELPERS
# =========================================================

def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}"), None
    except Exception:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)


def _lead_to_dict(lead):
    return {
        "id": str(lead.id),
        "email": lead.email,
        "status": lead.status,
        "current_step": lead.current_step,
        "is_completed": lead.is_completed,
        "qualification_result": lead.qualification_result,
        "disqualification_reason": lead.disqualification_reason,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


def _call_to_dict(call):
    return {
        "id": str(call.id),
        "lead_id": str(call.lead_id),
        "duration_seconds": call.duration_seconds,
        "ended_reason": call.ended_reason,
        "summary": call.summary,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


# =========================================================
# 1) POST /api/leads
# 4) GET  /api/leads
# =========================================================

@csrf_exempt
@api_key_required
def leads_collection(request):

    # -------------------------
    # CREATE LEAD
    # -------------------------
    if request.method == "POST":
        data, err = _parse_json(request)
        if err:
            return err

        email = (data.get("email") or "").strip().lower()
        if not email:
            return JsonResponse({"error": "email is required"}, status=400)

        qualification = data.get("qualification_result")
        reason = data.get("reason")
        current_step = data.get("current_step")
        ended_reason = data.get("ended_reason")

        lead = upsert_lead(
            email=email,
            qualification=qualification,
            reason=reason,
            current_step=current_step,
            ended_reason=ended_reason,
        )

        # CRM sync
        try:
            properties = {
                "email": lead.email,
                "lead_qualification_result": lead.qualification_result,
                "disqualification_reason": lead.disqualification_reason,
            }
            hubspot_upsert_contact(properties)
        except Exception:
            logger.exception("HubSpot sync failed")

        return JsonResponse({"lead": _lead_to_dict(lead)}, status=201)

    # -------------------------
    # LIST LEADS (WITH FILTERS)
    # -------------------------
    if request.method == "GET":

        qs = Lead.objects.all().order_by("-created_at")

        # Filtering
        status = request.GET.get("status")
        qualification = request.GET.get("qualification_result")
        created_at_gte = request.GET.get("created_at_gte")
        created_at_lte = request.GET.get("created_at_lte")

        if status:
            qs = qs.filter(status=status)

        if qualification:
            qs = qs.filter(qualification_result=qualification)

        if created_at_gte:
            dt = parse_datetime(created_at_gte)
            if dt:
                qs = qs.filter(created_at__gte=dt)

        if created_at_lte:
            dt = parse_datetime(created_at_lte)
            if dt:
                qs = qs.filter(created_at__lte=dt)

        limit = min(int(request.GET.get("limit", 50)), 200)
        results = [_lead_to_dict(l) for l in qs[:limit]]

        return JsonResponse({"results": results, "limit": limit})

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# 2) GET /api/leads/{id}
# 3) PATCH /api/leads/{id}
# =========================================================

@csrf_exempt
@api_key_required
def lead_detail(request, lead_id):

    try:
        lead = Lead.objects.get(id=lead_id)
    except Lead.DoesNotExist:
        return JsonResponse({"error": "Lead not found"}, status=404)

    # GET
    if request.method == "GET":
        return JsonResponse({"lead": _lead_to_dict(lead)})

    # PATCH
    if request.method == "PATCH":
        data, err = _parse_json(request)
        if err:
            return err

        allowed_fields = [
            "status",
            "current_step",
            "is_completed",
            "qualification_result",
            "disqualification_reason",
            "phone",
            "firstname",
            "lastname",
        ]

        for field in allowed_fields:
            if field in data:
                setattr(lead, field, data[field])

        lead.save()

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

    data, err = _parse_json(request)
    if err:
        return err

    summary = data.get("summary")

    if summary is None:
        return JsonResponse({"error": "summary is required"}, status=400)

    try:
        call = Call.objects.get(id=str(call_id))
    except Call.DoesNotExist:
        return JsonResponse({"error": "Call not found"}, status=404)

    # ✅ SAFE STORAGE (handles dict or string)
    if isinstance(summary, dict):
        call.summary = json.dumps(summary)
    else:
        call.summary = str(summary)

    call.save()

    return JsonResponse({"call": _call_to_dict(call)})