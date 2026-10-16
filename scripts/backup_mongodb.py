#!/usr/bin/env python3
"""Export LumenX metadata to legacy-compatible JSON for maintenance/rollback.

Stop backend writers first for a coherent multi-collection snapshot. Media files
must be backed up separately. The destination must not already exist.
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
from scripts.migrate_json_to_mongodb import SOURCES
from src.persistence import mongo_database


def backup(database, destination):
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'sha256': {}, 'counts': {}}
    for filename, (collection, model, shape) in SOURCES.items():
        records = {d['_id']: d['data'] for d in database[collection].find({})}
        for data in records.values():
            model.model_validate(data)
        if shape == 'singleton':
            data = records.get('global', {})
        elif shape == 'list':
            data = list(records.values())
            if collection == 'playground_history':
                data.sort(key=lambda item: (item['created_at'], item['id']))
        else:
            data = records
        content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        (destination / filename).write_bytes(content)
        manifest['counts'][collection] = len(records)
        manifest['sha256'][filename] = hashlib.sha256(content).hexdigest()
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    try:
        manifest = backup(mongo_database(), args.destination)
        print(json.dumps({'backup': str(args.destination.resolve()), 'counts': manifest['counts']}, indent=2))
    except Exception as exc:
        print(f'Backup failed: {type(exc).__name__}; do not use an incomplete destination', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
