#!/usr/bin/env python3
"""Scanner temporário da N2 — nomenclatura em PDFs/documentos emitidos.

Não altera arquivos. Lista ocorrências de Aluno/Aluna/Alunos/Alunas apenas em
arquivos com sinais de geração/entrega de documentos. Remover antes do PR final.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERM_RE = re.compile(r"(?i)\b(?:aluno|aluna|alunos|alunas)(?:\(a?s?\))?\b")
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".jinja", ".jinja2"}
PDF_SIGNALS = (
    "reportlab", "SimpleDocTemplate", "canvas.Canvas", "application/pdf",
    "FileResponse", "StreamingResponse", "BytesIO", "jsPDF", "autoTable",
    "doc.text", ".pdf", "pdf_", "_pdf", "gerar_pdf", "generate_pdf",
)


def is_candidate(path: Path, text: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("backend/pdf/"):
        return True
    if rel.startswith("backend/routers/") or rel.startswith("backend/services/"):
        return any(sig in text for sig in PDF_SIGNALS)
    if rel.startswith("frontend/src/"):
        return any(sig in text for sig in PDF_SIGNALS)
    return False


def main() -> int:
    files = 0
    matches = 0
    print("N2_DOCUMENT_TERM_SCAN_BEGIN")
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if not is_candidate(path, text):
            continue
        file_matches = []
        for line_no, line in enumerate(text.splitlines(), 1):
            if TERM_RE.search(line):
                file_matches.append((line_no, line.strip()))
        if not file_matches:
            continue
        files += 1
        rel = path.relative_to(ROOT).as_posix()
        print(f"FILE {rel} matches={len(file_matches)}")
        for line_no, line in file_matches:
            matches += 1
            print(f"MATCH {rel}:{line_no}: {line}")
    print(f"N2_DOCUMENT_TERM_SCAN_END files={files} matches={matches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
