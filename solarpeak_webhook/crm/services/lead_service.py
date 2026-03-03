from crm.models import Lead, Call

def upsert_lead(email, qualification, reason, current_step, ended_reason):
    lead, _ = Lead.objects.get_or_create(
        email=email,
        defaults={"status": "new", "current_step": "homeownership"},
    )

    lead.current_step = current_step
    lead.qualification_result = qualification or ""
    lead.disqualification_reason = reason or ""

    if qualification == "Disqualified":
        lead.status = "disqualified"
        lead.is_completed = True
        lead.current_step = "completed"
    elif qualification == "Qualified":
        if ended_reason in ["silence-timed-out", "customer-ended-call"]:
            lead.status = "in_progress"
            lead.is_completed = False
        else:
            lead.status = "qualified"
            lead.is_completed = True
            lead.current_step = "completed"
    else:
        lead.status = "in_progress"
        lead.is_completed = False

    lead.save()
    return lead


def store_call(call_id, transcript, duration_seconds, ended_reason, lead):
    Call.objects.update_or_create(
        id=str(call_id),
        defaults={
            "lead": lead,
            "transcript": transcript,
            "duration_seconds": int(duration_seconds or 0),
            "ended_reason": ended_reason,
        }
    )