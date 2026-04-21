"""
Sistema de Jobs assíncronos para geração de PDFs pesados.

⚠️  PERFORMANCE — LEIA /app/docs/pdf-performance.md ANTES DE ALTERAR ⚠️

Fluxo:
  1. Cliente chama POST .../async → retorna {job_id, status:'queued'}
  2. Cliente faz polling em GET .../job/{id}/status
  3. Quando status == 'done', cliente chama GET .../job/{id}/download
  4. Jobs expiram 10 min após conclusão (limpeza automática)

Mantém tudo em memória (single-worker, suficiente para SIGESC).
Se escalar horizontalmente, migrar para Redis.
"""
from __future__ import annotations
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

JOB_TTL_SECONDS = 600  # 10 min


@dataclass
class PdfJob:
    id: str
    status: str = 'queued'  # queued | running | done | error
    progress: int = 0
    message: str = 'Na fila'
    filename: str = 'documento.pdf'
    pdf_bytes: Optional[bytes] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    done_at: Optional[float] = None


class _JobRegistry:
    def __init__(self):
        self._jobs: dict[str, PdfJob] = {}
        self._lock = asyncio.Lock()

    def create(self) -> PdfJob:
        job = PdfJob(id=str(uuid.uuid4()))
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[PdfJob]:
        self._gc()
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for k, v in fields.items():
            setattr(job, k, v)

    def _gc(self) -> None:
        """Remove jobs finalizados há mais que JOB_TTL_SECONDS."""
        now = time.time()
        expired = [
            jid for jid, j in self._jobs.items()
            if j.done_at and (now - j.done_at) > JOB_TTL_SECONDS
        ]
        for jid in expired:
            self._jobs.pop(jid, None)


job_registry = _JobRegistry()


async def run_pdf_job(
    job_id: str,
    generator: Callable,
    *args,
    stages: Optional[list[tuple[int, str]]] = None,
    **kwargs,
) -> None:
    """Executa o gerador de PDF em background, reportando progresso.
    `generator` deve ser uma async callable que recebe um parâmetro `progress_cb`
    (ou ignora) e retorna (pdf_bytes, filename).
    """
    job = job_registry.get(job_id)
    if not job:
        return
    job_registry.update(job_id, status='running', progress=5, message='Iniciando...')

    def progress_cb(pct: int, msg: str = ''):
        job_registry.update(job_id, progress=max(5, min(95, pct)), message=msg or job.message)

    try:
        # Injetar callback se o generator suportar
        pdf_bytes, filename = await generator(*args, progress_cb=progress_cb, **kwargs)
        job_registry.update(
            job_id,
            status='done', progress=100, message='Concluído',
            pdf_bytes=pdf_bytes, filename=filename, done_at=time.time(),
        )
    except Exception as e:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        job_registry.update(
            job_id,
            status='error',
            error=str(e) or 'Erro ao gerar PDF',
            message='Erro',
            done_at=time.time(),
        )
        # Log verboso
        import logging
        logging.getLogger(__name__).error(f"PDF job {job_id} falhou: {e}\n{tb}")
