#!/usr/bin/env python3
"""Validated, non-destructive JSON import. Default is a read-only dry run.

Stop all JSON writers before --apply. Existing, different MongoDB documents are
never overwritten. If interrupted, rerun with identical source files to resume.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from src.apps.comic_gen.models import Script, Series, GlobalAssetLibrary
from src.apps.playground.models import PlaygroundGeneration, PlaygroundTemplate
from src.persistence import mongo_database, StorageError

SOURCES = {
    'projects.json': ('projects', Script, 'mapping'),
    'series.json': ('series', Series, 'mapping'),
    'library_assets.json': ('asset_libraries', GlobalAssetLibrary, 'singleton'),
    'playground_history.json': ('playground_history', PlaygroundGeneration, 'list'),
    'playground_templates.json': ('playground_templates', PlaygroundTemplate, 'list'),
}


def read_sources(output):
    """Validate every file before connecting or writing; preserve original data."""
    records, files = {}, {}
    if not output.is_dir():
        raise ValueError('Source output directory does not exist')
    for filename, (collection, model, shape) in SOURCES.items():
        path = output / filename
        if not path.exists():
            records[collection] = {}
            continue
        content = path.read_bytes()
        raw = json.loads(content)
        if shape == 'mapping':
            if not isinstance(raw, dict):
                raise ValueError(f'{filename}: expected an object')
            items = raw
        elif shape == 'list':
            if not isinstance(raw, list):
                raise ValueError(f'{filename}: expected an array')
            items = {item['id']: item for item in raw}
            if len(items) != len(raw):
                raise ValueError(f'{filename}: duplicate IDs')
        else:
            items = {'global': raw}
        for key, value in items.items():
            model.model_validate(value)
            if not isinstance(key, str) or not key or (shape != 'singleton' and value.get('id') != key):
                raise ValueError(f'{filename}: invalid or mismatched ID')
        records[collection] = items
        files[filename] = content
    return records, files


def check_target(database, records):
    """Allow an empty target or an exact resumable import; refuse merges."""
    for collection, items in records.items():
        existing = {d['_id']: d for d in database[collection].find({})}
        if existing.keys() - items.keys():
            raise StorageError(f'{collection}: target has additional records; import refused')
        for key in existing:
            if existing[key].get('data') != items[key] or existing[key].get('revision') != 1:
                raise StorageError(f'{collection}: target differs; import refused')


def migrate(database, output, apply=False):
    records, files = read_sources(output)
    check_target(database, records)
    report = {'counts': {name: len(items) for name, items in records.items()}, 'applied': False}
    if not apply:
        return report
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    backup = output / 'backups' / f'pre_mongodb_{stamp}'
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'created_at': stamp, 'sha256': {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }, 'missing': sorted(set(SOURCES) - files.keys()), 'counts': report['counts']}
    for name, content in files.items():
        (backup / name).write_bytes(content)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    # Recheck files after backup, before any database writes.
    _, latest_files = read_sources(output)
    if latest_files != files:
        raise StorageError('JSON files changed during backup; stop the backend and retry')
    from bson import BSON
    for items in records.values():
        for key, data in items.items():
            if len(BSON.encode({'_id': key, 'revision': 1, 'data': data})) >= 16 * 1024 * 1024:
                raise StorageError('A document exceeds MongoDB 16 MiB limit; import refused')
    for collection, items in records.items():
        for key, data in items.items():
            database[collection].update_one({'_id': key}, {'$setOnInsert': {
                'revision': 1, 'data': data,
            }}, upsert=True)
    check_target(database, records)
    # Verify the complete payload, including every media reference, before startup.
    for collection, items in records.items():
        if {d['_id']: d['data'] for d in database[collection].find({})} != items:
            raise StorageError(f'{collection}: verification failed; do not enable MongoDB')
    database.storage_metadata.update_one({'_id': 'json_migration_v1'}, {'$setOnInsert': {
        **manifest, 'backup': str(backup.resolve()),
    }}, upsert=True)
    report.update(applied=True, backup=str(backup.resolve()))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'output')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    try:
        # Validate before the first DB connection as well.
        read_sources(args.output_dir)
        result = migrate(mongo_database(), args.output_dir, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        # Connection exceptions may carry credentials or network details. Never
        # print third-party exception messages or raw validation input.
        detail = str(exc) if isinstance(exc, StorageError) else type(exc).__name__
        print(f'Migration failed: {detail}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
