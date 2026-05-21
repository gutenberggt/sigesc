"""Seeds idempotentes (templates, dados de referência).

Extraído de `server.py` (Fev/2026). Cada função é tolerante a falha — log warning
mas não interrompe startup.
"""
import logging

logger = logging.getLogger(__name__)


async def run_all_seeds(db):
    """Roda todos os seeds idempotentes na ordem correta."""
    # Feb/2026: 8 modelos institucionais de Plano AEE.
    try:
        from seeds.aee_templates_seed import seed_aee_templates
        await seed_aee_templates(db)
    except Exception as exc:
        logger.warning(f"Seed AEE templates: ignorado por erro: {exc}")

    # May/2026: BNCC complementar de Computação.
    try:
        from seeds.seed_computacao_bncc import seed_computacao
        stats = await seed_computacao(db)
        logger.info(f"Seed Currículo Computação: {stats}")
    except Exception as exc:
        logger.warning(f"Seed Currículo Computação: ignorado por erro: {exc}")

    # Fev/2026: Motivos oficiais MEC (Sistema Presença v4.2).
    try:
        from seeds.seed_mec_frequency_reasons import seed_attendance_frequency_reasons
        stats = await seed_attendance_frequency_reasons(db)
        logger.info(f"Seed Motivos MEC: {stats}")
    except Exception as exc:
        logger.warning(f"Seed Motivos MEC: ignorado por erro: {exc}")


async def init_external_services(db, client):
    """Inicializa índices e serviços externos (snapshots, verifiable_docs, monthly_reports)."""
    try:
        from services.snapshot_service import ensure_ttl_index as _ensure_snap_ttl
        await _ensure_snap_ttl(db)
    except Exception as exc:
        logger.warning(f"snapshot_service.ensure_ttl_index: {exc}")

    try:
        from services.verifiable_docs_service import ensure_indexes as _ensure_vd_idx
        await _ensure_vd_idx(db)
    except Exception as exc:
        logger.warning(f"verifiable_docs_service.ensure_indexes: {exc}")

    try:
        from services.monthly_report_service import ensure_indexes as _ensure_mr_idx
        await _ensure_mr_idx(db)
    except Exception as exc:
        logger.warning(f"monthly_report_service.ensure_indexes: {exc}")

    try:
        from services.monthly_report_scheduler import start_scheduler as _start_mr_sched
        _start_mr_sched(db)
    except Exception as exc:
        logger.warning(f"monthly_report_scheduler.start: {exc}")
