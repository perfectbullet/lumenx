"""Controlled six-case live probe; no changes to LumenX runtime or project DB."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

import requests

os.environ['NO_PROXY'] = os.environ.get('NO_PROXY', '') + ',192.168.8.231,127.0.0.1,localhost'
os.environ['no_proxy'] = os.environ['NO_PROXY']

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/agents/context/comfy-modalities-live-20261016'
URLS = {'A': 'https://u1114350-7918256b389a.westd.seetacloud.com:8443',
        'B': 'https://u1114350-79216a8ceebf.westd.seetacloud.com:8443'}
ARCHIVER = 'http://192.168.8.231:8610'
TEMPLATES = Path(__file__).with_name('comfy-probe-workflows')
CASES = ['tts', 'image', 'h3']
LOCK = threading.Lock()
RESULTS = {}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def event(key, **value):
    with LOCK:
        RESULTS.setdefault(key, {}).update(value)
        write(OUT / 'results.json', RESULTS)
        display = {k: v for k, v in value.items() if k != 'files'}
        if 'files' in value:
            display['files'] = [{'local': f['local'], 'bytes': f['bytes'], 'decode_ok': f['decode_ok']} for f in value['files']]
        print(json.dumps({'case': key, **display}, ensure_ascii=False), flush=True)


def req(url, method='GET', payload=None):
    response = requests.request(method, url, json=payload, timeout=(15, 90))
    response.raise_for_status()
    return response.json() if response.content else {}


def idle(base):
    queue = req(base + '/queue')
    return not queue['queue_running'] and not queue['queue_pending']


def upload(base, path):
    with path.open('rb') as image:
        response = requests.post(base + '/upload/image', files={'image': (path.name, image, 'image/png')},
                                 data={'type': 'input', 'subfolder': 'lumenx_probe_20261016', 'overwrite': 'false'}, timeout=60)
    response.raise_for_status()
    info = response.json()
    return '/'.join(x for x in [info.get('subfolder'), info['name']] if x)


def template(name, label):
    graph = json.loads((TEMPLATES / name).read_text())
    for node in graph.values():
        if node['class_type'] in ['SaveImage', 'SaveAudio', 'SaveVideo']:
            node['inputs']['filename_prefix'] = f'lumenx_probe/{label}'
    return graph


def tts_workflow(label):
    return template('qwen3-tts-custom-voice.api.json', label + '_tts')


def image_workflow(label):
    return template('qwen-image-2.1-t2i.api.json', label + '_image')


def video_workflow(label, reference):
    graph = template('minimax-h3-ref2va.api.json', label + '_h3')
    for node in graph.values():
        if node['class_type'] == 'CSH3MultimodalDirector':
            timeline = json.loads(node['inputs']['timeline_data'])
            for item in timeline.get('items', []):
                if item.get('file') == '__REFERENCE_IMAGE__':
                    item['file'] = reference
                    item['name'] = reference
            node['inputs']['timeline_data'] = json.dumps(timeline, ensure_ascii=False)
    return graph


def probe(label, kind, graph):
    base, key = URLS[label], label + '-' + kind
    folder = OUT / key
    write(folder / 'prompt.json', graph)
    if not idle(base):
        event(key, status='blocked', reason='Instance queue is not empty; no generation submitted')
        return None
    started = time.time()
    response = requests.post(base + '/prompt', json={'prompt': graph, 'client_id': str(uuid.uuid4())}, timeout=90)
    write(folder / 'submit.json', response.json())
    if response.status_code != 200:
        event(key, status='validation_failed', http_status=response.status_code)
        return None
    prompt_id = response.json()['prompt_id']
    event(key, status='running', prompt_id=prompt_id, started_at=datetime.now(timezone.utc).isoformat())
    deadline = time.monotonic() + 1800
    history = None
    while time.monotonic() < deadline:
        try:
            history = req(base + '/history/' + prompt_id).get(prompt_id)
            if history:
                break
        except requests.RequestException:
            pass  # GET can retry; never resubmit POST after uncertain delivery.
        time.sleep(5)
    if not history:
        event(key, status='unresolved', elapsed_seconds=round(time.time()-started, 2))
        return None
    write(folder / 'history.json', history)
    status = history.get('status', {})
    if status.get('status_str') != 'success':
        errors = [msg[1] for msg in status.get('messages', []) if msg[0] in ['execution_error', 'execution_interrupted']]
        event(key, status='execution_failed', elapsed_seconds=round(time.time()-started, 2),
              errors=[{k: x.get(k) for k in ['node_id', 'node_type', 'exception_type', 'exception_message']} for x in errors])
        return None
    files = []
    for node_id, output in history.get('outputs', {}).items():
        for output_kind, items in output.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get('filename'):
                    continue
                params = {k: item[k] for k in ['filename', 'subfolder', 'type'] if k in item}
                response = requests.get(base + '/view', params=params, timeout=120)
                response.raise_for_status()
                local = folder / Path(item['filename']).name
                local.write_bytes(response.content)
                result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(local)], capture_output=True, text=True)
                media = json.loads(result.stdout) if result.returncode == 0 else {}
                media.get('format', {}).pop('tags', None)
                for stream in media.get('streams', []):
                    stream.pop('tags', None)
                decode = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(local), '-f', 'null', '-'], capture_output=True, text=True)
                files.append({'node_id': node_id, 'output_kind': output_kind, 'remote': params, 'local': str(local.relative_to(ROOT)) if local.is_relative_to(ROOT) else str(local),
                              'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest(),
                              'ffprobe': media, 'decode_ok': decode.returncode == 0})
    event(key, status='success' if files else 'no_outputs', elapsed_seconds=round(time.time()-started, 2), files=files)
    return folder / Path(files[0]['local']).name if files else None


def image_edit_workflow(label, reference):
    graph = template('qwen-image-2.1-i2i.api.json', label + '_image_edit')
    graph['44']['inputs']['image'] = reference
    return graph


def free_and_observe(label, stage):
    """The native endpoint acknowledges before VRAM has necessarily returned."""
    base = URLS[label]
    if not idle(base):
        return False
    req(base + '/free', 'POST', {'unload_models': True, 'free_memory': True})
    initial = json.loads((OUT / f'{label}-initial-stats.json').read_text())['devices'][0]
    floor = initial['vram_free'] - 1024 ** 3
    observations, stable = [], 0
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        stats = req(base + '/system_stats')
        empty = idle(base)
        free = stats['devices'][0]['vram_free']
        observations.append({'time': datetime.now(timezone.utc).isoformat(), 'queue_empty': empty, 'stats': stats})
        stable = stable + 1 if empty and free >= floor else 0
        write(OUT / f'{label}-cleanup-{stage}.json', {'minimum_free_bytes': floor, 'stable_samples': stable, 'observations': observations})
        if stable >= 2:
            write(OUT / f'{label}-after-{stage}-stats.json', stats)
            return True
        if not empty:
            return False
        time.sleep(3)
    return False


def sequence(label):
    base = URLS[label]
    try:
        for kind in CASES:
            if RESULTS.get(label + '-' + kind, {}).get('status') == 'success':
                continue
            if kind == 'tts':
                graph = tts_workflow(label)
            elif kind == 'image':
                graph = image_workflow(label)
            else:
                reference = upload(base, OUT / 'reference.png')
                graph = image_edit_workflow(label, reference) if kind == 'image_edit' else video_workflow(label, reference)
            probe(label, kind, graph)
            # Avoid mixing models after a timed-out job. Never interrupt a queue.
            if not idle(base):
                event(label, status='stopped_sequence', reason='Queue still occupied')
                return
            if not free_and_observe(label, kind):
                event(label, status='cleanup_unconfirmed', reason='No stable VRAM baseline; stopped before next model')
                return
    except Exception as exc:
        event(label, status='probe_error', error_type=type(exc).__name__, message=str(exc)[:500])


def main():
    global OUT, CASES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs/agents/context' / ('comfy-probe-' + datetime.now().strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--cases', nargs='+', choices=['tts', 'image', 'image_edit', 'h3'], default=CASES)
    parser.add_argument('--reference-image', type=Path, help='Use a local image instead of reading the demonstration project')
    parser.add_argument('--resume', action='store_true', help='Skip successful cases recorded in the selected output directory')
    args = parser.parse_args()
    OUT, CASES = args.output_dir.resolve(), args.cases
    if (OUT / 'results.json').exists() and not args.resume:
        raise SystemExit('Existing results require --resume, or choose a new output directory')
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'results.json').exists():
        RESULTS.update(json.loads((OUT / 'results.json').read_text()))
        RESULTS.pop('A', None)
        RESULTS.pop('B', None)
    if args.reference_image:
        content = args.reference_image.read_bytes()
        write(OUT / 'reference-source.json', {'local_source': str(args.reference_image), 'sha256': hashlib.sha256(content).hexdigest(), 'read_only': True})
    else:
        project = req('http://192.168.8.231:17177/projects/c77dddda-6125-4288-b248-6ad3bbec0192')
        frame = next(f for f in project['frames'] if f.get('image_url'))
        reference = frame['image_url']
        write(OUT / 'reference-source.json', {'project_id': project['id'], 'frame_id': frame['id'], 'media_ref': reference, 'read_only': True})
        url = reference if reference.startswith('http') else 'http://192.168.8.231:17177/files/' + reference.removeprefix('output/')
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        content = response.content
    (OUT / 'reference.png').write_bytes(content)
    servers = req(ARCHIVER + '/api/comfyui-servers')
    server = next(s for s in servers if s['id'] == 'autodl-app')
    assert server['url'].rstrip('/') == URLS['A']
    write(OUT / 'archiver-server-before.json', server)
    original_enabled = server.get('enabled', True)
    req(ARCHIVER + '/api/comfyui-servers/autodl-app', 'PUT', {'enabled': False})
    try:
        time.sleep(6)
        for label, base in URLS.items():
            write(OUT / f'{label}-initial-queue.json', req(base + '/queue'))
            write(OUT / f'{label}-initial-stats.json', req(base + '/system_stats'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(sequence, URLS))
    finally:
        # Do not re-enable a server until all our submitted work has left queue.
        if idle(URLS['A']) and free_and_observe('A', 'restore'):
            result = req(ARCHIVER + '/api/comfyui-servers/autodl-app', 'PUT', {'enabled': original_enabled})
            write(OUT / 'archiver-server-restored.json', result)
            print('A original scheduling state restored', flush=True)
        else:
            print('A queue/cleanup not confirmed: scheduling remains paused; inspect evidence before restoring', flush=True)


if __name__ == '__main__':
    main()
