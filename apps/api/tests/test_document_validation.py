import io
import zipfile

import pytest

from app.services.document_validation import DocumentValidationError, validate_document_upload

MAX_SIZE = 10 * 1024 * 1024


def _minimal_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


def test_accepts_a_real_pdf() -> None:
    result = validate_document_upload("cert.pdf", b"%PDF-1.4\n...", MAX_SIZE)
    assert result.extension == ".pdf"
    assert result.content_type == "application/pdf"


def test_accepts_a_real_jpeg() -> None:
    result = validate_document_upload("photo.jpg", b"\xff\xd8\xff\xe0rest-of-jpeg", MAX_SIZE)
    assert result.extension == ".jpg"
    assert result.content_type == "image/jpeg"


def test_accepts_a_real_png() -> None:
    result = validate_document_upload("photo.png", b"\x89PNG\r\n\x1a\nrest-of-png", MAX_SIZE)
    assert result.content_type == "image/png"


def test_accepts_a_real_docx() -> None:
    result = validate_document_upload("agreement.docx", _minimal_docx_bytes(), MAX_SIZE)
    assert result.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(DocumentValidationError, match="Unsupported file type"):
        validate_document_upload("malware.exe", b"MZ\x90\x00", MAX_SIZE)


def test_rejects_empty_file() -> None:
    with pytest.raises(DocumentValidationError, match="empty"):
        validate_document_upload("cert.pdf", b"", MAX_SIZE)


def test_rejects_file_over_size_cap() -> None:
    with pytest.raises(DocumentValidationError, match="exceeds"):
        validate_document_upload("cert.pdf", b"%PDF-1.4" + b"0" * 100, 10)


def test_rejects_executable_disguised_as_pdf() -> None:
    with pytest.raises(DocumentValidationError, match="not a valid PDF"):
        validate_document_upload("cert.pdf", b"MZ\x90\x00\x03\x00\x00\x00", MAX_SIZE)


def test_rejects_disguised_jpeg() -> None:
    with pytest.raises(DocumentValidationError, match="not a valid JPEG"):
        validate_document_upload("photo.jpg", b"not-a-real-jpeg", MAX_SIZE)


def test_rejects_disguised_docx() -> None:
    with pytest.raises(DocumentValidationError, match="not a valid Office Open XML"):
        validate_document_upload("agreement.docx", b"not-a-zip-at-all", MAX_SIZE)


def test_rejects_zip_without_word_document_xml() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("something-else.txt", "not a word document")
    with pytest.raises(DocumentValidationError, match="not look like a valid Word document"):
        validate_document_upload("agreement.docx", buffer.getvalue(), MAX_SIZE)


def test_rejects_macro_enabled_docx() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/vbaProject.bin", b"macro-payload")
    with pytest.raises(DocumentValidationError, match="Macro-enabled"):
        validate_document_upload("agreement.docx", buffer.getvalue(), MAX_SIZE)
