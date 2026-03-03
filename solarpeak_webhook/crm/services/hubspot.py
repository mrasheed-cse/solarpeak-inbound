import re
import requests
from django.conf import settings

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {getattr(settings, 'HUBSPOT_ACCESS_TOKEN', '')}",
    "Content-Type": "application/json",
}

def hubspot_create_contact(properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts"
    r = requests.post(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def hubspot_update_contact(contact_id: str, properties: dict):
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}"
    r = requests.patch(url, headers=HUBSPOT_HEADERS, json={"properties": properties}, timeout=20)
    return r.status_code, r.json()

def parse_existing_contact_id(conflict_body: dict):
    msg = (conflict_body or {}).get("message", "") or ""
    m = re.search(r"Existing ID:\s*(\d+)", msg)
    return m.group(1) if m else None

def hubspot_upsert_contact(properties: dict):
    status, body = hubspot_create_contact(properties)
    if status == 409:
        existing_id = parse_existing_contact_id(body)
        if existing_id:
            return hubspot_update_contact(existing_id, properties)
    return status, body