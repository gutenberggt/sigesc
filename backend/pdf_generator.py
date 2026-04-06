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
    generate_relatorio_frequencia_bimestre_pdf,
    generate_learning_objects_pdf,
    generate_grades_report_pdf,
)

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
