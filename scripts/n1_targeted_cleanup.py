#!/usr/bin/env python3
"""Limpeza direcionada N1 após a normalização genérica.

Corrige resíduos visíveis e restaura fronteiras técnicas que NÃO pertencem ao N1.
Arquivo temporário: remover antes do PR final.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
TERM_RE = re.compile(r"(?i)\b(?:aluno|aluna|alunos|alunas)(?:\(a?s?\))?|Estudante\(a\)|Estudantes\(as\)")

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
        ("{attendanceData.students.length} alunos", "{attendanceData.students.length} estudantes"),
    ],
    "frontend/src/components/attendance/InformacoesTab.jsx": [
        ("{infoStudents.length} aluno(s)", "{infoStudents.length} estudantes"),
    ],
    "frontend/src/components/attendance/RelatoriosTab.jsx": [
        ("{classReport.total_students} alunos", "{classReport.total_students} estudantes"),
    ],
    "frontend/src/pages/BolsaFamilia.js": [
        ('<span className="opacity-80">alunos</span>', '<span className="opacity-80">estudantes</span>'),
    ],
    "frontend/src/pages/MonthlyReports.jsx": [
        ("</strong> alunos", "</strong> estudantes"),
    ],
    "frontend/src/pages/PmeAnosFinais.jsx": [
        ("} alunos`}", "} estudantes`}"),
    ],
    "frontend/src/pages/Promotion.jsx": [
        ("Exibindo {filteredPromotionData.length} de {promotionData.length} alunos", "Exibindo {filteredPromotionData.length} de {promotionData.length} estudantes"),
        ("Mostrar todos os alunos", "Mostrar todos os estudantes"),
        ("LISTA DE ALUNOS", "LISTA DE ESTUDANTES"),
        ("Mostrando {startIndex + 1} a {Math.min(endIndex, filteredPromotionData.length)} de {filteredPromotionData.length} alunos", "Mostrando {startIndex + 1} a {Math.min(endIndex, filteredPromotionData.length)} de {filteredPromotionData.length} estudantes"),
    ],
    "frontend/src/pages/StudentsComplete.js": [
        ("Gerando histórico(s) de ${serverTotal} alunos da turma...", "Gerando histórico(s) de ${serverTotal} estudantes da turma..."),
        ('placeholder="aluno@email.com"', 'placeholder="estudante@email.com"'),
        ("<strong>{serverTotal} alunos</strong>", "<strong>{serverTotal} estudantes</strong>"),
    ],
    "frontend/src/pages/VaccineDashboard.js": [
        ("{classInfo?.students?.length || 0} alunos", "{classInfo?.students?.length || 0} estudantes"),
        ("{classInfo?.total || 0} alunos", "{classInfo?.total || 0} estudantes"),
        ("Digite o nome ou CPF do aluno no campo de busca acima", "Digite o nome ou CPF do estudante no campo de busca acima"),
    ],
    "frontend/src/pages/AssocialDashboard.js": [
        ("Digite o nome ou CPF do aluno no campo de busca acima", "Digite o nome ou CPF do estudante no campo de busca acima"),
    ],
}


def scan_after_cleanup() -> int:
    residuals = 0
    forbidden = []
    print("POST_TARGET_RESIDUAL_SCAN_BEGIN")
    for path in sorted(FRONTEND.rglob("*")):
        if not path.is_file() or path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Estudante(a)" in line or "Estudantes(as)" in line or "role=estudante" in line:
                forbidden.append((path.relative_to(ROOT), line_no, line.strip()))
            if TERM_RE.search(line):
                residuals += 1
                print(f"POST_RESIDUAL {path.relative_to(ROOT)}:{line_no}: {line.strip()}")
    print(f"POST_TARGET_RESIDUAL_SCAN_END candidates={residuals}")
    if forbidden:
        print("FORBIDDEN_CANONICAL_FORMS_BEGIN")
        for path, line_no, line in forbidden:
            print(f"FORBIDDEN {path}:{line_no}: {line}")
        print(f"FORBIDDEN_CANONICAL_FORMS_END count={len(forbidden)}")
        return 1
    print("FORBIDDEN_CANONICAL_FORMS_END count=0")
    return 0


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
    return scan_after_cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
