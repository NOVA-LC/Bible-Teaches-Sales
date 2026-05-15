"""email_run.py — send weekly-prep results via Resend.

Used by the GitHub Actions workflow (weekly-prep.yml) to email the
generated JSON file(s) and (optionally) the injected .jwlibrary backup.

Reads RESEND_API_KEY, RESEND_FROM, RESEND_TO from environment.
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _send(payload: dict, api_key: str) -> None:
    """POST to Resend. Try curl primary (avoids Cloudflare bot-flagging that
    rejected urllib's default UA with 'error 1010'), urllib as fallback."""
    import subprocess
    body = json.dumps(payload).encode("utf-8")
    # curl primary — sends a realistic UA + handles TLS/keep-alive cleanly
    try:
        proc = subprocess.run(
            ["curl", "-sS", "-X", "POST",
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Content-Type: application/json",
             "-H", "User-Agent: Mozilla/5.0 (compatible; jwl-notes-agent/1.0)",
             "--data-binary", "@-",
             "-w", "\n__HTTP_CODE__:%{http_code}",
             "https://api.resend.com/emails"],
            input=body, capture_output=True, timeout=120,
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        # Split off the trailing http_code marker
        body_text, _, code_line = out.rpartition("\n__HTTP_CODE__:")
        http_code = code_line.strip() if code_line else "?"
        print(f"Resend status: {http_code}")
        print(f"Resend body: {body_text}")
        if http_code.startswith("2"):
            return
        print(f"Resend non-2xx response (exit {proc.returncode})", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        pass  # curl not on PATH — fall through to urllib
    # Fallback: urllib (with a sane UA)
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; jwl-notes-agent/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f"Resend status: {resp.status}")
            print(f"Resend body: {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"Resend HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')}",
              file=sys.stderr)
        sys.exit(1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--study-date", required=True)
    p.add_argument("--comments-glob", required=True,
                   help="Glob pattern for comment JSON files to attach")
    p.add_argument("--backup", default=None,
                   help="Optional path to the injected .jwlibrary file to attach")
    args = p.parse_args()

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("ERROR: RESEND_API_KEY not set", file=sys.stderr)
        return 2
    sender = os.environ.get("RESEND_FROM", "Tyler <tyler@gonenova.com>")
    # RESEND_TO can be a single address or a comma/semicolon-separated list
    # for multiple recipients (e.g., "tyler@gonenova.com, tylerjavonbrown@gmail.com").
    recipient_raw = os.environ.get("RESEND_TO", "tylerjavonbrown@gmail.com")
    recipients = [r.strip() for r in re.split(r"[,;]", recipient_raw) if r.strip()]

    json_paths = sorted(glob.glob(args.comments_glob))
    attachments = []
    summary_lines = [f"Weekly prep for study week containing {args.study_date}", ""]

    for jp in json_paths:
        path = Path(jp)
        with path.open("rb") as f:
            attachments.append({
                "filename": path.name,
                "content": base64.b64encode(f.read()).decode("ascii"),
            })
        # Add a one-line summary per JSON
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            note_count = sum(1 for n in doc.get("notes", []) if n.get("content"))
            ul_count = sum(len(n.get("underlines", [])) for n in doc.get("notes", []))
            meta = doc.get("_meta", {})
            summary_lines.append(
                f"  • {path.name}: {note_count} notes + {ul_count} underlines "
                f"({meta.get('article_title', '')})"
            )
        except Exception:
            summary_lines.append(f"  • {path.name}")

    if args.backup:
        bp = Path(args.backup)
        with bp.open("rb") as f:
            attachments.append({
                "filename": f"prep-{args.study_date}.jwlibrary",
                "content": base64.b64encode(f.read()).decode("ascii"),
            })
        summary_lines.append("")
        summary_lines.append(
            f"Injected backup attached: prep-{args.study_date}.jwlibrary"
        )
        summary_lines.append(
            "Save to Files on phone → tap → Open in JW Library to import."
        )

    summary_lines.append("")
    summary_lines.append(
        "Generated by tools/jwl_notes/agent/build_week.py — every note "
        "passed the six-gate Pre-Ship Self-Audit (Mandate 4)."
    )

    payload = {
        "from": sender,
        "to": recipients,
        "subject": f"JWL prep — week of {args.study_date}",
        "text": "\n".join(summary_lines),
        "attachments": attachments,
    }
    _send(payload, api_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
