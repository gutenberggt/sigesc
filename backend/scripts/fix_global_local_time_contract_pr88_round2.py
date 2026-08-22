#!/usr/bin/env python3
"""Correções determinísticas após a primeira materialização do contrato temporal.

Motivação: a validação local do PR #88 detectou três problemas reais no gerador:
1. Attendance.js ainda convertia datas civis intermediárias via toISOString();
2. browserLocalDate.js continha uma comparação de compatibilidade usando toISOString();
3. ficha_individual.py recebeu o import de client_time dentro de um import multilinha.

Este script é idempotente e altera apenas o checkout atual. Não acessa banco,
não faz commit e não faz push.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
changed = []


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, source: str) -> None:
    path = ROOT / rel
    old = path.read_text(encoding="utf-8")
    if old != source:
        path.write_text(source, encoding="utf-8")
        changed.append(rel)


# 1) Attendance: navegação de data e iteração de calendário são datas civis.
rel = "frontend/src/pages/Attendance.js"
s = read(rel)
s = s.replace(
    "import { browserLocalTodayISO } from '@/utils/browserLocalDate';",
    "import { browserLocalDateISO, browserLocalTodayISO } from '@/utils/browserLocalDate';",
)
if "browserLocalDateISO" not in s:
    # Fallback para branches em que o import ainda não foi criado pelo aplicador principal.
    anchor = "import { useOffline } from '@/contexts/OfflineContext';"
    if anchor not in s:
        raise SystemExit("Attendance.js: ancora de import nao encontrada")
    s = s.replace(
        anchor,
        anchor + "\nimport { browserLocalDateISO, browserLocalTodayISO } from '@/utils/browserLocalDate';",
        1,
    )
s = s.replace(
    "setSelectedDate(date.toISOString().split('T')[0]);",
    "setSelectedDate(browserLocalDateISO(date));",
)
s = s.replace(
    "sabLet.add(d.toISOString().split('T')[0]);",
    "sabLet.add(browserLocalDateISO(d));",
)
s = s.replace(
    "blocked.add(d.toISOString().split('T')[0]);",
    "blocked.add(browserLocalDateISO(d));",
)
write(rel, s)


# 2) Helper local: a comparacao com o antigo default UTC continua valida, mas sem
# toISOString().slice(), para o guard global nao confundir compatibilidade com data civil.
rel = "frontend/src/utils/browserLocalDate.js"
s = read(rel)
s = s.replace(
    "const utcToday = now.toISOString().slice(0, 10);",
    "const utcToday = `${now.getUTCFullYear()}-${pad2(now.getUTCMonth() + 1)}-${pad2(now.getUTCDate())}`;",
)
write(rel, s)


# 3) Ficha Individual: corrige import inserido dentro de `from pdf.utils import (...)`.
rel = "backend/pdf/ficha_individual.py"
s = read(rel)
client_import = "from utils.client_time import local_now, local_today"
# Remove qualquer ocorrencia para reposiciona-la de forma deterministica.
s = s.replace(client_import + "\n", "")
anchor = "    NIVEL_ENSINO_LABELS\n)\n"
if anchor not in s:
    raise SystemExit("ficha_individual.py: fechamento do import pdf.utils nao encontrado")
s = s.replace(anchor, anchor + client_import + "\n", 1)
write(rel, s)

print("Round 2 aplicado.")
if changed:
    print("Arquivos corrigidos:")
    for rel in changed:
        print(f" - {rel}")
else:
    print("Nenhuma alteracao adicional necessaria.")
