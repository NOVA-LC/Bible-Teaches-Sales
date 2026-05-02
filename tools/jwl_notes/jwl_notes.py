#!/usr/bin/env python3
"""jwl_notes.py — inject Study Notes into a JW Library backup (.jwlibrary).

Phase 1: notes only. No underlines / UserMark rows.

Schema convention (derived empirically from Tyler's userData.db, May 2026):
    For Watchtower study articles, a paragraph-anchored note is:
        BlockType        = 1
        BlockIdentifier  = the paragraph's WOL `data-pid`
        UserMarkId       = NULL (free-floating; no highlight required)

    This places the note in the per-paragraph note slot in JW Library.

    The `data-pid` is *not* the visible paragraph number. In the modern
    Watchtower layout (2026 study issues, e.g. DocumentId 2026280) the
    visible paragraphs are body <p> elements with `class=""` and
    `data-rel-pid="[<question-pid>]"`. The note must anchor to the
    body-paragraph data-pid, not the question's data-pid.

    Older articles (pre-2024-ish) attached notes to the `class="qu"`
    question block or `class="sd"` review-box block; in either case
    BlockType=1 and BlockIdentifier=data-pid still holds. Some of
    Tyler's older notes additionally have a UserMark (highlight)
    pointing at the same Identifier; the note itself still uses
    BlockType=1 + BlockIdentifier=data-pid.

    Bible verse notes (KeySymbol='nwtsty', etc.) use BlockType=2 with
    BlockIdentifier=verse-number; this tool does not currently emit
    those — pass an explicit `block_type` per note if needed.

Workflow:
    1. Export a backup from JW Library on any device.
    2. Run this tool against the .jwlibrary file.
    3. Import the new file in JW Library.

Example:
    python jwl_notes.py \\
        --input  MyBackup.jwlibrary \\
        --output MyBackup-with-notes.jwlibrary \\
        --comments comments/2026-05-03.json

Comments JSON shape (current):

    {
      "issue": 20260200,
      "key_symbol": "w",
      "document_id": 2026280,
      "title_contains": "Are You Prepared",
      "default_block_type": 1,
      "notes": [
        {
          "paragraph": 2,        # visible paragraph number (informational)
          "data_pid": 8,         # WOL data-pid — the actual anchor
          "block_type": 1,       # optional override; defaults to default_block_type
          "title": null,
          "content": "..."
        }
      ]
    }

Backward compat: a top-level `block` field on each note is still accepted
and treated as `data_pid` (which is what the wire schema actually wants).
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


def _resolve_anchor(note: dict, default_block_type: int) -> tuple[int, int]:
    """Return (block_type, block_identifier) for a note dict.

    Accepts either the new explicit form (`data_pid` + optional `block_type`)
    or the old form (`block`, treated as data_pid).
    """
    if "data_pid" in note and isinstance(note["data_pid"], int):
        ident = note["data_pid"]
    elif "block" in note and isinstance(note["block"], int):
        ident = note["block"]
    else:
        raise ValueError("note must include 'data_pid' (int) or legacy 'block' (int)")
    bt = note.get("block_type", default_block_type)
    if not isinstance(bt, int) or bt not in (1, 2):
        raise ValueError(f"block_type must be 1 or 2, got {bt!r}")
    return bt, ident


def load_comments(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        spec = json.load(f)
    if "issue" not in spec:
        sys.exit("comments file must include 'issue' (e.g. 20260200)")
    if "notes" not in spec or not isinstance(spec["notes"], list) or not spec["notes"]:
        sys.exit("comments file must include a non-empty 'notes' array")
    default_bt = spec.get("default_block_type", 1)
    if default_bt not in (1, 2):
        sys.exit(f"default_block_type must be 1 or 2, got {default_bt!r}")
    for i, n in enumerate(spec["notes"]):
        try:
            _resolve_anchor(n, default_bt)
        except ValueError as e:
            sys.exit(f"note #{i}: {e}")
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


def existing_anchors(conn: sqlite3.Connection, location_id: int) -> set[tuple[int, int]]:
    """Set of (BlockType, BlockIdentifier) pairs already noted at this Location."""
    cur = conn.cursor()
    cur.execute(
        "SELECT BlockType, BlockIdentifier FROM Note "
        "WHERE LocationId = ? AND BlockIdentifier IS NOT NULL",
        (location_id,),
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def insert_notes(
    conn: sqlite3.Connection,
    location_id: int,
    notes: list[dict],
    default_block_type: int,
) -> tuple[list[int], list[tuple[int, int]]]:
    existing = existing_anchors(conn, location_id)
    cur = conn.cursor()
    now = now_iso()
    inserted: list[int] = []
    skipped: list[tuple[int, int]] = []
    for n in notes:
        bt, ident = _resolve_anchor(n, default_block_type)
        if (bt, ident) in existing:
            skipped.append((bt, ident))
            continue
        cur.execute(
            """
            INSERT INTO Note
                (Guid, UserMarkId, LocationId, Title, Content,
                 LastModified, Created, BlockType, BlockIdentifier)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                location_id,
                n.get("title"),
                n["content"],
                now,
                now,
                bt,
                ident,
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
    default_bt = spec.get("default_block_type", 1)

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
            inserted, skipped = insert_notes(conn, loc["LocationId"], spec["notes"], default_bt)
            conn.commit()
        finally:
            conn.close()

        if skipped:
            print(f"Skipped (BlockType, BlockIdentifier) already noted: {skipped}")
        print(f"Inserted {len(inserted)} note(s); NoteIds={inserted}")

        if not inserted:
            sys.exit("Nothing to write — every paragraph already has a note. No output produced.")

        update_manifest(manifest_path, db_path)
        repackage(work, args.output)
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
