#!/usr/bin/env python3
"""N2 — normalização direcionada de nomenclatura em documentos emitidos.

Somente textos efetivamente impressos/emitidos em PDFs e relatórios institucionais.
Não altera IDs, campos, rotas, mensagens HTTP, filenames técnicos ou regras.
Arquivo temporário: remover antes do PR final.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = {
    "backend/pdf/declaracoes.py": [
        (
            "O(A) referido(a) aluno(a) está sendo transferido(a) desta instituição a pedido \n    de seu responsável legal, nada constando que o(a) desabone em termos de conduta \n    e aproveitamento escolar.",
            "O estudante acima identificado está sendo transferido desta instituição a pedido \n    de seu responsável legal, nada constando que desabone sua conduta ou seu \n    aproveitamento escolar.",
        ),
        (
            "Informamos que o <b>Histórico Escolar</b> do(a) aluno(a) será emitido e ",
            "Informamos que o <b>Histórico Escolar</b> do estudante será emitido e ",
        ),
    ],
    "backend/pdf/diario_aee.py": [
        ("Paragraph('Aluno(a):', label)", "Paragraph('Estudante:', label)"),
    ],
    "backend/pdf/dossie_institucional.py": [
        ('("Capacidade Total de Alunos", school.get("capacidade_total_alunos"))', '("Capacidade Total de Estudantes", school.get("capacidade_total_alunos"))'),
    ],
    "backend/pdf/ficha_individual.py": [
        ('<b>NOME DO(A) ALUNO(A):</b>', '<b>NOME DO ESTUDANTE:</b>'),
    ],
    "backend/pdf/historico_escolar.py": [
        ("p_lbl('ALUNO(A)')", "p_lbl('ESTUDANTE')"),
    ],
    "backend/pdf/livro_promocao.py": [
        ('Total de alunos(as): {total_alunos:02d}', 'Total de estudantes: {total_alunos:02d}'),
    ],
    "backend/pdf/notas.py": [
        ('<b>Total de Alunos:</b>', '<b>Total de Estudantes:</b>'),
        ('<b>ALUNO(A)</b>', '<b>ESTUDANTE</b>'),
        ('Nenhum aluno encontrado.', 'Nenhum estudante encontrado.'),
    ],
    "backend/pdf/plano_aee.py": [
        ("Paragraph('Aluno(a):', label)", "Paragraph('Estudante:', label)"),
    ],
    "backend/pdf/transfer_receipt.py": [
        ('("Alunos afetados",', '("Estudantes afetados",'),
    ],
    "backend/pdf/turma.py": [
        ("make_field('Alunos Matriculados:'", "make_field('Estudantes Matriculados:'"),
        ('section_header(f"ALUNOS MATRICULADOS ({len(students)})")', 'section_header(f"ESTUDANTES MATRICULADOS ({len(students)})")'),
        ("Paragraph('Aluno(a)', th_style)", "Paragraph('Estudante', th_style)"),
        ('Paragraph("Nenhum aluno matriculado", no_data_style)', 'Paragraph("Nenhum estudante matriculado", no_data_style)'),
    ],
    "backend/routers/bolsa_familia.py": [
        ('("Aluno", "student_name")', '("Estudante", "student_name")'),
        ('Paragraph("Alunos Transferidos no Período", trans_title_style)', 'Paragraph("Estudantes Transferidos no Período", trans_title_style)'),
    ],
    "backend/routers/history_reconstruction.py": [
        ('("Alunos processados", str(audit.get("students_processed")))', '("Estudantes processados", str(audit.get("students_processed")))'),
    ],
    "backend/routers/students.py": [
        ('header_text = "RELATÓRIO DE ALUNOS"', 'header_text = "RELATÓRIO DE ESTUDANTES"'),
        ('elements.append(Paragraph(f"Total: {len(students)} aluno(s) ativo(s)", subtitle_style))', 'elements.append(Paragraph(f"Total de estudantes ativos: {len(students)}", subtitle_style))'),
    ],
    "frontend/src/pages/AnalyticsDashboard.jsx": [
        ('% dos alunos com 2+ anos acima da idade esperada', '% dos estudantes com 2+ anos acima da idade esperada'),
    ],
}

FORBIDDEN_TARGET_SNIPPETS = {
    "backend/pdf/declaracoes.py": ["referido(a) aluno(a)", "Histórico Escolar</b> do(a) aluno(a)"],
    "backend/pdf/diario_aee.py": ["Paragraph('Aluno(a):', label)"],
    "backend/pdf/dossie_institucional.py": ["Capacidade Total de Alunos"],
    "backend/pdf/ficha_individual.py": ["NOME DO(A) ALUNO(A)"],
    "backend/pdf/historico_escolar.py": ["p_lbl('ALUNO(A)')"],
    "backend/pdf/livro_promocao.py": ["Total de alunos(as):"],
    "backend/pdf/notas.py": ["Total de Alunos:", "ALUNO(A)", "Nenhum aluno encontrado."],
    "backend/pdf/plano_aee.py": ["Paragraph('Aluno(a):', label)"],
    "backend/pdf/transfer_receipt.py": ["Alunos afetados"],
    "backend/pdf/turma.py": [
        "make_field('Alunos Matriculados:'",
        'section_header(f"ALUNOS MATRICULADOS',
        "Paragraph('Aluno(a)', th_style)",
        'Paragraph("Nenhum aluno matriculado"',
    ],
    "backend/routers/bolsa_familia.py": ['("Aluno", "student_name")', "Alunos Transferidos no Período"],
    "backend/routers/history_reconstruction.py": ["Alunos processados"],
    "backend/routers/students.py": ["RELATÓRIO DE ALUNOS", "aluno(s) ativo(s)"],
    "frontend/src/pages/AnalyticsDashboard.jsx": ["% dos alunos com 2+ anos acima da idade esperada"],
}


def main() -> int:
    changed_files = 0
    replacements_done = 0
    print("N2_APPLY_BEGIN")
    for relative, replacements in REPLACEMENTS.items():
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        original = text
        for old, new in replacements:
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                replacements_done += count
                print(f"REPLACE {relative} x{count}: {old!r} -> {new!r}")
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed_files += 1
    print(f"N2_APPLY_END files_changed={changed_files} replacements={replacements_done}")

    failures = []
    for relative, snippets in FORBIDDEN_TARGET_SNIPPETS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet in text:
                failures.append((relative, snippet))
    print(f"N2_TARGET_VALIDATION forbidden_remaining={len(failures)}")
    for relative, snippet in failures:
        print(f"FORBIDDEN_REMAINS {relative}: {snippet!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
