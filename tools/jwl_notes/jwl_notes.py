#!/usr/bin/env python3
"""jwl_notes.py — inject Study Notes into a JW Library backup (.jwlibrary).

Phase 1: notes only. No underlines / UserMark rows.

Workflow:
    1. Export a backup from JW Library on any device.
    2. Run this tool against the .jwlibrary file.
    3. Import the new file in JW Library.

Example:
    python jwl_notes.py \\
        --input  MyBackup.jwlibrary \\
        --output MyBackup-with-notes.jwlibrary \\
        --comments comments/2026-05-03.json

The comments file is JSON of the form:

    {
      "issue": 20260200,
      "key_symbol": "w",
      "title_contains": "Are You Prepared",
      "notes": [
        {"block": 2,  "title": null, "content": "..."},
        {"block": 8,  "title": null, "content": "..."}
      ]
    }

`issue` is the JW Library IssueTagNumber (YYYYMMDD with day = 00 for monthly
issues). `title_contains` and/or `document_id` disambiguate when an issue
contains multiple study articles. The article must already exist as a row
in the Location table — open it once on a JW Library device before exporting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_comments(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        spec = json.load(f)
    if "issue" not in spec:
        sys.exit("comments file must include 'issue' (e.g. 20260200)")
    if "notes" not in spec or not isinstance(spec["notes"], list) or not spec["notes"]:
        sys.exit("comments file must include a non-empty 'notes' array")
    for i, n in enumerate(spec["notes"]):
        if not isinstance(n.get("block"), int):
            sys.exit(f"note #{i}: 'block' must be an int")
        if not isinstance(n.get("content"), str) or not n["content"].strip():
            sys.exit(f"note #{i}: 'content' must be a non-empty string")
    return spec


def find_location(
    conn: sqlite3.Connection,
    key_symbol: str,
    issue: int,
    document_id: int | None,
    title_contains: str | None,
) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT LocationId, DocumentId, Title, MepsLanguage, Type
        FROM Location
        WHERE KeySymbol = ? AND IssueTagNumber = ?
        """,
        (key_symbol, issue),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    if not rows:
        sys.exit(
            f"No Location rows for KeySymbol={key_symbol!r} IssueTagNumber={issue}. "
            "Open the article once on a JW Library device, then export a fresh backup."
        )

    if document_id is not None:
        rows = [r for r in rows if r["DocumentId"] == document_id]
    elif title_contains:
        needle = title_contains.lower()
        rows = [r for r in rows if r["Title"] and needle in r["Title"].lower()]

    if len(rows) == 0:
        sys.exit("No Location row matched the document filter.")
    if len(rows) > 1:
        print(
            "Multiple candidate articles matched. Narrow with --document-id or --title-contains:",
            file=sys.stderr,
        )
        for r in rows:
            print(f"  DocumentId={r['DocumentId']:>5}  Title={r['Title']!r}", file=sys.stderr)
        sys.exit(2)
    return rows[0]


def existing_blocks(conn: sqlite3.Connection, location_id: int) -> set[int]:
    cur = conn.cursor()
    cur.execute(
        "SELECT BlockIdentifier FROM Note "
        "WHERE LocationId = ? AND BlockType = 2 AND BlockIdentifier IS NOT NULL",
        (location_id,),
    )
    return {row[0] for row in cur.fetchall()}


def insert_notes(
    conn: sqlite3.Connection, location_id: int, notes: list[dict]
) -> tuple[list[int], list[int]]:
    skipped = sorted(b for b in (n["block"] for n in notes) if b in existing_blocks(conn, location_id))
    skip_set = set(skipped)
    cur = conn.cursor()
    now = now_iso()
    inserted: list[int] = []
    for n in notes:
        if n["block"] in skip_set:
            continue
        cur.execute(
            """
            INSERT INTO Note
                (Guid, UserMarkId, LocationId, Title, Content,
                 LastModified, Created, BlockType, BlockIdentifier)
            VALUES (?, NULL, ?, ?, ?, ?, ?, 2, ?)
            """,
            (
                str(uuid.uuid4()),
                location_id,
                n.get("title"),
                n["content"],
                now,
                now,
                n["block"],
            ),
        )
        inserted.append(cur.lastrowid)
    return inserted, skipped


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_manifest(manifest_path: Path, db_path: Path) -> None:
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    backup = manifest.get("userDataBackup")
    if not backup:
        sys.exit("manifest.json has no userDataBackup section — not a JW Library backup.")
    backup["hash"] = sha256_file(db_path)
    backup["lastModifiedDate"] = now_iso()
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def repackage(work_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(work_dir.rglob("*")):
            if entry.is_file():
                zf.write(entry, entry.relative_to(work_dir))
    tmp.replace(output)


def main() -> int:
    p = argparse.ArgumentParser(description="Inject Study Notes into a .jwlibrary backup.")
    p.add_argument("--input", required=True, type=Path, help="source .jwlibrary file")
    p.add_argument("--output", required=True, type=Path, help="destination .jwlibrary file")
    p.add_argument("--comments", required=True, type=Path, help="JSON file describing the notes")
    p.add_argument("--document-id", type=int, default=None, help="exact DocumentId to target")
    p.add_argument("--title-contains", type=str, default=None, help="substring match on Location.Title")
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"input not found: {args.input}")

    spec = load_comments(args.comments)
    key_symbol = spec.get("key_symbol", "w")
    issue = int(spec["issue"])
    document_id = args.document_id if args.document_id is not None else spec.get("document_id")
    title_contains = args.title_contains or spec.get("title_contains")

    with tempfile.TemporaryDirectory(prefix="jwl_notes_") as td:
        work = Path(td)
        with zipfile.ZipFile(args.input, "r") as zf:
            zf.extractall(work)

        db_path = work / "userData.db"
        manifest_path = work / "manifest.json"
        if not db_path.exists() or not manifest_path.exists():
            sys.exit("input is not a valid .jwlibrary backup (missing userData.db or manifest.json).")

        conn = sqlite3.connect(db_path)
        try:
            loc = find_location(conn, key_symbol, issue, document_id, title_contains)
            print(
                f"Targeting LocationId={loc['LocationId']} "
                f"DocumentId={loc['DocumentId']} Title={loc['Title']!r}"
            )
            inserted, skipped = insert_notes(conn, loc["LocationId"], spec["notes"])
            conn.commit()
        finally:
            conn.close()

        if skipped:
            print(f"Skipped paragraphs already noted: {skipped}")
        print(f"Inserted {len(inserted)} note(s); NoteIds={inserted}")

        if not inserted:
            sys.exit("Nothing to write — every paragraph already has a note. No output produced.")

        update_manifest(manifest_path, db_path)
        repackage(work, args.output)
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
