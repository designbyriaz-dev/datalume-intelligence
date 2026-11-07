"""Exercises S3Storage against a *real* AWS S3 bucket — the one gap left
after tests/test_s3_storage_r2.py verified the same code path against a
real Cloudflare R2 bucket. R2 and AWS S3 share the exact same boto3
client code in app/services/storage.py, but AWS is the strict one the
module's own docstring originally flagged ("that's a reason for more
caution in production against real AWS, not less, since AWS is the
strict one") — this proves it for real rather than leaving that as an
assumption.

Unlike the MinIO test, this does NOT exercise bucket auto-creation: the
IAM user used here is deliberately scoped (least privilege) to
GetObject/PutObject/DeleteObject on one pre-existing bucket only, so it
cannot create or delete buckets. That scoping is itself the point —
this proves the app's actual production credential shape (object-level
access to a bucket provisioned ahead of time) works end to end, not a
broader admin-level shape the real deployment won't use.

Unlike the R2 test, no S3_ENDPOINT_URL is set here — boto3's default AWS
endpoint construction is exercised directly, since that's one more
thing R2/MinIO need that real AWS doesn't.

Skips the whole module unless real AWS credentials are supplied via
AWS_TEST_* env vars — never hardcoded here, since these are real
secrets tied to a real AWS account. To run this for real:

    export AWS_TEST_ACCESS_KEY=<access key id>
    export AWS_TEST_SECRET_KEY=<secret access key>
    export AWS_TEST_REGION=<the bucket's real region>
    export AWS_TEST_BUCKET=<your bucket name>
    pytest tests/test_s3_storage_aws.py -v

Every test writes under a unique uuid-prefixed key and deletes it again
in a finally block, so this is safe to run against the real bucket
without leaving litter or touching any other key.
"""

import os
import uuid

import pytest

from app.core.config import Settings
from app.services.storage import S3Storage, StorageError

AWS_ACCESS_KEY = os.environ.get("AWS_TEST_ACCESS_KEY")
AWS_SECRET_KEY = os.environ.get("AWS_TEST_SECRET_KEY")
AWS_REGION = os.environ.get("AWS_TEST_REGION")
AWS_BUCKET = os.environ.get("AWS_TEST_BUCKET")

pytestmark = pytest.mark.skipif(
    not (AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION and AWS_BUCKET),
    reason="No real AWS credentials supplied via AWS_TEST_* env vars",
)


def _storage() -> S3Storage:
    settings = Settings(
        s3_bucket=AWS_BUCKET,
        s3_access_key=AWS_ACCESS_KEY,
        s3_secret_key=AWS_SECRET_KEY,
        s3_region=AWS_REGION,
        s3_endpoint_url=None,  # real AWS: boto3's default endpoint construction, unlike R2/MinIO
    )
    return S3Storage(settings)


def _test_key(name: str) -> str:
    # Uuid-prefixed so a real run against a real bucket can never collide
    # with, or be mistaken for, an actual uploaded dataset.
    return f"_aws_verification/{uuid.uuid4().hex}/{name}"


def test_connects_to_the_real_bucket_without_trying_to_recreate_it() -> None:
    # The IAM user has no CreateBucket/ListAllMyBuckets permission — this
    # proves __init__'s head_bucket path finds the pre-existing bucket and
    # never falls through to create_bucket, which would fail outright
    # against this user's permissions if it did.
    storage = _storage()
    key = _test_key("connect.txt")
    try:
        storage.write(key, b"hello from a real AWS S3 bucket")
        assert storage.read(key) == b"hello from a real AWS S3 bucket"
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
