import requests
from django.conf import settings

BASE_URL = "https://api.hubapi.com"

HEADERS = {
    "Authorization": f"Bearer {settings.HUBSPOT_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}


def upsert_contact(email, properties):
    url = f"{BASE_URL}/crm/v3/objects/contacts"
    payload = {
        "properties": {
            "email": email,
            **properties
        }
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def create_note(contact_id, note_body):
    url = f"{BASE_URL}/crm/v3/objects/notes"
    payload = {
        "properties": {
            "hs_note_body": note_body
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 202
                    }
                ]
            }
        ]
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()