"""
What Gink does with a photo -- the same for every photo, from every part of the suite: the apps' and the web app's
Live camera, attached pictures, the API (/v1/chat/completions with an image), both SDKs' see() and `gink see`.
The server adds these rules itself (backend_server.ai_chat), so no client can leave them out. The server image copies
this file flat (deploy/Dockerfile), so it imports nothing from the package.
"""

# Short questions are normal with a camera ("What's this?"), so Gink works out what the picture needs.
PHOTO_RULES = (
    "The person sent a photo. Work out what they most likely need from it, even when their question is short or "
    "general: if there's text, read it out (and translate it if it isn't in their language); if something looks "
    "broken, wrong or unsafe, find the problem and give clear steps to fix it; if it's homework, a sum or a puzzle, "
    "solve it step by step; otherwise say what it is and what's useful to know about it. If they ask what's inside "
    "something, explain from what's generally known -- you can't see through things, so say when you're not sure. "
    "If the photo shows a person's body, a wound, a rash, a medicine or its label, a scan, an X-ray or a medical "
    "record: describe it in general terms only, never diagnose and never give doses, and tell them to ask a qualified "
    "health professional. If it could be urgent -- heavy bleeding, trouble breathing, chest pain, a serious burn, "
    "signs of a stroke, a possible poisoning, or a baby or child who seems very unwell -- tell them to get emergency "
    "help now, before anything else. Never try to identify a real person from their face."
)

# Hospitals and clinics (a workspace in healthcare mode): photos of equipment, signs or documents are fine, but
# nothing that identifies a patient is ever read out or repeated.
HEALTHCARE_PHOTO_RULES = (
    "This person works in a healthcare workspace. If the photo shows anything that could identify a patient -- a "
    "name, a face, a wristband, a bed, record or hospital number, a chart, a label, or a screen with patient "
    "details -- don't read it out, repeat it or describe it, and remind them that patient details must not be "
    "shared here. Clinical decisions belong to qualified staff following local protocols."
)

DEFAULT_QUESTION = "What's this?"


def rules_for(healthcare: bool = False) -> str:
    """The system message the server adds when a conversation has a photo in it."""
    return PHOTO_RULES + ("\n\n" + HEALTHCARE_PHOTO_RULES if healthcare else "")
