from __future__ import annotations

from typing import Any

import httpx

from .calendar_utils import create_calendar_artifact
from .db import add_deadline, list_deadlines
from .process_guide import lookup_process

PDOK_SEARCH_URL = "https://api.pdok.nl/kadaster/location-api/v1/search"


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "verify_dutch_address",
                "description": (
                    "Verify/geocode a Netherlands address from the document "
                    "using the current PDOK Location API."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": (
                                "Complete Netherlands address, preferably "
                                "street + number + postcode + city."
                            ),
                        }
                    },
                    "required": ["address"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "prepare_calendar_event",
                "description": (
                    "Prepare a reviewable calendar event. Generates a local "
                    ".ics file and pre-filled Google Calendar link, but does "
                    "not silently add anything to an external calendar."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {
                            "type": "string",
                            "description": (
                                "ISO 8601 local datetime, preferably with "
                                "timezone offset."
                            ),
                        },
                        "end": {
                            "type": "string",
                            "description": (
                                "ISO 8601 local datetime. If absent in the "
                                "document, use one hour only and disclose "
                                "the assumption."
                            ),
                        },
                        "location": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "start",
                        "end",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_deadline",
                "description": (
                    "Idempotently save a meaningful due date or appointment. "
                    "For appointments you MUST set kind='appointment' and pass "
                    "the physical appointment location. The backend treats the "
                    "same appointment date/time + same location as one item "
                    "even if the generated title is worded differently."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "due_at": {
                            "type": "string",
                            "description": "ISO 8601 date or datetime.",
                        },
                        "source": {
                            "type": "string",
                            "description": (
                                "Short issuer label, for example "
                                "Gemeente Nieuwegein, IND or CJIB."
                            ),
                        },
                        "notes": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "appointment",
                                "payment",
                                "response",
                                "other",
                            ],
                            "description": (
                                "Use appointment for a visit/meeting, payment "
                                "for a payment deadline, response for a reply "
                                "deadline, otherwise other."
                            ),
                        },
                        "location": {
                            "type": "string",
                            "description": (
                                "Physical appointment location. Required when "
                                "kind=appointment whenever the document states it."
                            ),
                        },
                    },
                    "required": [
                        "title",
                        "due_at",
                        "kind",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_official_process",
                "description": (
                    "Look up the bundled English process guide for supported "
                    "Dutch authorities such as IND, CJIB or Belastingdienst."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "organization": {
                            "type": "string",
                        },
                        "topic": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "organization",
                        "topic",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_upcoming_deadlines",
                "description": (
                    "Read deadlines previously saved in this local app."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]


async def verify_dutch_address(
    address: str,
) -> dict[str, Any]:
    params = {
        "q": address,
        "adres[version]": 1,
        "adres[relevance]": 0.8,
        "limit": 5,
        "f": "json",
    }

    headers = {
        "Accept": (
            "application/json, "
            "application/geo+json;q=0.9"
        ),
        "User-Agent": "Handle-It-NL/1.0",
    }

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(
            PDOK_SEARCH_URL,
            params=params,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                "PDOK Location API returned "
                f"HTTP {response.status_code}: "
                f"{response.text[:800]}"
            )

        payload = response.json()

    features = payload.get("features") or []

    if not features:
        return {
            "query": address,
            "verified": False,
            "matches": [],
            "message": (
                "PDOK returned no address matches."
            ),
        }

    matches: list[dict[str, Any]] = []

    for feature in features[:5]:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []

        display = (
            props.get("display_name")
            or props.get("weergavenaam")
            or props.get("naam")
            or props.get("omschrijving")
            or address
        )

        lon = None
        lat = None

        if (
            isinstance(coords, list)
            and len(coords) >= 2
        ):
            try:
                lon = float(coords[0])
                lat = float(coords[1])
            except (TypeError, ValueError):
                pass

        matches.append(
            {
                "display_name": str(display),
                "latitude": lat,
                "longitude": lon,
                "properties": props,
            }
        )

    best = matches[0]

    map_url = None
    if (
        best["latitude"] is not None
        and best["longitude"] is not None
    ):
        map_url = (
            "https://www.openstreetmap.org/"
            f"?mlat={best['latitude']}"
            f"&mlon={best['longitude']}"
            f"#map=18/{best['latitude']}/"
            f"{best['longitude']}"
        )

    return {
        "query": address,
        "verified": True,
        "display_name": best["display_name"],
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "map_url": map_url,
        "matches": matches,
    }


async def execute_tool(
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    if name == "verify_dutch_address":
        address = str(
            args.get("address", "")
        ).strip()

        if not address:
            raise ValueError(
                "Address is required."
            )

        return await verify_dutch_address(
            address
        )

    if name == "prepare_calendar_event":
        return create_calendar_artifact(
            title=str(
                args.get("title", "")
            ).strip(),
            start=str(
                args.get("start", "")
            ).strip(),
            end=str(
                args.get("end", "")
            ).strip(),
            location=(
                str(args["location"]).strip()
                if args.get("location")
                else None
            ),
            notes=(
                str(args["notes"]).strip()
                if args.get("notes")
                else None
            ),
        )

    if name == "save_deadline":
        title = str(
            args.get("title", "")
        ).strip()

        due_at = str(
            args.get("due_at", "")
        ).strip()

        kind = str(
            args.get("kind", "other")
        ).strip().lower()

        location = (
            str(args.get("location") or "").strip()
            or None
        )

        if not title or not due_at:
            raise ValueError(
                "title and due_at are required."
            )

        if (
            kind == "appointment"
            and not location
        ):
            # Do not invent a place, but make the missing field visible.
            # DB falls back to due time + source for legacy/ambiguous cases.
            location = None

        return add_deadline(
            title=title,
            due_at=due_at,
            source=(
                str(args.get("source") or "").strip()
                or None
            ),
            notes=(
                str(args.get("notes") or "").strip()
                or None
            ),
            kind=kind,
            location=location,
        )

    if name == "lookup_official_process":
        organization = str(
            args.get("organization", "")
        ).strip()
        topic = str(
            args.get("topic", "")
        ).strip()

        if not organization or not topic:
            raise ValueError(
                "organization and topic are required."
            )

        return lookup_process(
            organization=organization,
            topic=topic,
        )

    if name == "get_upcoming_deadlines":
        try:
            limit = max(
                1,
                min(
                    int(args.get("limit", 10)),
                    30,
                ),
            )
        except (TypeError, ValueError):
            limit = 10

        return {
            "deadlines": list_deadlines(limit)
        }

    raise ValueError(
        f"Unknown tool: {name}"
    )
