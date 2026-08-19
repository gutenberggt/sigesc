"""
SIGESC - Gerador de PDFs (Bridge para compatibilidade)
Este arquivo re-exporta todos os geradores do pacote `pdf/` modularizado.
Imports existentes como `from pdf_generator import generate_boletim_pdf` continuam funcionando.
"""

from pdf import (
    generate_boletim_pdf,
    generate_declaracao_matricula_pdf,
    generate_declaracao_transferencia_pdf,
    generate_declaracao_frequencia_pdf,
    generate_ficha_individual_pdf,
    generate_certificado_pdf,
    generate_class_details_pdf,
    generate_livro_promocao_pdf,
    generate_relatorio_frequencia_bimestre_pdf as _generate_relatorio_frequencia_bimestre_pdf,
    generate_learning_objects_pdf,
    generate_grades_report_pdf,
)
from pdf_status_compat import normalize_students_attendance_for_pdf


def generate_relatorio_frequencia_bimestre_pdf(*args, **kwargs):
    """Bridge compatível com status históricos P/F/J e canônicos.

    O gerador modular espera `present/absent/justified`, mas documentos
    históricos de frequência usam majoritariamente P/F/J. A normalização ocorre
    somente no payload de renderização; banco e autoria permanecem intocados.
    """
    if "students_attendance" in kwargs:
        kwargs = dict(kwargs)
        kwargs["students_attendance"] = normalize_students_attendance_for_pdf(
            kwargs.get("students_attendance")
        )
    elif len(args) >= 4:
        args = list(args)
        args[3] = normalize_students_attendance_for_pdf(args[3])
        args = tuple(args)

    return _generate_relatorio_frequencia_bimestre_pdf(*args, **kwargs)


__all__ = [
    'generate_boletim_pdf',
    'generate_declaracao_matricula_pdf',
    'generate_declaracao_transferencia_pdf',
    'generate_declaracao_frequencia_pdf',
    'generate_ficha_individual_pdf',
    'generate_certificado_pdf',
    'generate_class_details_pdf',
    'generate_livro_promocao_pdf',
    'generate_relatorio_frequencia_bimestre_pdf',
    'generate_learning_objects_pdf',
    'generate_grades_report_pdf',
]
