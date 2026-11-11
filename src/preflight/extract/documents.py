"""Bounded, in-memory ingestion; uploaded names never become filesystem paths."""

import hashlib
import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage, MIMEPart
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Literal, cast

import pymupdf

from preflight.context import EmailData

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 200_000
MAX_PAGES = 100
MAX_ATTACHMENTS = 10
type ErrorCode = Literal[
    "file_too_large",
    "mime_mismatch",
    "unsupported_type",
    "invalid_document",
    "ocr_unavailable",
    "too_many_attachments",
    "document_limit",
]


class IngestionError(ValueError):
    """A typed, non-sensitive ingestion failure suitable for a REVIEW report."""

    def __init__(self, code: ErrorCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True)
class Upload:
    """Raw caller-supplied bytes and optional declared media type."""

    name: str
    data: bytes
    declared_mime: str | None = None


@dataclass(frozen=True)
class Document:
    """Sniffed input, text pages and optional image or safely retained attachments."""

    mime: str
    text: str
    pages: tuple[str, ...]
    images: tuple[bytes, ...]
    content_hash: str
    email: EmailData | None = None
    attachments: tuple[Upload, ...] = ()


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def sniff_mime(data: bytes) -> str:
    """Identify supported signatures; email has a bounded RFC-header heuristic."""
    if len(data) > MAX_BYTES:
        raise IngestionError("file_too_large", "Upload exceeds 10 MB")
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    header = re.split(rb"\r?\n\r?\n", data[:8192], maxsplit=1)
    if (
        len(header) == 2
        and re.search(rb"(?im)^from:[^\r\n]+", header[0])
        and re.search(rb"(?im)^(?:to|subject|date|mime-version):", header[0])
    ):
        return "message/rfc822"
    raise IngestionError("unsupported_type", "Unsupported or unrecognized file signature")


def _verify_type(upload: Upload) -> str:
    mime = sniff_mime(upload.data)
    expected = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".eml": "message/rfc822",
    }.get(PurePosixPath(upload.name).suffix.lower())
    if expected is not None and expected != mime:
        raise IngestionError(
            "mime_mismatch", "Filename extension disagrees with file signature"
        )
    if expected is None:
        raise IngestionError("mime_mismatch", "Unsupported filename extension")
    if upload.declared_mime not in (None, "application/octet-stream", mime):
        raise IngestionError("mime_mismatch", "Declared MIME disagrees with file signature")
    return mime


def _open_document(data: bytes, filetype: str) -> pymupdf.Document:
    # PyMuPDF exposes its constructor without parameter annotations.
    return pymupdf.open(stream=data, filetype=filetype)  # type: ignore[no-untyped-call]


def _pdf(data: bytes) -> tuple[str, ...]:
    try:
        with _open_document(data, "pdf") as pdf:
            if pdf.needs_pass:
                raise IngestionError("invalid_document", "Encrypted PDFs are unsupported")
            if not 1 <= pdf.page_count <= MAX_PAGES:
                raise IngestionError("document_limit", "PDF page limit exceeded")
            pages: list[str] = []
            total = 0
            for page in pdf:
                text = cast(str, page.get_text())
                total += len(text)
                if total > MAX_TEXT:
                    raise IngestionError("document_limit", "PDF text limit exceeded")
                pages.append(text)
    except IngestionError:
        raise
    except (ValueError, RuntimeError, pymupdf.mupdf.FzErrorBase) as error:
        raise IngestionError("invalid_document", "Unreadable PDF") from error
    if not any(page.strip() for page in pages):
        raise IngestionError("ocr_unavailable", "PDF has no extractable text layer")
    # Mixed scanned/text PDFs cannot silently pass on just the extractable pages.
    if any(not page.strip() for page in pages):
        raise IngestionError("ocr_unavailable", "PDF includes a page without a text layer")
    return tuple(pages)


def _image(data: bytes, mime: str) -> None:
    try:
        with _open_document(data, mime.split("/")[1]) as image:
            page = image[0]
            if int(page.rect.width) * int(page.rect.height) > 40_000_000:
                raise IngestionError("document_limit", "Image dimensions exceed limit")
    except IngestionError:
        raise
    except (ValueError, RuntimeError, pymupdf.mupdf.FzErrorBase) as error:
        raise IngestionError("invalid_document", "Unreadable image") from error


