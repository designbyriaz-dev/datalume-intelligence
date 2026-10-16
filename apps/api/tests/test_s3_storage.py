"""Exercises S3Storage's real boto3 client code against moto's mocked S3
backend — a fake AWS endpoint that implements the actual S3 API/XML
semantics (request signing, bucket/object operations, error shapes), not
a hand-rolled stub of this app's own code. See app/services/storage.py's
module docstring for exactly what this does and doesn't prove.

This test file is what caught a real bug: S3Storage's bucket
auto-creation called create_bucket(Bucket=...) with no
CreateBucketConfiguration, which real AWS S3 rejects for any region
other than us-east-1 — including eu-west-2, this app's own configured
default region."""

from moto import mock_aws

from app.core.config import Settings
from app.services.storage import S3Storage, StorageError


def _settings(region: str = "eu-west-2", bucket: str = "datalume-test-bucket") -> Settings:
    return Settings(
        s3_bucket=bucket,
        s3_access_key="test-access-key",
        s3_secret_key="test-secret-key",
        s3_region=region,
        s3_endpoint_url=None,
    )


@mock_aws
def test_auto_creates_bucket_in_non_default_region() -> None:
    # This is the exact scenario that exposed the bug: a fresh bucket,
    # in a region other than AWS's special-cased us-east-1 default. Prior
    # to the fix, this raised IllegalLocationConstraintException instead
    # of succeeding.
    storage = S3Storage(_settings(region="eu-west-2"))
    storage.write("a/b.txt", b"hello")
    assert storage.read("a/b.txt") == b"hello"


@mock_aws
def test_auto_creates_bucket_in_us_east_1() -> None:
    # us-east-1 is the one region where passing a LocationConstraint at
    # all is rejected — the fix must omit it specifically for this case.
    storage = S3Storage(_settings(region="us-east-1"))
    storage.write("a/b.txt", b"hello")
    assert storage.read("a/b.txt") == b"hello"


@mock_aws
def test_does_not_recreate_an_existing_bucket() -> None:
    first = S3Storage(_settings())
    first.write("one.txt", b"first")
    # A second instance against the same bucket must find it via
    # head_bucket and not attempt (and fail on) create_bucket again.
    second = S3Storage(_settings())
    assert second.read("one.txt") == b"first"


@mock_aws
def test_write_read_roundtrip_preserves_bytes_exactly() -> None:
    storage = S3Storage(_settings())
    content = bytes(range(256)) * 10  # includes null bytes and non-UTF8 bytes
    storage.write("binary/data.bin", content)
    assert storage.read("binary/data.bin") == content


@mock_aws
def test_read_missing_key_raises_storage_error() -> None:
    storage = S3Storage(_settings())
    try:
        storage.read("never/written.txt")
        assert False, "expected StorageError"
    except StorageError:
        pass


@mock_aws
def test_delete_removes_object() -> None:
    storage = S3Storage(_settings())
    storage.write("to-delete.txt", b"gone soon")
    storage.delete("to-delete.txt")
    try:
        storage.read("to-delete.txt")
        assert False, "expected StorageError after delete"
    except StorageError:
        pass


@mock_aws
def test_overwriting_a_key_replaces_its_content() -> None:
    storage = S3Storage(_settings())
    storage.write("versioned.txt", b"v1")
    storage.write("versioned.txt", b"v2")
    assert storage.read("versioned.txt") == b"v2"
