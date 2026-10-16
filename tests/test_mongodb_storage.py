"""Persistence contracts: migration fidelity, restart, conflict and outage safety."""
import json
from unittest.mock import patch

import mongomock
import pytest
from pymongo.errors import AutoReconnect

from scripts.migrate_json_to_mongodb import migrate
from scripts.backup_mongodb import backup
from src.persistence import MongoRepository, StorageConflict, StorageError, repository_from_env
from src.apps.comic_gen.models import Script, Series, GlobalAssetLibrary, Character
from src.apps.comic_gen.pipeline import ComicGenPipeline
from src.apps.playground.storage import PlaygroundStorage
from src.apps.playground.models import PlaygroundTemplate


@pytest.fixture
def db():
    return mongomock.MongoClient().lumenxdb


def script():
    return Script(id='project-1', title='保留资产', original_text='test', created_at=1, updated_at=1,
                  merged_video_url='video/existing.mp4')


def seed_files(tmp_path):
    project = script().model_dump(mode='json')
    (tmp_path / 'projects.json').write_text(json.dumps({'project-1': project}))
    return project


def test_import_dry_run_backup_and_exact_resume(db, tmp_path):
    project = seed_files(tmp_path)
    original = (tmp_path / 'projects.json').read_bytes()
    report = migrate(db, tmp_path)
    assert not report['applied'] and db.list_collection_names() == []
    report = migrate(db, tmp_path, True)
    assert db.projects.find_one({'_id': 'project-1'})['data'] == project
    assert (tmp_path / 'projects.json').read_bytes() == original
    from pathlib import Path
    assert (Path(report['backup']) / 'projects.json').read_bytes() == original
    assert db.storage_metadata.find_one({'_id': 'json_migration_v1'})
    migrate(db, tmp_path, True)
    assert db.projects.count_documents({}) == 1


def test_invalid_source_never_partially_imported(db, tmp_path):
    seed_files(tmp_path)
    (tmp_path / 'series.json').write_text('{"bad": {"id": "different"}}')
    with pytest.raises(ValueError):
        migrate(db, tmp_path, True)
    assert db.list_collection_names() == []


def test_refuses_overwriting_live_database(db, tmp_path):
    seed_files(tmp_path)
    migrate(db, tmp_path, True)
    db.projects.update_one({'_id': 'project-1'}, {'$set': {'data.title': 'new', 'revision': 2}})
    with pytest.raises(StorageError):
        migrate(db, tmp_path, True)
    assert db.projects.find_one({})['data']['title'] == 'new'


def test_export_can_restore_to_legacy_json_and_fresh_mongodb(db, tmp_path):
    seed_files(tmp_path)
    history = [{'id': 'gen1', 'mode': 't2i', 'model_id': 'demo', 'prompt': 'a cat',
                'created_at': '2026-10-16T00:00:00Z', 'outputs': [
                    {'id': 'out1', 'media_type': 'image', 'media_path': 'playground/images/existing.png'}]}]
    (tmp_path / 'playground_history.json').write_text(json.dumps(history))
    migrate(db, tmp_path, True)
    destination = tmp_path / 'export'
    manifest = backup(db, destination)
    assert manifest['counts']['projects'] == 1
    assert json.loads((destination / 'playground_history.json').read_text()) == history
    restored = mongomock.MongoClient().restored
    migrate(restored, destination, True)
    assert restored.projects.find_one({})['data'] == db.projects.find_one({})['data']
    assert restored.playground_history.find_one({})['data'] == history[0]
    with pytest.raises(FileExistsError):
        backup(db, destination)


def test_independent_changes_and_unknown_documents_are_preserved(db):
    first, second = MongoRepository(db), MongoRepository(db)
    first.load('projects')
    first.save('projects', {'a': {'title': 'A'}, 'b': {'title': 'B'}})
    cached = first.load('projects')
    other = second.load('projects')
    other['b']['title'] = 'new B'
    other['c'] = {'title': 'C'}
    second.save('projects', other)
    cached['a']['title'] = 'new A'
    first.save('projects', cached)
    assert db.projects.find_one({'_id': 'b'})['data']['title'] == 'new B'
    del cached['a']
    first.save('projects', cached)
    assert db.projects.find_one({'_id': 'c'}) is not None


def test_stale_update_and_delete_cannot_overwrite(db):
    first, second = MongoRepository(db), MongoRepository(db)
    first.load('projects')
    first.save('projects', {'a': {'title': 'initial'}})
    first.load('projects')
    second.load('projects')
    second.save('projects', {'a': {'title': 'winner'}})
    with pytest.raises(StorageConflict):
        first.save('projects', {'a': {'title': 'stale'}})
    with pytest.raises(StorageConflict):
        first.save('projects', {})
    assert db.projects.find_one({})['data']['title'] == 'winner'


def test_outage_propagates_without_writing_json(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = MongoRepository(db)
    repo.load('projects')
    with patch.object(db.projects, 'insert_one', side_effect=AutoReconnect('private connection details')):
        with pytest.raises(StorageError, match='MongoDB write failed') as exc:
            repo.save('projects', {'a': {'title': 'A'}})
    assert 'private' not in str(exc.value)
    assert list(tmp_path.iterdir()) == []


def test_startup_requires_migration_and_never_falls_back(db, monkeypatch):
    monkeypatch.setenv('LUMENX_STORAGE_BACKEND', 'mongodb')
    with patch('src.persistence.mongo_database', return_value=db):
        with pytest.raises(StorageError, match='not initialized'):
            repository_from_env()
    monkeypatch.setenv('LUMENX_STORAGE_BACKEND', 'invalid')
    with pytest.raises(StorageError):
        repository_from_env()


def bare_pipeline(db):
    # Avoid model/network initialization: exercise the actual persistence methods.
    pipeline = object.__new__(ComicGenPipeline)
    import threading
    pipeline._save_lock = threading.RLock()
    pipeline._repository = MongoRepository(db)
    pipeline.scripts = pipeline._load_data()
    pipeline.series_store = pipeline._load_series_data()
    pipeline.library_store = pipeline._load_library_data()
    return pipeline


def test_pipeline_crud_survives_restart_without_json(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = bare_pipeline(db)
    pipeline.scripts['project-1'] = script()
    pipeline.series_store['series-1'] = Series(id='series-1', title='Series', created_at=1, updated_at=1)
    pipeline.library_store = GlobalAssetLibrary(characters=[Character(id='char-1', name='Hero', description='hero')])
    pipeline._save_data()
    pipeline._save_series_data()
    pipeline._save_library_data()
    restored = bare_pipeline(db)
    assert restored.get_script('project-1').merged_video_url == 'video/existing.mp4'
    assert restored.series_store['series-1'].title == 'Series'
    assert restored.library_store.characters[0].id == 'char-1'
    del restored.scripts['project-1']
    restored._save_data()
    assert bare_pipeline(db).scripts == {}
    assert list(tmp_path.iterdir()) == []


def test_playground_template_restart_and_delete(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch('src.apps.playground.storage.repository_from_env', side_effect=lambda: MongoRepository(db)):
        store = PlaygroundStorage()
        template = PlaygroundTemplate(id='t1', name='Demo', prompt='test', created_at='2026-10-16', updated_at='2026-10-16')
        store.add_template(template)
        restored = PlaygroundStorage()
        assert restored.get_template('t1').prompt == 'test'
        template.prompt = 'updated'
        restored.update_template(template)
        assert PlaygroundStorage().get_template('t1').prompt == 'updated'
        assert restored.delete_template('t1')
        assert PlaygroundStorage().list_templates() == []
    assert list(tmp_path.iterdir()) == []
