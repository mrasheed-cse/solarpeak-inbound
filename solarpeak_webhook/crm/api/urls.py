# from django.urls import path
# from . import views
# from .views import create_lead

# from django.urls import path
# from crm.api import views

from django.urls import path
from . import views

urlpatterns = [
    # path("leads/", views.LeadListCreateView.as_view()),
    # path("leads/<uuid:pk>/", views.LeadDetailView.as_view()),

    # path("leads/", views.create_lead),
    # path("leads/<uuid:lead_id>", views.update_lead),
    # path("calls/<str:call_id>/summary", views.store_call_summary),
    # path("leads", create_lead),

    # path("leads", views.leads_collection, name="leads_collection"),                 # POST, GET
    # path("leads/<uuid:lead_id>", views.lead_detail, name="lead_detail"),           # GET, PATCH
    # path("calls/<str:call_id>/summary", views.call_summary, name="call_summary"),  # POST

    path("leads", views.leads_collection),
    path("leads/<uuid:lead_id>", views.lead_detail),
    path("calls/<str:call_id>/summary", views.call_summary),
]
