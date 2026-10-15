"""One-time recovery of evidenced storyboard media; run on 231, dry-run by default."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.request


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backend_processes(base):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
            if (b'uvicorn' in argv and b'src.apps.comic_gen.api:app' in argv
                    and (entry / 'cwd').resolve() == base):
                found.append(int(entry.name))
        except OSError:
            continue
    return found


def start_backend(base, python):
    with (base / 'logs/backend.log').open('ab') as log:
        proc = subprocess.Popen(
            [str(python), '-m', 'uvicorn', 'src.apps.comic_gen.api:app',
             '--reload', '--host', '0.0.0.0', '--port', '17177'],
            cwd=base, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
    (base / 'logs/backend.pid').write_text(str(proc.pid) + '\n')
    return proc.pid


def get_project(project_id):
    with urllib.request.urlopen('http://127.0.0.1:17177/projects/' + project_id,
                                timeout=5) as response:
        return json.load(response)


def wait_ready(project_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            return get_project(project_id)
        except Exception:
            time.sleep(1)
    raise RuntimeError('Backend did not become ready within 45 seconds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    base = Path('/data/aigc/lumenx').resolve()
    sys.path.insert(0, str(base))
    from src.apps.comic_gen.models import Script
    source = base / 'output/projects.json'
    evidence = json.loads(args.evidence.read_text())
    candidate = json.loads(args.candidate.read_text())
    project_id = evidence['project_id']
    assert candidate['id'] == project_id
    assert digest(source) == evidence['current_projects_sha256'], 'Data changed; regenerate evidence first'
    original = json.loads(source.read_text())
    current = original[project_id]
    assert not current.get('video_tasks'), 'Existing tasks require manual reconciliation'
    assert len(candidate['frames']) == 10 and len(candidate['video_tasks']) == 12
    for image in evidence['old_storyboard_images']:
        assert digest(base / 'output' / image['path']) == image['sha256']
    for task in evidence['old_video_tasks']:
        assert len(task['matching_frames']) == 1
        assert (base / 'output' / task['path']).is_file()
    patched = copy.deepcopy(current)
    # Recover only the requested shot/media associations; retain current entities and settings.
    patched['frames'] = candidate['frames']
    patched['video_tasks'] = candidate['video_tasks']
    patched['merged_video_url'] = candidate['merged_video_url']
    placeholder = candidate['scenes'][0]
    if not any(s['id'] == placeholder['id'] for s in patched['scenes']):
        patched['scenes'].append(placeholder)
    patched['updated_at'] = time.time()
    restored = Script.model_validate(patched).model_dump(mode='json')
    updated = copy.deepcopy(original)
    updated[project_id] = restored
    assert all(updated[k] == v for k, v in original.items() if k != project_id)
    media = sorted({f['image_url'] for f in restored['frames']}
                   | {t['video_url'] for t in restored['video_tasks']}
                   | {restored['merged_video_url']})
    for relative in media:
        assert relative and (base / 'output' / relative).is_file()
    summary = {'project_id': project_id, 'old_current_frames': len(current['frames']),
               'recovered_frames': len(restored['frames']), 'recovered_videos': len(restored['video_tasks']),
               'preserved_characters': len(restored['characters']), 'media_files': len(media)}
    if not args.apply:
        print(json.dumps({'dry_run': True, **summary}, ensure_ascii=False))
        return
    pids = backend_processes(base)
    assert len(pids) == 1, ('Unexpected backend supervisor count', pids)
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
    backup = base / 'output/recovery_backups' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for path in (base / 'output').glob('*.json'):
        shutil.copy2(path, backup / path.name)
    shutil.copy2(args.evidence, backup / 'recovery-evidence.json')
    shutil.copy2(args.candidate, backup / 'candidate.json')
    original_hash = digest(source)
    stopped = False
    changed = False
    try:
        os.kill(pids[0], signal.SIGTERM)
        stopped = True
        deadline = time.monotonic() + 25
        while backend_processes(base) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert not backend_processes(base), 'Backend supervisor did not stop'
        # A graceful reloader stop also closes its child worker and HTTP listener.
        try:
            get_project(project_id)
        except Exception:
            pass
        else:
            raise RuntimeError('HTTP listener remains alive; refusing to write')
        assert digest(source) == original_hash, 'Project changed during shutdown; refusing to overwrite'
        atomic_json(source, updated)
        changed = True
        pid = start_backend(base, Path('/home/zenking/miniconda3/envs/lumenx/bin/python'))
        stopped = False
        result = wait_ready(project_id)
        assert len(result['frames']) == 10 and len(result['video_tasks']) == 12
        assert {f['id'] for f in result['frames']} == {f['id'] for f in restored['frames']}
        for relative in media:
            req = urllib.request.Request('http://127.0.0.1:17177/files/' + relative,
                                         headers={'Range': 'bytes=0-63'})
            with urllib.request.urlopen(req, timeout=10) as response:
                assert response.status in (200, 206) and response.read(64)
        receipt = {'applied': True, **summary, 'backup_dir': str(backup),
                   'backup_sha256': original_hash, 'restored_sha256': digest(source),
                   'backend_pid': pid, 'verified_media_files': len(media)}
        (backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(receipt, ensure_ascii=False))
    except Exception:
        # Stop our own supervisor before restoring a failed modification.
        if changed:
            for pid in backend_processes(base):
                os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 25
            while backend_processes(base) and time.monotonic() < deadline:
                time.sleep(0.5)
            if backend_processes(base):
                raise RuntimeError('Backend still alive; backup retained at ' + str(backup))
            atomic_json(source, original)
            stopped = True
        if stopped:
            start_backend(base, Path('/home/zenking/miniconda3/envs/lumenx/bin/python'))
        raise


if __name__ == '__main__':
    main()
