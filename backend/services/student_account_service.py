"""
Service para criação em massa de usuários a partir de alunos cadastrados.

Regra de geração (definida pelo produto):
- Nome: student.full_name
- Email: {primeiro_nome}{ultimo_sobrenome}{MM_nascimento}@sigesc.com  (sem acentos, sem espaços, minúsculas)
- Senha: DDMMYYYY (8 dígitos da data de nascimento)
- Role: 'aluno'

Duplicatas de email recebem sufixo -2, -3, ...

Idempotência: se já existir um user ativo com role='aluno' vinculado ao mesmo
student_id, o serviço pula o aluno (não sobrescreve senha/email existente).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from auth_utils import hash_password

EMAIL_DOMAIN = "@sigesc.com"


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _slug(text: str) -> str:
    """Remove acentos e tudo que não é a-z / 0-9."""
    ascii_text = _strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]", "", ascii_text)


def _parse_birth_date(raw) -> Optional[tuple[str, str, str]]:
    """Retorna (DD, MM, YYYY) ou None se birth_date inválida."""
    if not raw:
        return None
    s = str(raw).strip()
    # Formatos aceitos: YYYY-MM-DD, DD/MM/YYYY, YYYY/MM/DD, ISO datetime
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mm, dd = m.group(1), m.group(2), m.group(3)
        return dd, mm, y
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return m.group(3), m.group(2), m.group(1)
    return None


def _build_email_base(full_name: str, mm: str) -> Optional[str]:
    """Retorna a parte local do email: primeironomeultimosobrenomeMM."""
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if len(parts) < 2:
        return None  # precisa de pelo menos 2 palavras para montar primeiro+último
    first = _slug(parts[0])
    last = _slug(parts[-1])
    if not first or not last:
        return None
    return f"{first}{last}{mm}"


async def _resolve_unique_email(db, base: str, reserved: set[str]) -> str:
    """Garante unicidade do email verificando DB + set de reservados (mesmo batch)."""
    candidate = f"{base}{EMAIL_DOMAIN}"
    attempt = 1
    while True:
        if candidate not in reserved:
            existing = await db.users.find_one({"email": candidate}, {"_id": 0, "id": 1})
            if not existing:
                reserved.add(candidate)
                return candidate
        attempt += 1
        candidate = f"{base}-{attempt}{EMAIL_DOMAIN}"


async def build_plan_for_students(
    db,
    *,
    mantenedora_id: Optional[str] = None,
    school_ids: Optional[List[str]] = None,
    include_inactive: bool = False,
) -> dict:
    """
    Gera plano (sem escrever) de criação de usuários para alunos ativos.

    Retorna:
        {
          'to_create': [ {student_id, full_name, email, password, birth_date, school_id, ...} ],
          'skipped':   [ {student_id, reason, ...} ],
          'already_has_user': [ {student_id, email, user_id} ],
          'totals': {...}
        }
    """
    to_create: list[dict] = []
    skipped: list[dict] = []
    already: list[dict] = []
    reserved_emails: set[str] = set()

    q: dict = {}
    if not include_inactive:
        q["status"] = {"$in": ["active", "Ativo", "ativo"]}
    if mantenedora_id:
        q["mantenedora_id"] = mantenedora_id
    if school_ids:
        q["school_id"] = {"$in": school_ids}

    cursor = db.students.find(q, {"_id": 0}).sort("full_name", 1)

    async for st in cursor:
        sid = st.get("id")
        name = (st.get("full_name") or "").strip()
        birth = _parse_birth_date(st.get("birth_date") or st.get("dob"))

        # Já tem user?
        existing_u = await db.users.find_one(
            {"student_id": sid, "role": "aluno"}, {"_id": 0, "id": 1, "email": 1}
        )
        if existing_u:
            already.append({"student_id": sid, "full_name": name,
                            "email": existing_u["email"], "user_id": existing_u["id"]})
            continue

        if not name or len(name.split()) < 2:
            skipped.append({"student_id": sid, "full_name": name,
                            "reason": "nome incompleto (precisa ter pelo menos 2 palavras)"})
            continue
        if not birth:
            skipped.append({"student_id": sid, "full_name": name,
                            "reason": "data de nascimento ausente ou inválida"})
            continue

        dd, mm, yyyy = birth
        base = _build_email_base(name, mm)
        if not base:
            skipped.append({"student_id": sid, "full_name": name,
                            "reason": "não foi possível gerar email base"})
            continue

        email = await _resolve_unique_email(db, base, reserved_emails)
        password_plain = f"{dd}{mm}{yyyy}"

        school_id = st.get("school_id")
        mant_id = st.get("mantenedora_id")
        if not mant_id and school_id:
            sch = await db.schools.find_one({"id": school_id}, {"_id": 0, "mantenedora_id": 1})
            mant_id = (sch or {}).get("mantenedora_id")

        to_create.append({
            "student_id": sid,
            "full_name": name,
            "email": email,
            "password": password_plain,
            "birth_date": f"{yyyy}-{mm}-{dd}",
            "school_id": school_id,
            "mantenedora_id": mant_id,
        })

    totals = {
        "to_create": len(to_create),
        "skipped": len(skipped),
        "already_has_user": len(already),
        "scanned": len(to_create) + len(skipped) + len(already),
    }
    return {
        "to_create": to_create,
        "skipped": skipped,
        "already_has_user": already,
        "totals": totals,
    }


async def apply_plan(db, plan: dict) -> dict:
    """Aplica (grava) os users do plano. Retorna totals."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    errors: list[dict] = []
    for row in plan.get("to_create") or []:
        try:
            doc = {
                "id": str(uuid.uuid4()),
                "full_name": row["full_name"],
                "email": row["email"],
                "role": "aluno",
                "roles": ["aluno"],
                "status": "active",
                "avatar_url": None,
                "school_links": ([{"school_id": row["school_id"], "roles": ["aluno"]}]
                                 if row.get("school_id") else []),
                "mantenedora_id": row.get("mantenedora_id"),
                "student_id": row["student_id"],
                "password_hash": hash_password(row["password"]),
                "created_at": now,
                "must_change_password": True,  # boa prática: obrigar troca no 1º acesso
            }
            await db.users.insert_one(doc)
            inserted += 1
        except Exception as e:  # noqa: BLE001
            errors.append({"student_id": row.get("student_id"),
                           "email": row.get("email"), "error": str(e)})
    return {"inserted": inserted, "errors": errors}
