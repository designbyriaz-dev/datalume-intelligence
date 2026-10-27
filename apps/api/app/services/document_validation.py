"""Structural validation for uploaded property documents.

A deliberately separate module from app/services/upload_validation.py
rather than loosening it: that module's allow-list (.csv/.xlsx only) is
intentionally strict for dataset ingestion, and a document upload needs a
different, document-shaped allow-list (certificates, agreements, photos)
with its own magic-byte checks — mixing the two would weaken the dataset
path's guarantees for no real benefit.

Not a malware scanner — see app/services/malware_scanning.py's own
docstring for why that's a separate, optional layer; this module's job is
purely "does the content match its claimed type and stay under the size
cap", the same job upload_validation.py does for datasets.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".docx"}

_CONTENT_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_PDF_SIGNATURE = b"%PDF"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DOCX_SIGNATURE = b"PK\x03\x04"

MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class DocumentValidationError(Exception):
    pass


@dataclass
class ValidatedDocument:
    extension: str
    content_type: str
    content: bytes


def validate_document_upload(filename: str, content: bytes, max_size_bytes: int) -> ValidatedDocument:
    if "." not in filename:
        raise DocumentValidationError("File has no extension.")
    extension = "." + filename.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError(
            f"Unsupported file type '{extension}'. Supported types: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    if len(content) == 0:
        raise DocumentValidationError("File is empty.")

    if len(content) > max_size_bytes:
        raise DocumentValidationError(
            f"File is {len(content)} bytes, which exceeds the {max_size_bytes}-byte limit."
        )

    if extension == ".pdf":
        _validate_pdf(content)
    elif extension in (".jpg", ".jpeg"):
        _validate_jpeg(content)
    elif extension == ".png":
        _validate_png(content)
    elif extension == ".docx":
        _validate_docx(content)

    return ValidatedDocument(extension=extension, content_type=_CONTENT_TYPE_BY_EXTENSION[extension], content=content)


def _validate_pdf(content: bytes) -> None:
    if not content.startswith(_PDF_SIGNATURE):
        raise DocumentValidationError("File has a .pdf extension but is not a valid PDF.")


def _validate_jpeg(content: bytes) -> None:
    if not content.startswith(_JPEG_SIGNATURE):
        raise DocumentValidationError("File has a .jpg/.jpeg extension but is not a valid JPEG.")


def _validate_png(content: bytes) -> None:
    if not content.startswith(_PNG_SIGNATURE):
        raise DocumentValidationError("File has a .png extension but is not a valid PNG.")


def _validate_docx(content: bytes) -> None:
    if not content.startswith(_DOCX_SIGNATURE):
        raise DocumentValidationError(
            "File has a .docx extension but is not a valid Office Open XML archive."
        )

    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            total_uncompressed = sum(info.file_size for info in archive.infolist())
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentValidationError(
                    "File rejected: uncompressed content would exceed "
                    f"{MAX_DOCX_UNCOMPRESSED_BYTES} bytes (possible zip bomb)."
                )
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise DocumentValidationError("File is not a valid .docx archive.") from exc

    if "word/document.xml" not in names:
        raise DocumentValidationError("File does not look like a valid Word document.")

    if any(name.startswith("word/vbaProject") for name in names):
        raise DocumentValidationError(
            "Macro-enabled documents are not supported. Please save as a plain .docx file."
        )
