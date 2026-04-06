"""
Módulo PDF do SIGESC - Pacote principal.
Re-exporta todos os geradores de PDF para compatibilidade com imports existentes.
"""

from pdf.boletim import generate_boletim_pdf
from pdf.declaracoes import (
    generate_declaracao_matricula_pdf,
    generate_declaracao_transferencia_pdf,
    generate_declaracao_frequencia_pdf,
)
from pdf.ficha_individual import generate_ficha_individual_pdf
from pdf.certificado import generate_certificado_pdf
from pdf.turma import generate_class_details_pdf
from pdf.livro_promocao import generate_livro_promocao_pdf
from pdf.frequencia import generate_relatorio_frequencia_bimestre_pdf
from pdf.objetos import generate_learning_objects_pdf
from pdf.notas import generate_grades_report_pdf

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
