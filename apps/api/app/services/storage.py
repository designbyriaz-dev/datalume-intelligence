"""Object storage abstraction for uploaded datasets.

Two backends:

- LocalFilesystemStorage: writes under settings.local_storage_dir. Used
  automatically in development/tests, with zero external setup — same
  philosophy as the SQLite fallback for DATABASE_URL.
- S3Storage: a real boto3-backed implementation that works against AWS S3
  or any S3-compatible endpoint (MinIO, Cloudflare R2, ...) via
  S3_ENDPOINT_URL. Used automatically once S3_ACCESS_KEY is set.

S3Storage verification status: tests/test_s3_storage.py exercises the
real boto3 client code path (bucket-missing -> auto-create, write, read,
read-of-missing-key, delete, delete-then-read) against moto's mocked S3
backend — a fake AWS endpoint that implements the actual S3 API/XML
semantics, not a hand-rolled stub. That's real: it caught a genuine bug
(see the comment on create_bucket below) that unit tests mocking boto3
directly would never have caught, because the bug was in *which
arguments* real S3 requires, not in this code's own logic.

Also verified against a real (locally-run) MinIO server —
tests/test_s3_storage_minio.py — mirroring every case above plus one
that specifically settles the "MinIO is known to be lenient" claim
empirically (calling create_bucket the pre-fix, no-LocationConstraint
way directly, against a non-us-east-1 region, and confirming it
succeeds against real MinIO rather than just assuming it would). That
test file skips itself when no MinIO server is reachable, so it never
blocks CI — run it for real with `brew install minio && minio server
/tmp/some-dir --address :9000` (or `docker compose up minio`), then
`pytest tests/test_s3_storage_minio.py`.

Still not proven: a real AWS S3 or Cloudflare R2 bucket — MinIO's
leniency is now confirmed, not just assumed, but that's a reason for
more caution in production against real AWS, not less, since AWS is
the strict one. See docs/DEPLOYMENT.md.
"""

from __future__ import annotations

import abc
from pathlib import Path

from app.core.config import Settings, get_settings


class StorageError(Exception):
    pass


class ObjectStorage(abc.ABC):
    @abc.abstractmethod
    def write(self, key: str, content: bytes) -> None: ...

    @abc.abstractmethod
    def read(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...


class LocalFilesystemStorage(ObjectStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Keys are generated server-side (see datasets.py) and never come
        # directly from user input, but normalize defensively anyway so a
        # future caller can't escape base_dir via "..".
        path = (self.base_dir / key).resolve()
        if not str(path).startswith(str(self.base_dir.resolve())):
            raise StorageError(f"Invalid storage key: {key}")
        return path

    def write(self, key: str, content: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise StorageError(f"Object not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)


class S3Storage(ObjectStorage):
    def __init__(self, settings: Settings):
        import boto3

        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            # Real AWS S3 rejects create_bucket for any region other than
            # us-east-1 unless CreateBucketConfiguration.LocationConstraint
            # is set to that same region (and, confusingly, rejects it if
            # you DO set it for us-east-1 — that region is the one
            # "unspecified" default). Caught by testing this against a
            # mocked-but-API-accurate S3 backend (moto) in the app's own
            # default region (eu-west-2, not us-east-1) — without this,
            # first-run bucket auto-creation would fail against real AWS
            # in any non-default region. MinIO is generally lenient here,
            # which is exactly why this went unnoticed against it.
            create_kwargs: dict = {"Bucket": self.bucket}
            if settings.s3_region and settings.s3_region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
            self._client.create_bucket(**create_kwargs)

    def write(self, key: str, content: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=content)

    def read(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"Object not found: {key}") from exc
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


_storage_instance: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    settings = get_settings()

    if settings.s3_access_key:
        _storage_instance = S3Storage(settings)
    elif settings.environment == "production":
        raise StorageError(
            "No S3 credentials configured and environment=production — "
            "refusing to fall back to local disk storage. Set S3_ACCESS_KEY "
            "etc. (see .env.example)."
        )
    else:
        _storage_instance = LocalFilesystemStorage(settings.local_storage_dir)

    return _storage_instance


def reset_storage_for_tests() -> None:
    global _storage_instance
    _storage_instance = None
