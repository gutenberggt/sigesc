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


# ============================================================================
# Signature images (Fase 5c — Mai/2026)
# ============================================================================
# Reaproveita a mesma coleção `document_files` com document_type='signature_image'.
# Limites obrigatórios do owner:
#   - MAX 512 KB · PNG/JPG/WEBP · 600x200 px
#   - MIME validado server-side
#   - Re-encode obrigatório (anti-payload malicioso)
#   - Transparência preservada
ALLOWED_SIGNATURE_MIMES = {"image/png", "image/jpeg", "image/webp"}
SIGNATURE_MAX_BYTES = 512 * 1024
SIGNATURE_MAX_WIDTH = 600
SIGNATURE_MAX_HEIGHT = 200


def _reencode_signature(raw: bytes, declared_mime: str) -> tuple[bytes, str, int, int]:
    """Re-codifica a imagem para PNG (transparência preservada).

    Anti-payload: descarta qualquer EXIF/metadata; valida que é imagem real;
    rejeita extensões maliciosas; redimensiona se exceder 600x200.

    Returns (png_bytes, mime_type, width, height).
    """
    from PIL import Image
    from io import BytesIO

    if declared_mime not in ALLOWED_SIGNATURE_MIMES:
        raise ValueError(f"MIME_NOT_ALLOWED: {declared_mime}")
    if len(raw) > SIGNATURE_MAX_BYTES:
        raise ValueError(f"FILE_TOO_LARGE: {len(raw)} > {SIGNATURE_MAX_BYTES}")
    try:
        img = Image.open(BytesIO(raw))
        img.verify()  # detecta corrupção
        img = Image.open(BytesIO(raw))  # reabre (verify consome o stream)
    except Exception as e:
        raise ValueError(f"INVALID_IMAGE: {e}")

    # Garante modo RGBA (transparência preservada)
    if img.mode not in ("RGBA", "LA"):
        img = img.convert("RGBA")
    # Redimensiona se exceder limites (mantém aspect ratio)
    if img.width > SIGNATURE_MAX_WIDTH or img.height > SIGNATURE_MAX_HEIGHT:
        img.thumbnail((SIGNATURE_MAX_WIDTH, SIGNATURE_MAX_HEIGHT), Image.Resampling.LANCZOS)
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)  # PNG = transparência + sem EXIF
    return out.getvalue(), "image/png", img.width, img.height


async def store_signature_image(
    db, *,
    raw_bytes: bytes,
    declared_mime: str,
    user_id: str,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Persiste assinatura institucional. Substitui a anterior do mesmo user.

    Returns {file_id, size_bytes, sha256, width, height, mime_type}.
    """
    png_bytes, mime, width, height = _reencode_signature(raw_bytes, declared_mime)
    sha = hashlib.sha256(png_bytes).hexdigest()
    file_id = str(uuid.uuid4())
    doc = {
        "id": file_id,
        "filename": f"signature_{user_id}.png",
        "document_type": "signature_image",
        "mime_type": mime,
        "size_bytes": len(png_bytes),
        "sha256": sha,
        "width": width,
        "height": height,
        "data_base64": base64.b64encode(png_bytes).decode("ascii"),
        "owner_user_id": user_id,
        "mantenedora_id": mantenedora_id,
        "school_id": None,
        "student_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.document_files.insert_one(doc)
    return {
        "file_id": file_id,
        "size_bytes": len(png_bytes),
        "sha256": sha,
        "width": width,
        "height": height,
        "mime_type": mime,
    }


async def fetch_signature_image(db, file_id: str) -> Optional[dict]:
    doc = await db.document_files.find_one(
        {"id": file_id, "document_type": "signature_image"}, {"_id": 0},
    )
    if not doc:
        return None
    return {
        "bytes": base64.b64decode(doc["data_base64"]),
        "mime_type": doc.get("mime_type") or "image/png",
        "width": doc.get("width"),
        "height": doc.get("height"),
        "size_bytes": doc.get("size_bytes"),
    }
