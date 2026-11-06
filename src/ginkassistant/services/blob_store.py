"""
Where big files live, so Gink isn't limited by one server's disk.

  * Object storage (S3-compatible: Cloudflare R2, Backblaze B2, AWS S3, Wasabi...) when these are set:
      GINK_S3_BUCKET, GINK_S3_KEY, GINK_S3_SECRET, and for non-AWS services GINK_S3_ENDPOINT
      (e.g. https://<account>.r2.cloudflarestorage.com), optional GINK_S3_REGION (default "auto").
    It grows with use: you pay for what's stored, not for space reserved up front.
  * Otherwise files on the server's disk, next to the database (GINK_BLOB_DIR to choose the folder).

Blobs are content-addressed (named by their SHA-256), so the same content is stored once however many
projects, copies and versions use it. The server's database keeps only a short marker.
"""
import hashlib
import os
import threading
from collections import OrderedDict


class LocalStore:
    kind = "disk"

    def __init__(self, root: str):
        self.root = root

    def _path(self, key: str) -> str:
        return os.path.join(self.root, key[:2], key[2:4], key)

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        if os.path.exists(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def get(self, key: str):
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except OSError:
            return None

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except OSError:
            pass

    def keys(self):
        for root, _dirs, files in os.walk(self.root):
            for name in files:
                if not name.endswith(".part"):
                    yield name


class S3Store:
    kind = "object storage"

    def __init__(self, bucket: str, key: str, secret: str, endpoint: str = "", region: str = "auto", prefix: str = "gink/"):
        import boto3                                  # in deploy/requirements-server.txt
        from botocore.config import Config
        self.bucket, self.prefix = bucket, prefix
        self.s3 = boto3.client("s3", aws_access_key_id=key, aws_secret_access_key=secret, region_name=region or "auto",
                               endpoint_url=endpoint or None,
                               config=Config(retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=10, read_timeout=60))

    def put(self, key: str, data: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data)

    def get(self, key: str):
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self.prefix + key)["Body"].read()
        except Exception:
            return None

    def delete(self, key: str) -> None:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=self.prefix + key)
        except Exception:
            pass

    def keys(self):
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents") or []:
                yield obj["Key"][len(self.prefix):]


_store = {"value": None, "problem": ""}
_cache = OrderedDict()
_cache_lock = threading.Lock()
CACHE_BYTES = 64_000_000


def store(default_root: str = ""):
    """The configured store (created once). A broken object-storage setup falls back to disk, with a reason."""
    if _store["value"] is None:
        env = os.environ.get
        if env("GINK_S3_BUCKET") and env("GINK_S3_KEY") and env("GINK_S3_SECRET"):
            try:
                _store["value"] = S3Store(env("GINK_S3_BUCKET"), env("GINK_S3_KEY"), env("GINK_S3_SECRET"),
                                          env("GINK_S3_ENDPOINT", ""), env("GINK_S3_REGION", "auto"))
            except Exception as exc:
                _store["problem"] = f"Object storage isn't working ({type(exc).__name__}); using the server's disk."
        if _store["value"] is None:
            _store["value"] = LocalStore(env("GINK_BLOB_DIR") or default_root or "blobs")
    return _store["value"]


def reset() -> None:
    _store.update(value=None, problem="")
    with _cache_lock:
        _cache.clear()


def key_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(data: bytes, default_root: str = "") -> str:
    key = key_for(data)
    store(default_root).put(key, data)
    _remember(key, data)
    return key


def get(key: str, default_root: str = ""):
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    data = store(default_root).get(key)
    if data is not None:
        _remember(key, data)
    return data


def _remember(key: str, data: bytes) -> None:
    with _cache_lock:
        _cache[key] = data
        _cache.move_to_end(key)
        total = sum(len(v) for v in _cache.values())
        while total > CACHE_BYTES and len(_cache) > 1:
            _k, v = _cache.popitem(last=False)
            total -= len(v)


def collect_garbage(in_use: set, default_root: str = "") -> int:
    """Delete blobs nothing refers to any more (files, copies and versions all deleted)."""
    s, removed = store(default_root), 0
    for key in list(s.keys()):
        if key not in in_use:
            s.delete(key)
            removed += 1
            with _cache_lock:
                _cache.pop(key, None)
    return removed
