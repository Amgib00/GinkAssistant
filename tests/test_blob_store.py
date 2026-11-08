"""Big files leave the database: content-addressed blobs on disk or in object storage (S3-compatible),
with versions and copies costing almost nothing, and unused blobs cleaned up."""
import base64
import os
import sys
import types
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from ginkassistant.services import blob_store


@pytest.fixture(autouse=True)
def fresh_store():
    blob_store.reset()
    yield
    blob_store.reset()


def raw(b, pid):
    return dict(b._genie_db(lambda con: con.execute("SELECT path, content FROM genie_files WHERE project_id=?", (pid,)).fetchall()))


def test_big_files_live_in_the_blob_store(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "big"}).json()["project"]["id"]
    big = "x = 1\n" * 5000                                                       # 30 KB
    b._genie_write(pid, "big.py", big)
    b._genie_write(pid, "small.py", "print(1)")
    stored = raw(b, pid)
    assert stored["big.py"].startswith(b.GENIE_BLOB) and stored["small.py"] == "print(1)"
    assert b._genie_files(pid)["big.py"] == big                                 # read back whole
    assert {f["path"]: f["size"] for f in b._genie_summary(pid)}["big.py"] == len(big)
    assert "big.py:1: x = 1" in b._genie_tool(pid, "search_files", {"text": "x = 1"}, [])
    key = stored["big.py"][len(b.GENIE_BLOB):].split(":")[0]
    assert os.path.exists(os.path.join(b._blob_root(), key[:2], key[2:4], key))  # on disk, next to the database


def test_versions_copies_and_undo_with_blobs(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "v"}).json()["project"]["id"]
    one, two = "a = 1\n" * 3000, "a = 2\n" * 3000
    b._genie_write(pid, "app.py", one)
    cp = b._genie_checkpoint(pid, "before")
    snap = b._genie_db(lambda con: con.execute("SELECT files FROM genie_snapshots WHERE id=?", (cp,)).fetchone()[0])
    assert len(snap) < 300                                                       # a marker, not 18 KB
    b._genie_write(pid, "app.py", two)
    r = c.post(f"/genie/projects/{pid}/undo", headers=h, json={"checkpoint": cp})
    assert r.status_code == 200 and b._genie_files(pid)["app.py"] == one
    dup = c.post(f"/genie/projects/{pid}/duplicate", headers=h).json()["project"]["id"]
    assert b._genie_files(dup)["app.py"] == one and raw(b, dup)["app.py"] == raw(b, pid)["app.py"]   # shared blob


def test_pictures_too(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "p"}).json()["project"]["id"]
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    b._genie_write(pid, "logo.png", "", picture=png + b"\0" * 9000)
    assert raw(b, pid)["logo.png"].endswith(":p")
    entry = b._genie_summary(pid)[0]
    assert entry["picture"] is True and entry["size"] == len(png) + 9000


def test_unused_blobs_are_cleaned_up(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "g"}).json()["project"]["id"]
    b._genie_write(pid, "keep.py", "k = 1\n" * 3000)
    b._genie_write(pid, "gone.py", "g = 1\n" * 3000)
    b._genie_checkpoint(pid, "v1")
    b._genie_delete_file(pid, "gone.py")
    assert b._blob_gc() == 0                                                     # still in a version
    b._genie_db(lambda con: con.execute("DELETE FROM genie_snapshots WHERE project_id=?", (pid,)))
    assert b._blob_gc() == 1 and b._genie_files(pid)["keep.py"].startswith("k = 1")


def test_object_storage_when_configured(monkeypatch):
    objects = {}

    class Body:
        def __init__(self, d): self.d = d
        def read(self): return self.d

    class Client:
        def put_object(self, Bucket, Key, Body): objects[(Bucket, Key)] = Body
        def get_object(self, Bucket, Key):
            if (Bucket, Key) not in objects:
                raise KeyError(Key)
            return {"Body": Body(objects[(Bucket, Key)])}
        def delete_object(self, Bucket, Key): objects.pop((Bucket, Key), None)
        def get_paginator(self, name):
            return types.SimpleNamespace(paginate=lambda Bucket, Prefix: [{"Contents": [{"Key": k} for (bk, k) in objects
                                                                                       if bk == Bucket and k.startswith(Prefix)]}])
    seen = {}

    def client(service, **kw):
        seen.update(kw, service=service)
        return Client()
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "botocore", types.ModuleType("botocore"))
    monkeypatch.setitem(sys.modules, "botocore.config", types.SimpleNamespace(Config=lambda **kw: kw))
    for k, v in {"GINK_S3_BUCKET": "gink-files", "GINK_S3_KEY": "AK", "GINK_S3_SECRET": "SK",
                 "GINK_S3_ENDPOINT": "https://acc.r2.cloudflarestorage.com"}.items():
        monkeypatch.setenv(k, v)
    key = blob_store.put(b"hello world")
    assert blob_store.store().kind == "object storage" and ("gink-files", "gink/" + key) in objects
    assert seen["endpoint_url"] == "https://acc.r2.cloudflarestorage.com" and seen["service"] == "s3"
    blob_store._cache.clear()
    assert blob_store.get(key) == b"hello world"
    assert blob_store.collect_garbage(set()) == 1 and objects == {}


def test_broken_object_storage_falls_back_to_disk(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "boto3", None)                              # not installed
    for k in ("GINK_S3_BUCKET", "GINK_S3_KEY", "GINK_S3_SECRET"):
        monkeypatch.setenv(k, "x")
    s = blob_store.store(str(tmp_path))
    assert s.kind == "disk" and "isn't working" in blob_store._store["problem"]


def test_files_from_the_disk_move_to_object_storage_when_read(monkeypatch, tmp_path):
    """Switching object storage on later must not lose the big files already kept on the server's disk."""
    disk = blob_store.LocalStore(str(tmp_path))
    key = blob_store.key_for(b"an old big file")
    disk.put(key, b"an old big file")
    objects = {}

    class Client:
        def put_object(self, Bucket, Key, Body): objects[Key] = Body
        def get_object(self, Bucket, Key):
            if Key not in objects:
                raise KeyError(Key)
            return {"Body": types.SimpleNamespace(read=lambda: objects[Key])}
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda service, **kw: Client()))
    monkeypatch.setitem(sys.modules, "botocore", types.ModuleType("botocore"))
    monkeypatch.setitem(sys.modules, "botocore.config", types.SimpleNamespace(Config=lambda **kw: kw))
    for k, v in {"GINK_S3_BUCKET": "b", "GINK_S3_KEY": "k", "GINK_S3_SECRET": "s"}.items():
        monkeypatch.setenv(k, v)
    assert blob_store.get(key, str(tmp_path)) == b"an old big file"
    assert objects["gink/" + key] == b"an old big file"                          # now in object storage too
