"""
Regressão — Controle de Frequência (PDF): células P/F/J em branco para aluno ATIVO.

Bug: o PDF de frequência por bimestre (`GET /api/attendance/pdf/bimestre/{class_id}`)
apaga as células a partir da `action_date` de alunos que SAÍRAM da turma
(student_history: transferencia_saida/remanejamento/progressao/reclassificacao/
desistencia/cancelamento). Porém alunos que continuam ATIVOS na turma mas que
possuem um registro histórico antigo (ex.: foram cancelados/remanejados e depois
REMATRICULADOS na mesma turma) tinham TODAS as células P/F/J apagadas, mesmo com
frequência lançada.

Fix: não apagar células de alunos que estão ATIVOS na turma.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import httpx
import pdfplumber
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
SCHOOL = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
CLASS = "c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd"
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PWD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")


async def _run_scenario():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    sid = str(uuid.uuid4())
    name = f"ZZ REGRESSAO FREQ {str(uuid.uuid4())[:5]}"
    dates = ["2026-03-10", "2026-03-11"]
    try:
        await db.students.insert_one({
            "id": sid, "full_name": name, "school_id": SCHOOL, "class_id": CLASS,
            "status": "active", "benefits": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.enrollments.insert_one({
            "id": str(uuid.uuid4()), "student_id": sid, "school_id": SCHOOL,
            "class_id": CLASS, "academic_year": 2026, "status": "active",
            "enrollment_number": "ZZREG1",
        })
        att_ids = []
        for d in dates:
            aid = str(uuid.uuid4()); att_ids.append(aid)
            await db.attendance.insert_one({
                "id": aid, "class_id": CLASS, "date": d, "period": "regular",
                "records": [{"student_id": sid, "status": "P"}],
                "number_of_classes": 1, "academic_year": 2026, "aula_numero": 1,
            })
        # Histórico ANTIGO de cancelamento (action_date antes das frequências) — o
        # gatilho que antes apagava as células.
        hist_id = str(uuid.uuid4())
        await db.student_history.insert_one({
            "id": hist_id, "student_id": sid, "school_id": SCHOOL, "class_id": CLASS,
            "action_type": "cancelamento", "action_date": "2026-02-15T12:00:00+00:00",
        })

        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            lg = (await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})).json()
            h = {"Authorization": f"Bearer {lg['access_token']}", "X-CSRF-Token": lg["csrf_token"]}
            pdf = await c.get(f"/api/attendance/pdf/bimestre/{CLASS}?bimestre=1&academic_year=2026", headers=h)
        return pdf.status_code, pdf.content, name
    finally:
        await db.students.delete_one({"id": sid})
        await db.enrollments.delete_many({"student_id": sid})
        await db.attendance.delete_many({"id": {"$in": att_ids}})
        await db.student_history.delete_many({"student_id": sid})


def _row_cells(pdf_bytes, name_token):
    path = f"/tmp/_freq_regr_{uuid.uuid4().hex}.pdf"
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    try:
        with pdfplumber.open(path) as pdf:
            words = pdf.pages[0].extract_words()
        anchor = next((w for w in words if w["text"] == name_token), None)
        assert anchor, f"Linha do aluno ({name_token}) não encontrada no PDF"
        y = anchor["top"]
        row = sorted([w for w in words if abs(w["top"] - y) < 4], key=lambda w: w["x0"])
        return [w["text"] for w in row]
    finally:
        os.remove(path)


def test_active_student_with_stale_history_not_blanked():
    status, content, name = asyncio.run(_run_scenario())
    assert status == 200, f"PDF deve gerar 200, veio {status}"
    token = name.split()[-1]  # sufixo único
    cells = _row_cells(content, token)
    # Deve conter as presenças (P) e o total PRESEN.=2, FALTAS=0 — NÃO em branco.
    assert cells.count("P") == 2, f"Esperado 2 'P' nas células, veio: {cells}"
    assert cells[-2:] == ["0", "2"], f"Esperado FALTAS=0 PRESEN.=2, veio: {cells[-2:]} ({cells})"
    print(f"✓ Aluno ativo com histórico antigo renderiza P/F/J corretamente: {cells}")


if __name__ == "__main__":
    test_active_student_with_stale_history_not_blanked()
    print("OK")
