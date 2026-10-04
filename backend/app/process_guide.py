from __future__ import annotations

from typing import Any

GUIDES: dict[str, list[dict[str, Any]]] = {
    "ind": [
        {
            "topic_keywords": ["collect", "collection", "residence document", "document ready", "ophalen"],
            "topic": "Collecting an IND document",
            "summary": (
                "IND says you should make an appointment only after the message/letter says your document is ready. "
                "The collection page lists items such as a valid passport/travel document and the appointment code."
            ),
            "official_url": "https://ind.nl/en/appointment-to-collect-document",
            "cautions": [
                "Use the location and requirements stated in your own IND letter.",
                "Do not assume a document is ready unless IND says so."
            ],
        },
        {
            "topic_keywords": ["biometric", "biometrics", "fingerprints", "photo", "signature", "vingerafdruk"],
            "topic": "IND biometrics appointment",
            "summary": (
                "IND states that biometrics appointments are for photo, signature and fingerprints and should be made "
                "after receiving the relevant IND letter."
            ),
            "official_url": "https://ind.nl/en/after-your-application/biometrics-appointment-photo-signature-and-fingerprints",
            "cautions": [
                "Follow the exact instructions and location in your letter.",
                "Do not book before the IND communication allows it."
            ],
        },
        {
            "topic_keywords": ["pay", "payment", "application fee", "kosten", "betalen"],
            "topic": "IND application payment",
            "summary": (
                "IND correspondence may require payment before processing continues. The exact amount, payment method "
                "and deadline depend on the application and are stated by IND."
            ),
            "official_url": "https://ind.nl/en/applied-for-a-residence-permit-what-happens-next",
            "cautions": [
                "Use the amount and instructions in your own IND letter/My IND.",
                "Do not pay based only on AI-extracted bank details."
            ],
        },
    ],
    "cjib": [
        {
            "topic_keywords": ["fine", "boete", "payment", "pay", "traffic", "verkeersboete"],
            "topic": "CJIB fine payment",
            "summary": (
                "CJIB says the letter states the amount and the date by which the money must be received. "
                "When paying by transfer, the correct payment reference from the letter is important."
            ),
            "official_url": "https://www.cjib.nl/en/id-pay-my-fine",
            "cautions": [
                "Check the 16-digit CJIB number/payment reference on the original letter.",
                "If a deadline has passed or details look suspicious, verify via CJIB directly."
            ],
        },
        {
            "topic_keywords": ["traffic", "verkeersboete", "letter m", "m"],
            "topic": "CJIB traffic-fine procedure",
            "summary": (
                "CJIB explains that traffic-fine notices state the offence and amount and that missing payment deadlines "
                "can lead to reminders and increased amounts."
            ),
            "official_url": "https://www.cjib.nl/en/our-procedures-traffic-fines",
            "cautions": [
                "The exact deadline and amount on your own letter take priority."
            ],
        },
    ],
    "belastingdienst": [
        {
            "topic_keywords": ["tax", "assessment", "aanslag", "payment", "pay", "betalingskenmerk"],
            "topic": "Belastingdienst payment / assessment",
            "summary": (
                "Belastingdienst requires the correct payment reference for tax-assessment payments. "
                "For payments from abroad, it warns that processing can take extra time."
            ),
            "official_url": "https://www.belastingdienst.nl/wps/wcm/connect/en/individuals/content/payments-from-abroad",
            "cautions": [
                "Use the payment reference and bank details from current official Belastingdienst information or your assessment.",
                "Do not trust AI-extracted payment details without checking the original document."
            ],
        }
    ],
}


def normalize_org(value: str) -> str:
    lowered = value.lower()
    if "immigratie" in lowered or "naturalisatie" in lowered or "ind" == lowered.strip():
        return "ind"
    if "cjib" in lowered or "centraal justitieel incassobureau" in lowered:
        return "cjib"
    if "belastingdienst" in lowered or "tax administration" in lowered:
        return "belastingdienst"
    return lowered.strip()


def lookup_process(organization: str, topic: str) -> dict[str, Any]:
    key = normalize_org(organization)
    candidates = GUIDES.get(key, [])
    topic_lower = topic.lower()

    if not candidates:
        return {
            "found": False,
            "organization": organization,
            "topic": topic,
            "message": (
                "No curated process guide is available for this organization. "
                "Use the letter itself and the organization's official website as the source of truth."
            ),
        }

    scored = []
    for item in candidates:
        score = sum(1 for keyword in item["topic_keywords"] if keyword in topic_lower)
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    best = scored[0][1]

    return {
        "found": True,
        "organization": organization,
        "topic": best["topic"],
        "summary": best["summary"],
        "official_url": best["official_url"],
        "cautions": best["cautions"],
    }
