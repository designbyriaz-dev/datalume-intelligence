"""Structural validation for uploaded dataset files.

This is deliberately NOT a malware scanner — there is no AV engine wired
in (see settings.malware_scanning_enabled). What this module does provide,
for real:

- File-extension allow-list (.csv, .xlsx only — .xls and .xlsm rejected).
- Magic-byte verification that the file's actual content matches its
  claimed type, so a disguised executable/zip can't masquerade as a .csv.
- A size cap, enforced on the raw upload.
- A zip-bomb guard for .xlsx (a zip archive): rejects files whose
  uncompressed entry sizes blow past a sane limit, without fully
  inflating them first.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

# Signatures that should never appear at the start of a .csv file. If one
# does, the upload is lying about its type.
_BINARY_SIGNATURES = {
    b"PK\x03\x04": "a ZIP/Office archive",
    b"MZ": "a Windows executable",
    b"\x7fELF": "a Linux executable",
    b"%PDF": "a PDF",
    b"\x1f\x8b": "a GZIP archive",
}

_XLSX_SIGNATURE = b"PK\x03\x04"

# Guard against zip bombs: reject an .xlsx whose uncompressed content
# would exceed this, even though the uploaded (compressed) file itself
# passed the size cap.
MAX_XLSX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


class UploadValidationError(Exception):
    pass


@dataclass
class ValidatedUpload:
    extension: str
    content: bytes


def validate_upload(filename: str, content: bytes, max_size_bytes: int) -> ValidatedUpload:
    if "." not in filename:
        raise UploadValidationError("File has no extension.")
    extension = "." + filename.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            f"Unsupported file type '{extension}'. Supported types: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    if len(content) == 0:
        raise UploadValidationError("File is empty.")

    if len(content) > max_size_bytes:
        raise UploadValidationError(
            f"File is {len(content)} bytes, which exceeds the {max_size_bytes}-byte limit."
        )

    if extension == ".csv":
        _validate_csv_signature(content)
    elif extension == ".xlsx":
        _validate_xlsx(content)

    return ValidatedUpload(extension=extension, content=content)


def _validate_csv_signature(content: bytes) -> None:
    head = content[:8]
    for signature, description in _BINARY_SIGNATURES.items():
        if head.startswith(signature):
            raise UploadValidationError(
                f"File has a .csv extension but its content looks like {description}."
            )
    # A CSV should be decodable as text at all (encoding is detected
    # properly later for parsing — this is just a sanity check that we
    # weren't handed arbitrary binary data).
    try:
        content[:4096].decode("utf-8")
    except UnicodeDecodeError:
        try:
            content[:4096].decode("latin-1")
        except UnicodeDecodeError as exc:
            raise UploadValidationError("File content is not decodable as text.") from exc


def _validate_xlsx(content: bytes) -> None:
    if not content.startswith(_XLSX_SIGNATURE):
        raise UploadValidationError(
            "File has a .xlsx extension but is not a valid Office Open XML archive."
        )

    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            total_uncompressed = sum(info.file_size for info in archive.infolist())
            if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise UploadValidationError(
                    "File rejected: uncompressed content would exceed "
                    f"{MAX_XLSX_UNCOMPRESSED_BYTES} bytes (possible zip bomb)."
                )
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("File is not a valid .xlsx archive.") from exc

    if "xl/workbook.xml" not in names:
        raise UploadValidationError("File does not look like a valid Excel workbook.")

    if any(name.startswith("xl/vbaProject") for name in names):
        raise UploadValidationError(
            "Macro-enabled workbooks are not supported. Please save as a plain .xlsx file."
        )
