from crm.models import ConfirmedEmail


def get_confirmed_email(call_id: str):
    if not call_id:
        return None

    rec = ConfirmedEmail.objects.filter(call_id=str(call_id)).first()
    return rec.email if rec and rec.email else None