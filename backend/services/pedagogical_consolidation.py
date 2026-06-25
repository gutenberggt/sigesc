"""Consolidação pedagógica canônica na movimentação de alunos.

Princípio 1 (Preservação): a turma de ORIGEM nunca é alterada/removida.
Princípio 2 (Continuidade): a turma de DESTINO recebe cópia idempotente de
frequência, notas E conteúdo (objetos de conhecimento) do aluno.

Idempotente: rodar duas vezes não duplica (skip quando já existe no destino).
Usado pelo motor de movimentação (backend) e pela ferramenta de Reconstrução.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


async def consolidate_student_movement(db, *, student_id, source_class_id,
                                       target_class_id, academic_year=None):
    if not source_class_id or not target_class_id or source_class_id == target_class_id:
        return {"attendance": 0, "grades": 0, "content_entries": 0, "skipped": True}

    # Ano de referência: herda da turma de ORIGEM (onde o dado foi lançado).
    if academic_year is None:
        src = await db.classes.find_one({"id": source_class_id}, {"_id": 0, "academic_year": 1})
        academic_year = (src or {}).get("academic_year") or datetime.now().year

    now = datetime.now(timezone.utc).isoformat()
    counts = {"attendance": 0, "grades": 0, "content_entries": 0}

    # ===== Frequência (registros do aluno) =====
    attendances = await db.attendance.find(
        {"class_id": source_class_id, "academic_year": academic_year, "records.student_id": student_id},
        {"_id": 0}).to_list(2000)
    for att in attendances:
        student_record = next((dict(r) for r in att.get("records", []) if r.get("student_id") == student_id), None)
        if not student_record:
            continue
        student_record["migrated_from_class_id"] = source_class_id
        student_record["migrated_at"] = now
        existing = await db.attendance.find_one(
            {"class_id": target_class_id, "date": att["date"], "academic_year": academic_year})
        if existing:
            recs = [r for r in existing.get("records", []) if r.get("student_id") != student_id]
            recs.append(student_record)
            await db.attendance.update_one({"id": existing["id"]}, {"$set": {"records": recs}})
        else:
            await db.attendance.insert_one({
                "id": str(uuid.uuid4()), "class_id": target_class_id, "date": att["date"],
                "academic_year": academic_year, "records": [student_record],
                "period": att.get("period", "regular"), "course_id": att.get("course_id"),
                "created_at": now})
        counts["attendance"] += 1

    # ===== Notas =====
    grades = await db.grades.find(
        {"class_id": source_class_id, "student_id": student_id, "academic_year": academic_year},
        {"_id": 0}).to_list(500)
    for g in grades:
        exists = await db.grades.find_one({
            "class_id": target_class_id, "student_id": student_id,
            "course_id": g.get("course_id"), "academic_year": academic_year})
        if exists:
            continue
        await db.grades.insert_one({**g, "id": str(uuid.uuid4()), "class_id": target_class_id,
                                    "migrated_from_class_id": source_class_id, "migrated_at": now,
                                    "created_at": now})
        counts["grades"] += 1

    # ===== Conteúdo / Objetos de Conhecimento =====
    # content_entries é por (turma, curso, data). Copia idempotente para o destino,
    # preservando o que o aluno teve no período cursado na origem.
    contents = await db.content_entries.find(
        {"class_id": source_class_id, "academic_year": academic_year}, {"_id": 0}).to_list(3000)
    if not contents:  # alguns registros legados não têm academic_year
        contents = await db.content_entries.find({"class_id": source_class_id}, {"_id": 0}).to_list(3000)
    for c in contents:
        if c.get("deleted"):
            continue
        exists = await db.content_entries.find_one({
            "class_id": target_class_id, "course_id": c.get("course_id"), "date": c.get("date")})
        if exists:
            continue
        await db.content_entries.insert_one({**c, "id": str(uuid.uuid4()), "class_id": target_class_id,
                                             "migrated_from_class_id": source_class_id, "migrated_at": now,
                                             "created_at": now})
        counts["content_entries"] += 1

    counts["academic_year"] = academic_year
    return counts
