from django.urls import path
from .views import vapi_webhook, lookup_lead_state_tool, confirm_email_tool

urlpatterns = [
    path("webhook/", vapi_webhook),
    path("tool/lookup-lead-state/", lookup_lead_state_tool, name="lookup_lead_state_tool"),
    path("tool/confirm-email/", confirm_email_tool, name="confirm_email_tool"),
]