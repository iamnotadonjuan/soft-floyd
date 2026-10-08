"""Validation and model input for account-owned coach image attachments."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class CoachImage:
    mime_type: str
    data: bytes

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data).decode('ascii')}"


def parse_image_data_url(value: str | None) -> CoachImage | None:
    if value is None:
        return None
    header, separator, encoded = value.partition(",")
    if not separator or not header.startswith("data:") or not header.endswith(";base64"):
        raise ValueError("Image must be a JPEG, PNG, or WebP file")
    mime_type = header[5:-7]
    if mime_type not in MIME_TYPES:
        raise ValueError("Image must be a JPEG, PNG, or WebP file")
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("Image must be 5 MB or smaller")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image data is invalid") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 5 MB or smaller")
    valid = (
        (mime_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff"))
        or (mime_type == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )
    if not valid:
        raise ValueError("Image content does not match its file type")
    return CoachImage(mime_type, data)
