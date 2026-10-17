"""Exercises S3Storage against a *real* Cloudflare R2 bucket — the one gap
storage.py's own module docstring calls out as "still not proven": MinIO's
leniency is now confirmed (tests/test_s3_storage_minio.py), but that's a
reason for caution against real cloud storage, not a substitute for
testing it.

Unlike the MinIO test, this does NOT exercise bucket auto-creation: the
R2 Account API Token used here is deliberately scoped (least privilege)
to "Object Read & Write" on one pre-existing bucket only, so it cannot
create or delete buckets. That scoping is itself the point — this proves
the app's actual production credential shape (object-level access to a
bucket provisioned ahead of time) works end to end, not a broader
admin-level shape the real deployment won't use.

Skips the whole module unless real R2 credentials are supplied via
R2_TEST_* env vars — never hardcoded here, since (unlike MinIO's public
default admin/admin) these are real secrets tied to a real Cloudflare
account. To run this for real:

    export R2_TEST_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
    export R2_TEST_ACCESS_KEY=<access key id>
    export R2_TEST_SECRET_KEY=<secret access key>
    export R2_TEST_BUCKET=datalume-uploads  # optional, this is the default
    pytest tests/test_s3_storage_r2.py -v

Every test writes under a unique uuid-prefixed key and deletes it again
in a finally block, so this is safe to run against the real production
bucket without leaving litter or touching any other key.
"""

import os
import uuid

import pytest

from app.core.config import Settings
from app.services.storage import S3Storage, StorageError

R2_ENDPOINT = os.environ.get("R2_TEST_ENDPOINT")
R2_ACCESS_KEY = os.environ.get("R2_TEST_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_TEST_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_TEST_BUCKET", "datalume-uploads")

pytestmark = pytest.mark.skipif(
    not (R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY),
    reason="No real R2 credentials supplied via R2_TEST_* env vars",
)


def _storage() -> S3Storage:
    settings = Settings(
        s3_bucket=R2_BUCKET,
        s3_access_key=R2_ACCESS_KEY,
        s3_secret_key=R2_SECRET_KEY,
        s3_region="auto",  # R2's required convention — it has no real regions
        s3_endpoint_url=R2_ENDPOINT,
    )
    return S3Storage(settings)


def _test_key(name: str) -> str:
    # Uuid-prefixed so a real run against the real production bucket can
    # never collide with, or be mistaken for, an actual uploaded dataset.
    return f"_r2_verification/{uuid.uuid4().hex}/{name}"


def test_connects_to_the_real_bucket_without_trying_to_recreate_it() -> None:
    # The access token is scoped to this one bucket only (no bucket admin
    # permissions) — this proves __init__'s head_bucket path finds the
    # pre-existing bucket and never falls through to create_bucket, which
    # would fail outright against this token's permissions if it did.
    storage = _storage()
    key = _test_key("connect.txt")
    try:
        storage.write(key, b"hello from a real R2 bucket")
        assert storage.read(key) == b"hello from a real R2 bucket"
    finally:
        storage.delete(key)


def test_write_read_roundtrip_preserves_bytes_exactly() -> None:
    storage = _storage()
    key = _test_key("binary.bin")
    content = bytes(range(256)) * 10  # includes null bytes and non-UTF8 bytes
    try:
        storage.write(key, content)
        assert storage.read(key) == content
    finally:
        storage.delete(key)


def test_read_missing_key_raises_storage_error() -> None:
    storage = _storage()
    key = _test_key("never-written.txt")
    with pytest.raises(StorageError):
        storage.read(key)


def test_delete_removes_object() -> None:
    storage = _storage()
    key = _test_key("to-delete.txt")
    storage.write(key, b"gone soon")
    storage.delete(key)
    with pytest.raises(StorageError):
        storage.read(key)


def test_overwriting_a_key_replaces_its_content() -> None:
    storage = _storage()
    key = _test_key("versioned.txt")
    try:
        storage.write(key, b"v1")
        storage.write(key, b"v2")
        assert storage.read(key) == b"v2"
    finally:
        storage.delete(key)
