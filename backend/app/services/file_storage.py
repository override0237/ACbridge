"""Safe storage for private uploads (verification evidence, hardship documents).

* Only genuine JPG / PNG / PDF files: the extension AND the file's first bytes must agree.
* Size-capped; stored under a server-generated name (the client's filename is never used on disk,
  which blocks path traversal); never served from a public folder.
"""
import uuid
from pathlib import Path

from app.config import get_settings
from app.errors import BadRequestError

_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",), ".pdf": (b"%PDF-",),
}


def store_private_file(folder_name: str, owner_id: uuid.UUID, filename: str, data: bytes) -> str:
    settings = get_settings()
    if len(data) == 0 or len(data) > settings.max_evidence_bytes:
        raise BadRequestError(f"File must be between 1 byte and {settings.max_evidence_bytes} bytes")
    extension = Path(filename or "").suffix.lower()
    signatures = _SIGNATURES.get(extension)
    if signatures is None or not data.startswith(signatures):
        raise BadRequestError("Only genuine JPG, PNG or PDF files are accepted")
    folder = Path(settings.evidence_upload_dir) / folder_name / str(owner_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}{extension}"
    stored.write_bytes(data)
    return str(stored)
