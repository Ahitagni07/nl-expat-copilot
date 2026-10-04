from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "handle_it.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _normalise_text(value: str | None) -> str:
    value = (value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalise_due_at(value: str) -> str:
    raw = value.strip()

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.replace(second=0, microsecond=0).isoformat()
    except ValueError:
        return _normalise_text(raw)


def _location_key(value: str | None) -> str:
    """
    Prefer Dutch postcode + house number because model wording around a place
    can vary ("Stadshuis ... Stadsplein 1 ..." vs "Stadsplein 1 ...").
    Postcode + house number identifies the same Dutch address much more
    reliably than comparing the generated location sentence.
    """
    raw = (value or "").strip()

    postcode_match = re.search(
        r"\b(\d{4})\s*([A-Za-z]{2})\b",
        raw,
        flags=re.IGNORECASE,
    )

    if postcode_match:
        postcode = (
            postcode_match.group(1)
            + postcode_match.group(2).upper()
        )

        prefix = raw[: postcode_match.start()]
        house_numbers = re.findall(
            r"\b(\d+[A-Za-z]?)\b",
            prefix,
        )

        if house_numbers:
            return (
                f"nl-address:{postcode.lower()}:"
                f"{house_numbers[-1].lower()}"
            )

        return f"nl-postcode:{postcode.lower()}"

    return _normalise_text(raw)


def _analysis_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    return value if isinstance(value, dict) else {}


def _analysis_score(raw: str | None) -> int:
    """
    Used only when old duplicate rows have to be merged.
    Prefer the richer, successfully structured analysis over a
    'needs_review' fallback.
    """
    data = _analysis_dict(raw)
    if not data:
        return 0

    understanding = data.get("understanding")
    if not isinstance(understanding, dict):
        understanding = {}

    score = 0

    if understanding.get("category") != "needs_review":
        score += 100

    if understanding.get("subject"):
        score += 10

    if understanding.get("simple_summary"):
        score += 10

    action_items = understanding.get("action_items")
    if isinstance(action_items, list):
        score += min(len(action_items), 10) * 4

    for key, weight in (
        ("calendar_actions", 20),
        ("address_actions", 12),
        ("official_guidance", 8),
        ("tool_trace", 6),
    ):
        value = data.get(key)
        if isinstance(value, list) and value:
            score += weight + min(len(value), 10)

    return score


def _infer_kind_location(
    title: str,
    source: str | None,
    notes: str | None,
    analysis_json: str | None,
    stored_kind: str | None = None,
    stored_location: str | None = None,
) -> tuple[str, str | None]:
    if stored_kind:
        return stored_kind, stored_location

    data = _analysis_dict(analysis_json)
    understanding = data.get("understanding")
    if not isinstance(understanding, dict):
        understanding = {}

    category = str(understanding.get("category") or "").strip()

    location = (
        stored_location
        or understanding.get("appointment_location")
    )

    calendar_actions = data.get("calendar_actions")
    if (
        not location
        and isinstance(calendar_actions, list)
        and calendar_actions
        and isinstance(calendar_actions[0], dict)
    ):
        location = calendar_actions[0].get("location")

    address_actions = data.get("address_actions")
    if (
        not location
        and isinstance(address_actions, list)
        and address_actions
        and isinstance(address_actions[0], dict)
    ):
        location = (
            address_actions[0].get("query")
            or address_actions[0].get("display_name")
        )

    combined = " ".join(
        [
            title or "",
            source or "",
            notes or "",
        ]
    ).lower()

    if (
        category == "appointment_or_visit"
        or calendar_actions
        or "appointment" in combined
        or "afspraak" in combined
    ):
        return "appointment", str(location).strip() if location else None

    if category == "payment_required":
        return "payment", None

    if "payment" in combined or "betalen" in combined or "betaling" in combined:
        return "payment", None

    return "other", str(location).strip() if location else None


def _fingerprint(
    *,
    title: str,
    due_at: str,
    source: str | None,
    kind: str | None = None,
    location: str | None = None,
) -> str:
    kind_value = _normalise_text(kind) or "other"
    due_value = _normalise_due_at(due_at)

    if kind_value == "appointment":
        loc_value = _location_key(location)

        # Requirement: same appointment date/time + same place == one item.
        if loc_value:
            canonical = f"appointment|{due_value}|{loc_value}"
        else:
            # Legacy fallback for old rows that never stored appointment location.
            canonical = (
                "appointment|"
                f"{due_value}|{_normalise_text(source)}"
            )
    else:
        # For non-appointment deadlines retain title/source so two different
        # obligations due on the same day do not get merged accidentally.
        canonical = "|".join(
            [
                kind_value,
                due_value,
                _normalise_text(source),
                _normalise_text(title),
            ]
        )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _row_to_deadline(
    row: sqlite3.Row,
    *,
    is_duplicate: bool = False,
) -> dict[str, Any]:
    keys = set(row.keys())

    analysis_json = (
        row["analysis_json"]
        if "analysis_json" in keys
        else None
    )

    return {
        "id": row["id"],
        "title": row["title"],
        "due_at": row["due_at"],
        "source": row["source"],
        "notes": row["notes"],
        "is_duplicate": is_duplicate,
        "has_details": bool(analysis_json),
    }


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                source TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(deadlines)"
            ).fetchall()
        }

        migrations = {
            "fingerprint": "TEXT",
            "analysis_json": "TEXT",
            "kind": "TEXT",
            "location": "TEXT",
        }

        for column, sql_type in migrations.items():
            if column not in columns:
                con.execute(
                    f"ALTER TABLE deadlines "
                    f"ADD COLUMN {column} {sql_type}"
                )

        # Old versions used a title-based fingerprint.
        # Drop the index first, recompute all identities using the new
        # date/time + place rule, then recreate the unique index.
        con.execute(
            "DROP INDEX IF EXISTS idx_deadlines_fingerprint"
        )

        rows = con.execute(
            """
            SELECT
                id,
                title,
                due_at,
                source,
                notes,
                fingerprint,
                analysis_json,
                kind,
                location
            FROM deadlines
            ORDER BY id ASC
            """
        ).fetchall()

        groups: dict[str, list[sqlite3.Row]] = {}

        for row in rows:
            inferred_kind, inferred_location = _infer_kind_location(
                title=row["title"],
                source=row["source"],
                notes=row["notes"],
                analysis_json=row["analysis_json"],
                stored_kind=row["kind"],
                stored_location=row["location"],
            )

            fp = _fingerprint(
                title=row["title"],
                due_at=row["due_at"],
                source=row["source"],
                kind=inferred_kind,
                location=inferred_location,
            )

            con.execute(
                """
                UPDATE deadlines
                SET fingerprint = ?, kind = ?, location = ?
                WHERE id = ?
                """,
                (
                    fp,
                    inferred_kind,
                    inferred_location,
                    row["id"],
                ),
            )

            groups.setdefault(fp, []).append(row)

        # Collapse legacy duplicates. Keep whichever row has the richest valid
        # analysis snapshot; this specifically avoids retaining a later
        # "needs_review" fallback over a good earlier analysis.
        for fp, duplicate_rows in groups.items():
            if len(duplicate_rows) <= 1:
                continue

            best = max(
                duplicate_rows,
                key=lambda row: (
                    _analysis_score(row["analysis_json"]),
                    -row["id"],
                ),
            )

            best_id = best["id"]
            best_analysis = best["analysis_json"]
            best_score = _analysis_score(best_analysis)

            # If another row unexpectedly has richer analysis, copy it.
            for candidate in duplicate_rows:
                score = _analysis_score(candidate["analysis_json"])
                if score > best_score:
                    best_analysis = candidate["analysis_json"]
                    best_score = score

            if best_analysis:
                con.execute(
                    """
                    UPDATE deadlines
                    SET analysis_json = ?
                    WHERE id = ?
                    """,
                    (best_analysis, best_id),
                )

            for candidate in duplicate_rows:
                if candidate["id"] != best_id:
                    con.execute(
                        "DELETE FROM deadlines WHERE id = ?",
                        (candidate["id"],),
                    )

        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_deadlines_fingerprint
            ON deadlines(fingerprint)
            WHERE fingerprint IS NOT NULL
            """
        )

        # Cache exact uploaded documents so uploading the identical PDF/image
        # does not call the model again and cannot produce a different answer.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS document_analyses (
                document_hash TEXT PRIMARY KEY,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        con.commit()


def add_deadline(
    title: str,
    due_at: str,
    source: str | None = None,
    notes: str | None = None,
    *,
    kind: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    kind_value = _normalise_text(kind) or "other"

    fp = _fingerprint(
        title=title,
        due_at=due_at,
        source=source,
        kind=kind_value,
        location=location,
    )

    with _connect() as con:
        existing = con.execute(
            """
            SELECT
                id,
                title,
                due_at,
                source,
                notes,
                analysis_json
            FROM deadlines
            WHERE fingerprint = ?
            LIMIT 1
            """,
            (fp,),
        ).fetchone()

        if existing:
            return _row_to_deadline(
                existing,
                is_duplicate=True,
            )

        try:
            cursor = con.execute(
                """
                INSERT INTO deadlines (
                    title,
                    due_at,
                    source,
                    notes,
                    fingerprint,
                    kind,
                    location
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    due_at,
                    source,
                    notes,
                    fp,
                    kind_value,
                    location,
                ),
            )
            con.commit()
        except sqlite3.IntegrityError:
            existing = con.execute(
                """
                SELECT
                    id,
                    title,
                    due_at,
                    source,
                    notes,
                    analysis_json
                FROM deadlines
                WHERE fingerprint = ?
                LIMIT 1
                """,
                (fp,),
            ).fetchone()

            if existing:
                return _row_to_deadline(
                    existing,
                    is_duplicate=True,
                )
            raise

        row = con.execute(
            """
            SELECT
                id,
                title,
                due_at,
                source,
                notes,
                analysis_json
            FROM deadlines
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_deadline(
        row,
        is_duplicate=False,
    )


def list_deadlines(
    limit: int = 30,
) -> list[dict[str, Any]]:
    with _connect() as con:
        rows = con.execute(
            """
            SELECT
                id,
                title,
                due_at,
                source,
                notes,
                analysis_json
            FROM deadlines
            ORDER BY datetime(due_at) ASC, due_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        _row_to_deadline(row)
        for row in rows
    ]


