#!/usr/bin/env python3
"""verify_merge.py — simulate JW Library's import on a freshly-injected backup.

Background
----------
JW Library's "Restore" import isn't a straight overwrite — it merges the imported
backup against the device's current state. The merge gates on several pieces of
state, including the global LastModified timestamp inside userData.db, conflict
detection on (LocationId, BlockType, BlockIdentifier) for Notes, and similar keys
for UserMark / BlockRange.

Until this script existed, the only way to verify a fresh injection was to email
it to the operator, have them Restore on their phone, and report back. Painful
loop. This verifier runs the merge logic locally so the tool can self-check
before delivery.

How
---
The verifier uses sircharlo's `jwl-backup-merger` Python tool, which implements
JW Library's merge semantics for schema v16 backups. We invoke it as a
subprocess, then inspect the merged DB to confirm each of our newly-inserted
NoteIds (and UserMarkIds) survives the merge.

Pass criterion: every new row in `output.jwlibrary` (not present in
`input.jwlibrary`) is also present in the merge of (input + output) by the
same content/anchor key.

Fail mode: any new row missing from the merge → JW Library will silently drop
it on Restore.

Usage
-----
    python verify_merge.py <input.jwlibrary> <output.jwlibrary>

Returns exit 0 if all new rows survive merge, 1 otherwise.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_URL = "https://github.com/sircharlo/jwl-backup-merger.git"


def _open_db(jwlibrary_path: Path, work_dir: Path) -> sqlite3.Connection:
    extract = work_dir / jwlibrary_path.stem
    extract.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jwlibrary_path) as zf:
        zf.extractall(extract)
    return sqlite3.connect(extract / "userData.db")


def _new_rows(input_db: sqlite3.Connection, output_db: sqlite3.Connection) -> dict:
    """Return rows present in output but not in input, keyed by (table, anchor_tuple)."""
    new = {"Note": [], "UserMark": [], "BlockRange": []}

    in_notes = {(r[0],) for r in input_db.execute("SELECT Guid FROM Note")}
    for r in output_db.execute("SELECT NoteId, Guid, BlockType, BlockIdentifier, LocationId, substr(Content,1,80) FROM Note"):
        if (r[1],) not in in_notes:
            new["Note"].append(r)

    in_um = {(r[0],) for r in input_db.execute("SELECT UserMarkGuid FROM UserMark")}
    for r in output_db.execute("SELECT UserMarkId, UserMarkGuid, ColorIndex FROM UserMark"):
        if (r[1],) not in in_um:
            new["UserMark"].append(r)

    in_br = {tuple(r) for r in input_db.execute("SELECT BlockType, Identifier, StartToken, EndToken, UserMarkId FROM BlockRange")}
    for r in output_db.execute("SELECT BlockType, Identifier, StartToken, EndToken, UserMarkId FROM BlockRange"):
        if tuple(r) not in in_br:
            new["BlockRange"].append(r)

    return new


def _ensure_merger(work_dir: Path) -> Path:
    """Clone sircharlo's merger into a temp dir if not already cached."""
    cache = Path.home() / ".cache" / "jwl_notes" / "jwl-backup-merger"
    if (cache / "jw-backup-merger.py").exists():
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        shutil.rmtree(cache)
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(cache)], check=True,
                   capture_output=True)
    return cache


def _run_merger(merger_dir: Path, input_path: Path, output_path: Path,
                merged_out_dir: Path) -> Path:
    """Run sircharlo's merger and return the produced .jwlibrary file path."""
    merger_dir = merger_dir.resolve()
    folder = merged_out_dir / "in"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(input_path, folder / "input.jwlibrary")
    shutil.copy(output_path, folder / "output.jwlibrary")
    out_dir = merged_out_dir / "out"
    out_dir.mkdir(exist_ok=True)
    proc = subprocess.run(
        ["python3", str(merger_dir / "jw-backup-merger.py"),
         "--folder", str(folder)],
        cwd=str(merger_dir),
        input="y\n",
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"merger failed:\n{proc.stdout}\n{proc.stderr}")
    # The merger outputs to <repo>/merged/UserdataBackup_*.jwlibrary
    merged_files = sorted((merger_dir / "merged").glob("*.jwlibrary"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
    if not merged_files:
        raise RuntimeError("merger produced no output")
    final = out_dir / "merged.jwlibrary"
    shutil.copy(merged_files[0], final)
    return final


def verify(input_path: Path, output_path: Path) -> bool:
    """Run the merge simulation. Return True if all new rows survive."""
    with tempfile.TemporaryDirectory(prefix="jwl_verify_") as td:
        td = Path(td)
        in_conn = _open_db(input_path, td)
        out_conn = _open_db(output_path, td)
        new = _new_rows(in_conn, out_conn)
        n_notes = len(new["Note"])
        n_um = len(new["UserMark"])
        n_br = len(new["BlockRange"])
        print(f"Output adds {n_notes} Note(s), {n_um} UserMark(s), {n_br} BlockRange(s) over input.")
        if n_notes + n_um + n_br == 0:
            print("Nothing new to verify.")
            return True

        merger_dir = _ensure_merger(td)
        merged_path = _run_merger(merger_dir, input_path, output_path, td)
        merged_conn = _open_db(merged_path, td)

        merged_note_guids = {r[0] for r in merged_conn.execute("SELECT Guid FROM Note")}
        merged_um_guids = {r[0] for r in merged_conn.execute("SELECT UserMarkGuid FROM UserMark")}
        # BlockRange has no GUID — match by (BlockType, Identifier, StartToken, EndToken)
        merged_br = {tuple(r) for r in merged_conn.execute(
            "SELECT BlockType, Identifier, StartToken, EndToken FROM BlockRange")}

        survived_notes = sum(1 for r in new["Note"] if r[1] in merged_note_guids)
        survived_um = sum(1 for r in new["UserMark"] if r[1] in merged_um_guids)
        survived_br = sum(1 for r in new["BlockRange"] if r[:4] in merged_br)

        print(f"Notes      survived merge: {survived_notes}/{n_notes}")
        print(f"UserMarks  survived merge: {survived_um}/{n_um}")
        print(f"BlockRanges survived merge: {survived_br}/{n_br}")

        if survived_notes < n_notes:
            print("\nDropped Notes (would be invisible in JW Library after Restore):")
            for r in new["Note"]:
                if r[1] not in merged_note_guids:
                    print(f"  NoteId={r[0]} Guid={r[1]} BT={r[2]} ident={r[3]} loc={r[4]} content={r[5]!r}")
        if survived_um < n_um:
            print("\nDropped UserMarks:")
            for r in new["UserMark"]:
                if r[1] not in merged_um_guids:
                    print(f"  UserMarkId={r[0]} Guid={r[1]} color={r[2]}")

        all_ok = (survived_notes == n_notes and survived_um == n_um and survived_br == n_br)
        print("\n" + ("PASS — JW Library will accept this backup."
                       if all_ok else "FAIL — some rows would be silently dropped on Restore."))
        return all_ok


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simulate JW Library's merge to verify a freshly-injected backup."
    )
    p.add_argument("input", type=Path, help="Original .jwlibrary file (pre-injection)")
    p.add_argument("output", type=Path, help="Injected .jwlibrary file (post-injection)")
    args = p.parse_args()
    if not args.input.exists() or not args.output.exists():
        sys.exit("input or output file not found")
    return 0 if verify(args.input, args.output) else 1


if __name__ == "__main__":
    sys.exit(main())
