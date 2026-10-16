"""Exercises S3Storage against a *real* MinIO server — not moto's mocked
AWS backend (see tests/test_s3_storage.py). This is the verification gap
app/services/storage.py's own module docstring calls out: moto proves API
correctness against AWS's documented semantics, but MinIO is known to be
lenient about some things AWS is strict about (region/LocationConstraint
being the specific example that bit this app before), so passing against
moto alone doesn't prove this code actually works against MinIO.

Skips the whole module if no MinIO server is reachable at
MINIO_TEST_ENDPOINT (default http://127.0.0.1:9000) rather than failing —
this is real infrastructure, not something CI should be expected to run.
To exercise this for real: brew install minio, then
`minio server /tmp/some-dir --address :9000` (or `docker compose up minio`
per infra/docker-compose.yml), then run `pytest tests/test_s3_storage_minio.py -v`.
"""

import os
import uuid

import boto3
import pytest

from app.core.config import Settings
from app.services.storage import S3Storage, StorageError

MINIO_ENDPOINT = os.environ.get("MINIO_TEST_ENDPOINT", "http://127.0.0.1:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_TEST_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_TEST_SECRET_KEY", "minioadmin")


def _minio_reachable() -> bool:
    try:
        import httpx

        resp = httpx.get(f"{MINIO_ENDPOINT}/minio/health/live", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _minio_reachable(), reason=f"No real MinIO server reachable at {MINIO_ENDPOINT}"
)


def _settings(region: str = "eu-west-2", bucket: str | None = None) -> Settings:
    return Settings(
        s3_bucket=bucket or f"datalume-test-{uuid.uuid4().hex[:12]}",
        s3_access_key=MINIO_ACCESS_KEY,
        s3_secret_key=MINIO_SECRET_KEY,
        s3_region=region,
        s3_endpoint_url=MINIO_ENDPOINT,
    )


def _cleanup_bucket(bucket: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="eu-west-2",
    )
    try:
        objects = client.list_objects_v2(Bucket=bucket).get("Contents", [])
        for obj in objects:
            client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)
    except Exception:
        pass  # best-effort cleanup — a leftover throwaway test bucket is harmless


def test_auto_creates_bucket_in_non_default_region() -> None:
    # The exact scenario that exposed the original bug against moto/AWS:
    # a fresh bucket in a region other than us-east-1. Confirms the fix
    # (conditionally setting CreateBucketConfiguration) also works against
    # real MinIO, not just moto.
    settings = _settings(region="eu-west-2")
    try:
        storage = S3Storage(settings)
        storage.write("a/b.txt", b"hello")
        assert storage.read("a/b.txt") == b"hello"
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_auto_creates_bucket_in_us_east_1() -> None:
    settings = _settings(region="us-east-1")
    try:
        storage = S3Storage(settings)
        storage.write("a/b.txt", b"hello")
        assert storage.read("a/b.txt") == b"hello"
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_does_not_recreate_an_existing_bucket() -> None:
    settings = _settings()
    try:
        first = S3Storage(settings)
        first.write("one.txt", b"first")
        second = S3Storage(settings)  # same bucket — must find it via head_bucket
        assert second.read("one.txt") == b"first"
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_write_read_roundtrip_preserves_bytes_exactly() -> None:
    settings = _settings()
    try:
        storage = S3Storage(settings)
        content = bytes(range(256)) * 10  # includes null bytes and non-UTF8 bytes
        storage.write("binary/data.bin", content)
        assert storage.read("binary/data.bin") == content
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_read_missing_key_raises_storage_error() -> None:
    settings = _settings()
    try:
        storage = S3Storage(settings)
        with pytest.raises(StorageError):
            storage.read("never/written.txt")
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_delete_removes_object() -> None:
    settings = _settings()
    try:
        storage = S3Storage(settings)
        storage.write("to-delete.txt", b"gone soon")
        storage.delete("to-delete.txt")
        with pytest.raises(StorageError):
            storage.read("to-delete.txt")
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_overwriting_a_key_replaces_its_content() -> None:
    settings = _settings()
    try:
        storage = S3Storage(settings)
        storage.write("versioned.txt", b"v1")
        storage.write("versioned.txt", b"v2")
        assert storage.read("versioned.txt") == b"v2"
    finally:
        _cleanup_bucket(settings.s3_bucket)


def test_minio_leniency_towards_the_original_bug_is_empirically_confirmed() -> None:
    """Settles the "MinIO is known to be lenient" claim this app's docs
    have repeated without ever actually testing it: calls create_bucket
    the *old, buggy* way (no CreateBucketConfiguration) directly against
    real MinIO, in a non-us-east-1 region — the exact shape that raised
    IllegalLocationConstraintException against real AWS S3 (and against
    moto, which reproduces that same error). If this succeeds, the
    leniency claim is empirically true for this MinIO version, not just
    a plausible guess."""
    bucket = f"datalume-leniency-test-{uuid.uuid4().hex[:12]}"
    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="eu-west-2",
    )
    try:
        # Deliberately the pre-fix call shape: Bucket only, no
        # CreateBucketConfiguration, even though region_name is eu-west-2.
        client.create_bucket(Bucket=bucket)
        client.head_bucket(Bucket=bucket)  # didn't raise -> bucket really exists
    finally:
        _cleanup_bucket(bucket)
