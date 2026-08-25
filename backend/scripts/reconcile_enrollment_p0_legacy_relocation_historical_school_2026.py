#!/usr/bin/env python3
"""Executa o reparo P0 de remanejamentos legados com validação temporal de escola.

Extensão estrita do reparador `reconcile_enrollment_p0_legacy_relocation_2026.py`.
A única flexibilização permitida é para a turma de ORIGEM: quando seu `school_id`
atual não coincide com a escola do caso, o script exige prova em `school_history`
de que a turma pertencia à escola esperada exatamente no instante auditado do
remanejamento.

Por padrão permanece READ-ONLY. O gate de escrita, token, escopo nominal,
revalidação otimista e pós-condição são herdados integralmente do reparador base.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import reconcile_enrollment_p0_legacy_relocation_2026 as base


# Instantes confirmados por student_history + audit_logs em produção.
MOVEMENT_AT_BY_STUDENT = {
    "4cf4babd-39f0-4baf-aa22-d5a3369eed71": "2026-06-01T13:23:18.472942+00:00",
    "e924c856-6c26-4bc8-b257-6400b68ec675": "2026-06-01T13:22:25.362975+00:00",
}

_ORIGINAL_ASSESS_SNAPSHOT = base.assess_snapshot


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _parse_instant(value: Any) -> datetime | None:
    raw = _norm(value)
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def class_belongs_to_school_at(
    class_doc: dict[str, Any] | None,
    expected_school_id: str,
    instant: str,
) -> bool:
    """Confirma vínculo da turma com escola no instante, em modo fail-closed.

    Se a escola atual já é a esperada, aceita diretamente. Caso contrário,
    somente `school_history` com intervalo válido cobrindo o instante é aceito.
    Intervalo: start_date <= instante < end_date; `end_date=None` é aberto.
    """
    if not class_doc or not _norm(expected_school_id):
        return False

    if _norm(class_doc.get("school_id")) == _norm(expected_school_id):
        return True

    moment = _parse_instant(instant)
    if moment is None:
        return False

    history = class_doc.get("school_history")
    if not isinstance(history, list) or not history:
        return False

    for item in history:
        if not isinstance(item, dict):
            continue
        if _norm(item.get("school_id")) != _norm(expected_school_id):
            continue

        start = _parse_instant(item.get("start_date"))
        end_raw = item.get("end_date")
        end = _parse_instant(end_raw) if _norm(end_raw) else None

        # Histórico sem início válido não serve como prova temporal.
        if start is None:
            continue
        if moment < start:
            continue
        if end is not None and moment >= end:
            continue
        return True

    return False


def assess_snapshot(*, case: dict[str, str], origin_class=None, **kwargs):
    """Adapta apenas a validação da escola da turma de origem.

    O reparador base continua responsável por todos os demais invariantes.
    Quando o vínculo histórico é comprovado, passamos ao avaliador base uma
    cópia da turma com o `school_id` lógico da data auditada; nenhum documento
    de banco é alterado por essa normalização em memória.
    """
    effective_origin = origin_class
    expected_school = _norm(case.get("school_id"))
    current_origin_school = _norm((origin_class or {}).get("school_id"))

    if origin_class and current_origin_school != expected_school:
        movement_at = MOVEMENT_AT_BY_STUDENT.get(_norm(case.get("student_id")), "")
        if class_belongs_to_school_at(origin_class, expected_school, movement_at):
            effective_origin = dict(origin_class)
            effective_origin["school_id"] = expected_school

    return _ORIGINAL_ASSESS_SNAPSHOT(
        case=case,
        origin_class=effective_origin,
        **kwargs,
    )


# `base.assess_case()` resolve `assess_snapshot` no namespace do módulo base.
# Substituição deliberada e local ao processo deste wrapper.
base.assess_snapshot = assess_snapshot


if __name__ == "__main__":
    raise SystemExit(asyncio.run(base.run(base.parse_args())))
