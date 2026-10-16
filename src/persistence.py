"""MongoDB metadata storage; media and editable document files stay local.

Each pipeline owns a snapshot. Only changed documents are saved, using revision
checks to prevent a stale process from overwriting another process's changes.
This is not a replacement for the future worker/job repository: the current
pipeline must still run as one API process because its live models are cached.
"""

from copy import deepcopy
from functools import lru_cache
import os
import threading

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError


class StorageError(RuntimeError):
    """Safe public error, without connection details or credentials."""


class StorageConflict(StorageError):
    pass


class MongoRepository:
    def __init__(self, database):
        self.database = database
        self._snapshots = {}
        self._lock = threading.RLock()

    def load(self, collection):
        with self._lock:
            try:
                docs = list(self.database[collection].find({}))
            except PyMongoError:
                raise StorageError("MongoDB read failed; no JSON fallback was used") from None
            snapshot = {d['_id']: (d['revision'], d['data']) for d in docs}
            self._snapshots[collection] = deepcopy(snapshot)
            return {key: deepcopy(value[1]) for key, value in snapshot.items()}

    def save(self, collection, records):
        """Persist only local changes. Never delete unknown/externally added IDs.

        A batch is NOT a transaction: earlier documents may have committed when a
        later write fails. Their snapshots advance immediately, making retries
        safe. A conflict requires reloading/restarting the owning pipeline.
        """
        with self._lock:
            if collection not in self._snapshots:
                raise StorageError("Collection must be loaded before saving")
            baseline = self._snapshots[collection]
            target = self.database[collection]
            try:
                for key, data in records.items():
                    previous = baseline.get(key)
                    if previous is not None and previous[1] == data:
                        continue
                    if previous is None:
                        try:
                            target.insert_one({'_id': key, 'revision': 1, 'data': data})
                        except DuplicateKeyError:
                            raise StorageConflict("Metadata changed in another process; restart the backend before retrying") from None
                        revision = 1
                    else:
                        revision = previous[0] + 1
                        result = target.replace_one(
                            {'_id': key, 'revision': previous[0]},
                            {'_id': key, 'revision': revision, 'data': data},
                        )
                        if result.matched_count != 1:
                            raise StorageConflict("Metadata changed in another process; restart the backend before retrying")
                    baseline[key] = (revision, deepcopy(data))
                for key in list(baseline.keys() - records.keys()):
                    result = target.delete_one({'_id': key, 'revision': baseline[key][0]})
                    if result.deleted_count != 1:
                        raise StorageConflict("Metadata changed before deletion; restart the backend before retrying")
                    del baseline[key]
            except PyMongoError:
                raise StorageError("MongoDB write failed; changes were not written to JSON") from None


@lru_cache(maxsize=4)
def _connect(uri, name):
    client = None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                             socketTimeoutMS=15000, appname='lumenx', tz_aware=True)
        client[name].command('ping')
    except (PyMongoError, ValueError):
        if client is not None:
            client.close()
        raise StorageError("Cannot connect/authenticate to MongoDB; check MONGODB_URI and MONGODB_DATABASE") from None
    return client[name]


def mongo_database():
    uri = os.getenv('MONGODB_URI', '').strip()
    name = os.getenv('MONGODB_DATABASE', 'lumenxdb').strip()
    if not uri or not name:
        raise StorageError("MONGODB_URI and MONGODB_DATABASE are required")
    return _connect(uri, name)


def repository_from_env():
    backend = os.getenv('LUMENX_STORAGE_BACKEND', 'json').strip().lower()
    if backend == 'json':
        return None
    if backend != 'mongodb':
        raise StorageError("LUMENX_STORAGE_BACKEND must be mongodb or json")
    database = mongo_database()
    # A successful migration is explicit. An uninitialized database must never
    # silently show an empty project list while old JSON data exists.
    try:
        initialized = database.storage_metadata.find_one({'_id': 'json_migration_v1'})
    except PyMongoError:
        raise StorageError("Cannot read MongoDB migration metadata") from None
    if not initialized:
        raise StorageError("MongoDB is not initialized; run scripts/migrate_json_to_mongodb.py --apply first")
    return MongoRepository(database)
