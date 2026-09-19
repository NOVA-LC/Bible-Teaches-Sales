"""Create reusable local article/reference JSON without model calls.

Read saved official article HTML; metadata is explicit so a wrong discovery result
cannot silently select another study. Private reference notes stay in ignored runs.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from .build_week import scrape_article
from .prep_session import atomic_json


def article_from_html(html: str, metadata: dict) -> dict:
    paragraphs = scrape_article(html)
    if not paragraphs or not any(p.question_pid is not None for p in paragraphs):
        raise ValueError('No study paragraphs/questions found; check the saved official article HTML')
    return {'article_meta': metadata, 'paragraphs': [asdict(p) for p in paragraphs]}


def extract_references(backup: Path, document_id: int, key_symbol: str) -> list[str]:
    """Read only explicitly selected publication notes; never modify the backup."""
    if type(document_id) is not int or document_id <= 0 or not key_symbol:
        raise ValueError('Explicit positive document ID and publication key required')
    with zipfile.ZipFile(backup) as archive, tempfile.TemporaryDirectory() as tmp:
        # Extract one known member, not arbitrary archive paths or other private data.
        db = Path(tmp)/'userData.db'
        db.write_bytes(archive.read('userData.db'))
        connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
        try:
            connection.execute('PRAGMA query_only=ON')
            rows = connection.execute(
                'SELECT n.Content FROM Note n JOIN Location l ON n.LocationId=l.LocationId '
                'WHERE l.DocumentId=? AND l.KeySymbol=? AND n.Content IS NOT NULL '
                'ORDER BY n.BlockIdentifier,n.NoteId', (document_id,key_symbol)).fetchall()
        finally:
            connection.close()
    notes = [text for (text,) in rows if text.strip()]
    if not notes:
        raise ValueError('No notes found for the explicitly selected article')
    return notes


def save_snapshot(path: Path, value) -> None:
    """An identical repeat is a no-op; changed inputs need a new snapshot path."""
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != value:
            raise ValueError(f'{path} already contains different inputs; choose a new run directory')
        return
    atomic_json(path,value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    article = commands.add_parser('article')
    article.add_argument('--html',type=Path,required=True)
    article.add_argument('--metadata-json',type=Path,required=True)
    article.add_argument('--output',type=Path,required=True)
    refs = commands.add_parser('references')
    refs.add_argument('--backup',type=Path,required=True)
    refs.add_argument('--document-id',type=int,required=True)
    refs.add_argument('--key-symbol',required=True)
    refs.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'article':
            result = article_from_html(args.html.read_text(encoding='utf-8'), json.loads(args.metadata_json.read_text(encoding='utf-8')))
        else:
            result = extract_references(args.backup,args.document_id,args.key_symbol)
        save_snapshot(args.output,result)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,sqlite3.Error) as exc:
        parser.exit(2,f'{exc}\n')
    print(f'Saved {args.command} snapshot: {args.output}')
    return 0

if __name__ == '__main__': raise SystemExit(main())