def _address(message: EmailMessage, header: str, *, required: bool) -> tuple[str, str]:
    headers = message.get_all(header, [])
    addresses = getaddresses([str(value) for value in headers])
    if not addresses and not required:
        return "", ""
    if len(addresses) != 1 or "@" not in addresses[0][1] or len(headers) != 1:
        raise IngestionError("invalid_document", f"Email requires one valid {header} address")
    return addresses[0]


def _email(data: bytes) -> tuple[EmailData, tuple[Upload, ...]]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except (ValueError, RecursionError) as error:
        raise IngestionError("invalid_document", "Malformed email") from error
    if not isinstance(message, EmailMessage) or message.defects:
        raise IngestionError("invalid_document", "Malformed email structure")
    display, sender = _address(message, "From", required=True)
    _, reply = _address(message, "Reply-To", required=False)
    bodies: list[str] = []
    html_bodies: list[str] = []
    attachments: list[Upload] = []
    queue: list[tuple[MIMEPart, int]] = [(message, 0)]
    parts = 0
    attachment_bytes = 0
    while queue:
        part, depth = queue.pop()
        parts += 1
        if parts > 100 or depth > 20:
            raise IngestionError("document_limit", "Email MIME complexity limit exceeded")
        if part.defects:
            raise IngestionError("invalid_document", "Malformed email part")
        if part.get_content_type() == "message/rfc822":
            raise IngestionError("unsupported_type", "Nested email attachments are unsupported")
        if part.is_multipart():
            queue.extend((child, depth + 1) for child in part.iter_parts())
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            raise IngestionError("invalid_document", "Invalid email payload")
        filename = part.get_filename()
        is_attachment = (
            filename is not None
            or part.get_content_disposition() == "attachment"
            or part.get_content_maintype() != "text"
        )
        if is_attachment:
            if len(attachments) >= MAX_ATTACHMENTS:
                raise IngestionError("too_many_attachments", "Email attachment limit exceeded")
            attachment_bytes += len(payload)
            if attachment_bytes > MAX_BYTES:
                raise IngestionError("file_too_large", "Decoded attachments exceed 10 MB")
            mime = sniff_mime(payload)
            suffix = {
                "application/pdf": ".pdf",
                "image/png": ".png",
                "image/jpeg": ".jpg",
            }.get(mime)
            if suffix is None:
                raise IngestionError("unsupported_type", "Unsupported email attachment")
            safe_name = (filename or ("attachment" + suffix)).replace("\\", "/").split("/")[-1]
            attachment = Upload(safe_name, payload, part.get_content_type())
            _verify_type(attachment)
            attachments.append(attachment)
        else:
            try:
                decoded = payload.decode(part.get_content_charset() or "utf-8", errors="strict")
            except (LookupError, UnicodeError) as error:
                raise IngestionError("invalid_document", "Undecodable email text") from error
            if part.get_content_type() == "text/plain":
                bodies.append(decoded)
            elif part.get_content_type() == "text/html":
                parser = _HTMLText()
                parser.feed(decoded)
                html_bodies.append(" ".join(parser.parts))
    body = "\n".join(bodies or html_bodies)
    headers = "\n".join(f"{key}: {value}" for key, value in message.items())
    text = headers + "\n\n" + body
    if len(text) > MAX_TEXT:
        raise IngestionError("document_limit", "Email text limit exceeded")
    return EmailData(
        from_address=sender,
        display_name=display,
        reply_to=reply or None,
        authentication_results=tuple(
            str(value) for value in message.get_all("Authentication-Results", [])
        ),
        body=body,
        source_text=text,
    ), tuple(attachments)


def ingest(upload: Upload) -> Document:
    """Validate bounded upload bytes and extract text without writing attachments."""
    mime = _verify_type(upload)
    digest = hashlib.sha256(upload.data).hexdigest()
    if mime == "application/pdf":
        pages = _pdf(upload.data)
        return Document(mime, "\n".join(pages), pages, (), digest)
    if mime.startswith("image/"):
        _image(upload.data, mime)
        return Document(mime, "", (), (upload.data,), digest)
    email, attachments = _email(upload.data)
    return Document(
        mime,
        email.source_text,
        (email.source_text,),
        (),
        digest,
        email,
        attachments,
    )
