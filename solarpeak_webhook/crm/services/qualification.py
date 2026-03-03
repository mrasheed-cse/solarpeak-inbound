def detect_qualification(transcript: str):
    t = (transcript or "").lower()

    if "higher energy usage" in t:
        return "Disqualified", "Low electricity bill"
    if "require homeowner approval" in t:
        return "Disqualified", "Not homeowner"
    if "ready to install within a year" in t:
        return "Disqualified", "Timeline beyond 12 months"

    if "specialist will contact you" in t or "we look forward to helping you go solar" in t:
        return "Qualified", ""

    return "Unknown", ""


def detect_current_step(transcript: str):
    t = (transcript or "").lower()

    if "homeowner" not in t:
        return "homeownership"
    if "electricity bill" not in t:
        return "bill"
    if "within the next 12 months" not in t:
        return "timeline"
    if any(x in t for x in ["full name", "phone number", "property address", "email"]):
        return "collecting_contact"

    return "unknown"