import uuid
from django.db import models


class Lead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    firstname = models.CharField(max_length=100, blank=True)
    lastname = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=True)

    qualification_result = models.CharField(max_length=20, blank=True)
    disqualification_reason = models.TextField(blank=True)

    # Conversation State Fields
    current_step = models.CharField(max_length=100, blank=True)  

    # e.g. "homeownership", "bill", "timeline", "collecting_contact"

    is_completed = models.BooleanField(default=False)

    status = models.CharField(max_length=20, default="new")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



class Call(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="calls")

    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)

    duration_seconds = models.IntegerField(default=0)
    ended_reason = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)



class ConfirmedEmail(models.Model):
    call_id = models.CharField(primary_key=True, max_length=100)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
