"""Helpers para armazenar/recuperar PDFs gerados via render_jobs.

Estratégia simples: collection `document_files` com `data_base64` (escala bem
para boletins individuais de até ~50 KB cada). Se um dia precisar lidar com
arquivos maiores (>1 MB), trocar por GridFS sem mudar contrato externo.
"""
from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional


async def store_pdf(
    db,
    *,
    pdf_bytes: bytes,
    filename: str,
    document_type: str,
    mantenedora_id: Optional[str] = None,
    school_id: Optional[str] = None,
    student_id: Optional[str] = None,
) -> dict:
    """Persiste o PDF e retorna {file_id, size, sha256, filename}."""
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    file_id = str(uuid.uuid4())
    doc = {
        "id": file_id,
        "filename": filename,
        "document_type": document_type,
        "mime_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
        "sha256": sha,
        "data_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "mantenedora_id": mantenedora_id,
        "school_id": school_id,
        "student_id": student_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.document_files.insert_one(doc)
    return {
        "file_id": file_id,
        "size_bytes": len(pdf_bytes),
        "sha256": sha,
        "filename": filename,
    }


async def fetch_pdf(db, file_id: str) -> Optional[dict]:
    """Retorna {pdf_bytes, filename, sha256, ...} ou None."""
    doc = await db.document_files.find_one({"id": file_id}, {"_id": 0})
    if not doc:
        return None
    pdf = base64.b64decode(doc["data_base64"])
    return {
        "pdf_bytes": pdf,
        "filename": doc.get("filename") or "documento.pdf",
        "sha256": doc.get("sha256"),
        "mime_type": doc.get("mime_type") or "application/pdf",
        "size_bytes": doc.get("size_bytes") or len(pdf),
        "created_at": doc.get("created_at"),
    }
