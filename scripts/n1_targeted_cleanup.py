#!/usr/bin/env python3
"""Limpeza direcionada N1 após a normalização genérica.

Corrige resíduos visíveis e restaura fronteiras técnicas que NÃO pertencem ao N1.
Arquivo temporário: remover antes do PR final.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = {
    "frontend/src/pages/AdminTools.js": [
        ("Gera contas de acesso (role=estudante) para todos os estudantes", "Gera contas de acesso (role=aluno) para todos os estudantes"),
    ],
    "frontend/src/pages/DiarioAEE.js": [
        ("student?.full_name || 'estudante'", "student?.full_name || 'aluno'"),
    ],
    # N2 cuidará de documentos/PDFs. N1 não altera o texto gerado neste PDF.
    "frontend/src/pages/AnalyticsDashboard.jsx": [
        ("Distorção Idade-Série: ${ind.distorcao_idade_serie_pct || 0}% dos estudantes com 2+ anos acima da idade esperada", "Distorção Idade-Série: ${ind.distorcao_idade_serie_pct || 0}% dos alunos com 2+ anos acima da idade esperada"),
    ],
    "frontend/src/components/attendance/LancamentoTab.jsx": [
        ("{attendanceData.students.length} alunos</span>", "{attendanceData.students.length} estudantes</span>"),
    ],
    "frontend/src/components/attendance/InformacoesTab.jsx": [
        ("{infoStudents.length} aluno(s)</span>", "{infoStudents.length} estudantes</span>"),
    ],
    "frontend/src/components/attendance/RelatoriosTab.jsx": [
        ("{classReport.total_students} alunos</p>", "{classReport.total_students} estudantes</p>"),
    ],
    "frontend/src/pages/BolsaFamilia.js": [
        ('<span className="opacity-80">alunos</span>', '<span className="opacity-80">estudantes</span>'),
    ],
    "frontend/src/pages/MonthlyReports.jsx": [
        ("<strong>{summary.total_alunos}</strong> alunos", "<strong>{summary.total_alunos}</strong> estudantes"),
    ],
    "frontend/src/pages/PmeAnosFinais.jsx": [
        ("} alunos`}", "} estudantes`}"),
    ],
    "frontend/src/pages/Promotion.jsx": [
        ("} alunos</span>", "} estudantes</span>"),
        (">Mostrar todos os alunos<", ">Mostrar todos os estudantes<"),
        (">LISTA DE ALUNOS<", ">LISTA DE ESTUDANTES<"),
        ("} alunos</div>", "} estudantes</div>"),
    ],
    "frontend/src/pages/StudentsComplete.js": [
        ("Gerando histórico(s) de ${serverTotal} alunos da turma...", "Gerando histórico(s) de ${serverTotal} estudantes da turma..."),
        ('placeholder="aluno@email.com"', 'placeholder="estudante@email.com"'),
    ],
    "frontend/src/pages/VaccineDashboard.js": [
        ("{classInfo?.students?.length || 0} alunos</span>", "{classInfo?.students?.length || 0} estudantes</span>"),
        ("Digite o nome ou CPF do aluno no campo de busca acima", "Digite o nome ou CPF do estudante no campo de busca acima"),
    ],
    "frontend/src/pages/AssocialDashboard.js": [
        ("Digite o nome ou CPF do aluno no campo de busca acima", "Digite o nome ou CPF do estudante no campo de busca acima"),
    ],
}


def main() -> int:
    changed = 0
    print("TARGETED_CLEANUP_BEGIN")
    for relative, replacements in REPLACEMENTS.items():
        path = ROOT / relative
        if not path.exists():
            print(f"MISSING {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        for old, new in replacements:
            if old in text:
                count = text.count(old)
                text = text.replace(old, new)
                print(f"FIX {relative} x{count}: {old!r} -> {new!r}")
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    print(f"TARGETED_CLEANUP_END files_changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
