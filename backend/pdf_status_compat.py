"""Compatibilidade de status para relatórios PDF de frequência.

O histórico do SIGESC contém registros com códigos curtos (P/F/J), enquanto o
gerador modular de PDF trabalha com os valores canônicos
present/absent/justified. Esta camada é deliberadamente pura: não altera banco,
não muta os objetos recebidos e mantém valores já canônicos intactos.
"""

from __future__ import annotations

from typing import Any, Mapping


_LEGACY_TO_CANONICAL = {
    "P": "present",
    "F": "absent",
    "J": "justified",
}


def normalize_attendance_status_for_pdf(status: Any) -> Any:
    """Converte P/F/J para o vocabulário esperado pelo gerador de PDF.

    Valores canônicos e valores desconhecidos são preservados para manter o
    comportamento anterior do renderer (que decide como exibi-los).
    """
    if status is None:
        return status
    if not isinstance(status, str):
        return status
    value = status.strip()
    return _LEGACY_TO_CANONICAL.get(value, value)


def normalize_students_attendance_for_pdf(
    students_attendance: list[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Retorna cópia compatível com PDF sem modificar o payload original."""
    normalized: list[dict[str, Any]] = []
    for student in students_attendance or []:
        item = dict(student)
        attendance_by_date = item.get("attendance_by_date") or {}
        item["attendance_by_date"] = {
            key: normalize_attendance_status_for_pdf(value)
            for key, value in attendance_by_date.items()
        }
        normalized.append(item)
    return normalized