def attach_analysis_snapshot(
    deadline_ids: list[int],
    analysis: dict[str, Any],
) -> None:
    if not deadline_ids:
        return

    payload = json.dumps(
        analysis,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    new_score = _analysis_score(payload)

    with _connect() as con:
        for deadline_id in set(deadline_ids):
            current = con.execute(
                """
                SELECT analysis_json
                FROM deadlines
                WHERE id = ?
                """,
                (deadline_id,),
            ).fetchone()

            if not current:
                continue

            current_score = _analysis_score(
                current["analysis_json"]
            )

            # Never replace a good saved analysis with a weaker parse/fallback.
            if (
                current["analysis_json"]
                and current_score > new_score
            ):
                continue

            con.execute(
                """
                UPDATE deadlines
                SET analysis_json = ?
                WHERE id = ?
                """,
                (payload, deadline_id),
            )

        con.commit()


def get_deadline_analysis(
    deadline_id: int,
) -> dict[str, Any] | None:
    with _connect() as con:
        row = con.execute(
            """
            SELECT analysis_json
            FROM deadlines
            WHERE id = ?
            """,
            (deadline_id,),
        ).fetchone()

    if not row or not row["analysis_json"]:
        return None

    return _analysis_dict(
        row["analysis_json"]
    ) or None


def get_cached_document_analysis(
    document_hash: str,
) -> dict[str, Any] | None:
    with _connect() as con:
        row = con.execute(
            """
            SELECT analysis_json
            FROM document_analyses
            WHERE document_hash = ?
            """,
            (document_hash,),
        ).fetchone()

    if not row:
        return None

    return _analysis_dict(
        row["analysis_json"]
    ) or None


def save_cached_document_analysis(
    document_hash: str,
    analysis: dict[str, Any],
) -> None:
    payload = json.dumps(
        analysis,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with _connect() as con:
        con.execute(
            """
            INSERT INTO document_analyses (
                document_hash,
                analysis_json
            )
            VALUES (?, ?)
            ON CONFLICT(document_hash)
            DO UPDATE SET
                analysis_json = excluded.analysis_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (document_hash, payload),
        )
        con.commit()

def delete_deadline(deadline_id: int) -> bool:
    """Delete one saved deadline/appointment and invalidate cached analyses."""
    with _connect() as con:
        cursor = con.execute(
            "DELETE FROM deadlines WHERE id = ?",
            (deadline_id,),
        )
        deleted = cursor.rowcount > 0

        if deleted:
            # Cached document analyses contain saved deadline IDs. Clearing this
            # cache ensures a re-upload can recreate the deleted item cleanly.
            con.execute("DELETE FROM document_analyses")

        con.commit()

    return deleted
