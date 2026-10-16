"""One-time backend-only cutover; settings arrive over stdin, never in argv."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.request
from urllib.parse import urlsplit, urlunsplit

BASE = Path('/data/aigc/lumenx')
PYTHON = Path('/home/zenking/miniconda3/envs/lumenx/bin/python')
STAGE = Path('/tmp/lumenx-mongodb-20261016')
FILES = ['src/persistence.py', 'src/apps/comic_gen/api.py', 'src/apps/comic_gen/pipeline.py',
         'src/apps/playground/storage.py', 'scripts/migrate_json_to_mongodb.py', 'scripts/backup_mongodb.py']
EXPECTED = {
    'src/apps/comic_gen/api.py': '5c9b54963d6ef9e70b837972824e38200fe9e73ac5b8b51241ff6b5b48668b45',
    'src/apps/comic_gen/pipeline.py': '7e7e8709123f3855ad0e73394775ea78192d38f49f6635434e40663ce29733a0',
    'src/apps/playground/storage.py': '629031f5b83bd18ebe2be310ab0d20322e5dd3711e436be1c9d3506811ffc595',
}


def read_api(path):
    with urllib.request.urlopen('http://127.0.0.1:17177' + path, timeout=5) as response:
        return json.load(response)


def pids():
    result = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
            if b'uvicorn' in argv and b'src.apps.comic_gen.api:app' in argv and (entry / 'cwd').resolve() == BASE:
                result.append(int(entry.name))
        except OSError:
            pass
    return result


def stop():
    for pid in pids():
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 25
    while pids() and time.monotonic() < deadline:
        time.sleep(.5)
    if pids():
        raise RuntimeError('Backend did not stop gracefully')
    try:
        read_api('/projects/')
    except Exception:
        return
    raise RuntimeError('API listener still exists')


def start():
    with (BASE / 'logs/backend.log').open('ab') as log:
        process = subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'src.apps.comic_gen.api:app',
                                    '--reload', '--host', '0.0.0.0', '--port', '17177'],
                                   cwd=BASE, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    (BASE / 'logs/backend.pid').write_text(str(process.pid) + '\n')
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            return read_api('/projects/')
        except Exception:
            time.sleep(1)
    raise RuntimeError('API startup timeout')


def stable_media(value):
    if isinstance(value, dict):
        return {k: stable_media(v) for k, v in value.items()}
    if isinstance(value, list):
        return [stable_media(v) for v in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        url = urlsplit(value)
        return urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    return value


def main():
    settings = json.load(sys.stdin)
    assert set(settings) == {'MONGODB_URI', 'MONGODB_DATABASE', 'LUMENX_STORAGE_BACKEND'}
    assert settings['LUMENX_STORAGE_BACKEND'] == 'mongodb'
    os.chdir(BASE)
    sys.path.insert(0, str(BASE))
    for name, digest in EXPECTED.items():
        assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == digest, 'Backend source changed'
    for name in FILES:
        assert (STAGE / name).is_file(), 'Missing staged file'
        compile((STAGE / name).read_bytes(), name, 'exec')
    before = read_api('/projects/')
    assert not any(task.get('status') in ('pending', 'processing') for p in before for task in p.get('video_tasks', [])), 'Active video tasks'
    assert len(pids()) == 1, 'Expected exactly one backend supervisor'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    backup = BASE / 'output/backups' / ('mongodb_cutover_' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    names = FILES + ['.env', 'requirements.txt']
    existing = [name for name in names if (BASE / name).exists()]
    for name in existing:
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, target)
    stopped = False
    try:
        stop()
        stopped = True
        for name in FILES:
            shutil.copy2(STAGE / name, BASE / name)
        requirements = (BASE / 'requirements.txt').read_text()
        if not any(line.strip().startswith('pymongo') for line in requirements.splitlines()):
            (BASE / 'requirements.txt').write_text(requirements + '\n# Metadata database\npymongo>=4.10,<5\n')
        from dotenv import set_key
        for key, value in settings.items():
            set_key(str(BASE / '.env'), key, value)
            os.environ[key] = value
        from src.persistence import mongo_database
        from scripts.migrate_json_to_mongodb import migrate, SOURCES
        db = mongo_database()
        report = migrate(db, BASE / 'output', apply=True)
        original_hashes = {name: hashlib.sha256((BASE / 'output' / name).read_bytes()).hexdigest()
                           for name in SOURCES if (BASE / 'output' / name).exists()}
        after = start()
        assert {p['id'] for p in after} == {p['id'] for p in before}, 'Project IDs differ after restart'
        summaries = []
        for project in before:
            current = read_api('/projects/' + project['id'])
            # Full persisted media-bearing structures must survive the switch.
            for field in ['frames', 'video_tasks', 'merged_video_url']:
                assert stable_media(current.get(field)) == stable_media(project.get(field)), 'Media references changed: ' + field
            summaries.append({'id': project['id'], 'frames': len(current.get('frames', [])),
                              'video_tasks': len(current.get('video_tasks', []))})
        assert all(hashlib.sha256((BASE / 'output' / name).read_bytes()).hexdigest() == digest
                   for name, digest in original_hashes.items()), 'Legacy JSON unexpectedly changed'
        # Exercise actual Mongo CRUD/restart loading with an isolated collection,
        # without adding test records to the user's project list.
        from src.persistence import MongoRepository
        collection = '_cutover_probe_' + stamp.replace('.', '_')
        try:
            repo = MongoRepository(db)
            repo.load(collection)
            repo.save(collection, {'probe': {'value': 'created'}})
            restored = MongoRepository(db)
            assert restored.load(collection) == {'probe': {'value': 'created'}}
            restored.save(collection, {'probe': {'value': 'updated'}})
            assert MongoRepository(db).load(collection)['probe']['value'] == 'updated'
            restored.save(collection, {})
            assert db[collection].count_documents({}) == 0
        finally:
            db.drop_collection(collection)
        result = {'applied': True, 'database': db.name, 'code_and_env_backup': str(backup),
                  'json_backup': report['backup'], 'counts': report['counts'], 'projects': summaries,
                  'legacy_json_unchanged': True, 'mongo_crud_verified': True}
        (backup / 'receipt.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    except Exception as exc:
        if stopped:
            stop()
            for name in names:
                if name in existing:
                    shutil.copy2(backup / name, BASE / name)
                elif (BASE / name).exists():
                    (BASE / name).unlink()
            # Original process environment was JSON; restarting reads restored .env.
            for key in settings:
                os.environ.pop(key, None)
            start()
        print(json.dumps({'applied': False, 'rolled_back': stopped, 'error_type': type(exc).__name__,
                          'backup': str(backup)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
