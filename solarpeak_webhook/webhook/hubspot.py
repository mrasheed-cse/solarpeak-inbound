import requests
from django.conf import settings

BASE_URL = "https://api.hubapi.com"

HEADERS = {
    "Authorization": f"Bearer {settings.HUBSPOT_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}


def search_contact_by_phone(phone):
    url = f"{BASE_URL}/crm/v3/objects/contacts/search"

    data = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "phone",
                        "operator": "EQ",
                        "value": phone
                    }
                ]
            }
        ]
    }

    response = requests.post(url, json=data, headers=HEADERS, timeout=20)
    results = response.json().get("results", [])

    if results:
        return results[0]["id"]

    return None


def create_contact(properties):
    url = f"{BASE_URL}/crm/v3/objects/contacts"
    response = requests.post(url, json={"properties": properties}, headers=HEADERS, timeout=20)
    return response.status_code, response.json()


def update_contact(contact_id, properties):
    url = f"{BASE_URL}/crm/v3/objects/contacts/{contact_id}"
    response = requests.patch(url, json={"properties": properties}, headers=HEADERS, timeout=20)
    return response.status_code, response.json()


def upsert_contact(properties):
    """
    Upsert by:
    1. Email if present
    2. Otherwise phone lookup
    """

    email = properties.get("email")
    phone = properties.get("phone")

    # Try create first if email exists (HubSpot auto-handles duplicates by email)
    if email:
        status, data = create_contact(properties)
        if status in [200, 201]:
            return status, data

    # If create fails or no email, try phone lookup
    if phone:
        contact_id = search_contact_by_phone(phone)
        if contact_id:
            return update_contact(contact_id, properties)

    # Fallback create
    return create_contact(properties)