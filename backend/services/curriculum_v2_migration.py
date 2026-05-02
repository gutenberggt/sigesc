"""Migração idempotente para Modelo Curricular Multi-Camadas v2 (Feb 2026).

Executada no startup do backend e via endpoint admin. Garantias:
 1. Índices únicos criados (bncc_skills.codigo_bncc; curriculum_adaptations
    compostos por mantenedora + component + ano + bimestre + código).
 2. Componentes existentes recebem `escopo` baseado em `fonte`.
 3. Cada `curriculum_skills` (legado) gera:
     - 1 `bncc_skills` se `codigo` bater com padrão BNCC (EI|EF|EM + ano + comp + nn)
     - 1 `curriculum_adaptations` ligada ao bncc_skill_id ou codigo_local
 4. Cada `learning_objects.skill_codigos` não migrado recebe `adaptation_ids`
    preenchidos (quando existe adaptation com o código correspondente).

Rodar 2x não duplica. Usa IDs determinísticos por sha1.
"""
from __future__ import annotations

import re
import hashlib
from datetime import datetime, timezone
from typing import Optional

BNCC_CODE_RE = re.compile(r'^(EI|EF|EM)(\d{2})([A-Z]{2})(\d{2}[A-Z]?)$')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_id(prefix: str, *parts) -> str:
    raw = "::".join(str(p) for p in parts)
    h = hashlib.sha1(raw.encode()).hexdigest()[:24]
    return f"{prefix}_{h}"


# aliases internos (compat)
_hash_id = hash_id


def etapa_bncc_from_codigo(codigo: str, ano: Optional[int]) -> str:
    """EI|EF_AI|EF_AF|EJA|EM. Usa prefixo + ano."""
    m = BNCC_CODE_RE.match(codigo or '')
    if not m:
        if ano and 1 <= ano <= 5:
            return 'EF_AI'
        if ano and 6 <= ano <= 9:
            return 'EF_AF'
        return 'EF_AI'
    prefix = m.group(1)
    if prefix == 'EI':
        return 'EI'
    if prefix == 'EM':
        return 'EM'
    # EF - decide AI vs AF
    if ano and ano >= 6:
        return 'EF_AF'
    return 'EF_AI'


def escopo_from_fonte(fonte: Optional[str]) -> str:
    if fonte in ('BNCC', 'BNCC_COMPUTACAO'):
        return 'NACIONAL'
    return 'MUNICIPAL'


# aliases internos (compat)
_escopo_from_fonte = escopo_from_fonte
_etapa_bncc_from_codigo = etapa_bncc_from_codigo


AREA_BY_COMPONENT = {
    'LP': 'Linguagens', 'AR': 'Linguagens', 'EF': 'Linguagens', 'LI': 'Linguagens',
    'MA': 'Matemática',
    'CI': 'Ciências da Natureza',
    'GE': 'Ciências Humanas', 'HI': 'Ciências Humanas', 'ER': 'Ciências Humanas',
    'CO': 'Computação',
    'EA': 'Ciências Humanas',
}


async def ensure_indexes(db) -> dict:
    """Cria índices únicos e compostos. Idempotente (Mongo ignora duplicados)."""
    await db.bncc_skills.create_index("codigo_bncc", unique=True)
    await db.bncc_skills.create_index([("etapa", 1), ("ano", 1), ("componente_codigo", 1)])
    await db.curriculum_adaptations.create_index(
        [("mantenedora_id", 1), ("component_id", 1), ("ano", 1), ("bimestre", 1)]
    )
    await db.curriculum_adaptations.create_index("bncc_skill_id")
    await db.curriculum_adaptations.create_index("codigo_local")
    # Unique upsert-key
    await db.curriculum_adaptations.create_index(
        [("mantenedora_id", 1), ("component_id", 1),
         ("bncc_skill_id", 1), ("codigo_local", 1),
         ("ano", 1), ("bimestre", 1)],
        unique=True, name="uq_adaptation_slot",
    )
    return {"indexes_ok": True}


async def backfill_components_escopo(db) -> dict:
    """Adiciona campo `escopo` a componentes pré-v2."""
    n = 0
    cursor = db.curriculum_components.find({"escopo": {"$exists": False}}, {"_id": 0, "id": 1, "fonte": 1})
    async for c in cursor:
        escopo = _escopo_from_fonte(c.get('fonte'))
        await db.curriculum_components.update_one(
            {"id": c['id']},
            {"$set": {"escopo": escopo, "area_conhecimento": None}}
        )
        n += 1
    return {"components_backfilled": n}


async def migrate_legacy_skills_to_v2(db) -> dict:
    """Converte cada curriculum_skills em bncc_skill (se BNCC canônico) + adaptation.

    Regras:
     - codigo bate BNCC_CODE_RE → cria/obtém bncc_skill; cria adaptation FK.
     - codigo não-BNCC → cria adaptation MUNICIPAL com codigo_local.
    """
    stats = {
        "bncc_inserted": 0, "bncc_existed": 0,
        "adapt_inserted": 0, "adapt_existed": 0,
        "components_created": 0,
    }

    # Caminho do mantenedora padrão — "default" quando o tenant ainda não se
    # preocupou com multi-rede. Para DCM_FA municipal, usa "floresta_araguaia".
    DEFAULT_MANTENEDORA = None  # NACIONAL (nulls no v2)
    DCM_FA_MANTENEDORA = "floresta_araguaia"  # Para dados DCM_FA

    cursor = db.curriculum_skills.find({}, {"_id": 0})
    async for sk in cursor:
        codigo = sk.get('codigo') or ''
        fonte = sk.get('fonte') or 'BNCC'
        ano = sk.get('ano')
        componente_codigo = sk.get('componente_codigo')

        is_bncc = bool(BNCC_CODE_RE.match(codigo))
        bncc_id: Optional[str] = None

        if is_bncc:
            # Upsert bncc_skill
            existing = await db.bncc_skills.find_one({"codigo_bncc": codigo}, {"_id": 0, "id": 1})
            if existing:
                bncc_id = existing['id']
                stats["bncc_existed"] += 1
            else:
                m = BNCC_CODE_RE.match(codigo)
                comp_from_code = m.group(3) if m else componente_codigo
                etapa = _etapa_bncc_from_codigo(codigo, ano)
                bncc_id = _hash_id("bncc", codigo)
                doc = {
                    "id": bncc_id,
                    "codigo_bncc": codigo,
                    "descricao_bncc": sk.get('descricao') or '',
                    "eixo": sk.get('unidade_tematica'),
                    "etapa": etapa,
                    "ano": ano,
                    "ano_range": None,
                    "area_conhecimento": AREA_BY_COMPONENT.get(comp_from_code or ''),
                    "componente_codigo": comp_from_code,
                    "ativo": True,
                    "created_at": _now(),
                    "updated_at": None,
                }
                try:
                    await db.bncc_skills.insert_one(doc)
                    stats["bncc_inserted"] += 1
                except Exception:
                    # race: outra inserção entrou primeiro
                    existing = await db.bncc_skills.find_one({"codigo_bncc": codigo}, {"_id": 0, "id": 1})
                    if existing:
                        bncc_id = existing['id']
                        stats["bncc_existed"] += 1

        # Garantir componente v2 (escopo + area)
        component_id = sk.get('componente_id')
        if not component_id:
            # fallback: componente por código+etapa
            comp_codigo_up = (componente_codigo or 'XX').upper()
            etapa_old = 'anos_finais' if (ano and ano >= 6) else 'anos_iniciais'
            component_id = _hash_id("comp", f"{comp_codigo_up}-{etapa_old}-{fonte}")
            await db.curriculum_components.update_one(
                {"id": component_id},
                {"$setOnInsert": {
                    "id": component_id,
                    "codigo": comp_codigo_up,
                    "nome": comp_codigo_up,
                    "etapa": etapa_old,
                    "fonte": fonte,
                    "escopo": _escopo_from_fonte(fonte),
                    "area_conhecimento": AREA_BY_COMPONENT.get(comp_codigo_up),
                    "ativo": True,
                    "created_at": _now(),
                }},
                upsert=True,
            )
            stats["components_created"] += 1

        # Determinar mantenedora_id da adaptation
        mant_id = DCM_FA_MANTENEDORA if fonte == 'DCM_FA' else DEFAULT_MANTENEDORA

        # Upsert da adaptation (unique por slot)
        filt = {
            "mantenedora_id": mant_id,
            "component_id": component_id,
            "bncc_skill_id": bncc_id,
            "codigo_local": None if is_bncc else codigo,
            "ano": ano or 0,
            "bimestre": sk.get('bimestre'),
        }
        existing_a = await db.curriculum_adaptations.find_one(filt, {"_id": 0, "id": 1})
        if existing_a:
            stats["adapt_existed"] += 1
            continue

        fonte_a = 'DCM_FA' if fonte == 'DCM_FA' else (
            'BNCC_COMPUTACAO' if fonte == 'BNCC_COMPUTACAO' else 'MUNICIPAL'
        )
        adapt_id = _hash_id("adapt", codigo, mant_id or "_", ano or 0, sk.get('bimestre') or 0)
        adapt_doc = {
            "id": adapt_id,
            "mantenedora_id": mant_id,
            "component_id": component_id,
            "bncc_skill_id": bncc_id,
            "codigo_local": None if is_bncc else codigo,
            "descricao_local": None if is_bncc else sk.get('descricao'),
            "eixo_local": sk.get('unidade_tematica'),
            "objeto_conhecimento": sk.get('objeto_conhecimento'),
            "ano": ano or 0,
            "bimestre": sk.get('bimestre'),
            "ordem_sequencia": 0,
            "fonte": fonte_a,
            "ativo": True,
            "created_at": _now(),
            "updated_at": None,
        }
        try:
            await db.curriculum_adaptations.insert_one(adapt_doc)
            stats["adapt_inserted"] += 1
        except Exception:
            stats["adapt_existed"] += 1
    return stats


async def migrate_learning_objects_skill_codigos(db) -> dict:
    """Para cada learning_object com skill_codigos mas sem adaptation_ids,
    tenta localizar adaptations correspondentes pelos códigos.
    """
    stats = {"migrated": 0, "partial_hits": 0, "no_match": 0, "scanned": 0}
    # Constrói dict codigo → adaptation_id (pega uma adaptation por código, preferindo NACIONAL)
    code_to_adapt: dict = {}
    cursor = db.curriculum_adaptations.find(
        {"ativo": True},
        {"_id": 0, "id": 1, "bncc_skill_id": 1, "codigo_local": 1, "mantenedora_id": 1}
    )
    # Carrega bncc id → codigo
    bncc_id_to_code: dict = {}
    async for b in db.bncc_skills.find({}, {"_id": 0, "id": 1, "codigo_bncc": 1}):
        bncc_id_to_code[b['id']] = b['codigo_bncc']
    async for a in cursor:
        codes = set()
        if a.get('bncc_skill_id') and a['bncc_skill_id'] in bncc_id_to_code:
            codes.add(bncc_id_to_code[a['bncc_skill_id']])
        if a.get('codigo_local'):
            codes.add(a['codigo_local'])
        for c in codes:
            # Prefere manter o primeiro (NACIONAL/sem mantenedora) se houver empate
            if c not in code_to_adapt or a.get('mantenedora_id') is None:
                code_to_adapt[c] = a['id']

    cursor = db.learning_objects.find(
        {"skill_codigos": {"$exists": True, "$ne": []},
         "$or": [{"adaptation_ids": {"$exists": False}}, {"adaptation_ids": []}]},
        {"_id": 0, "id": 1, "skill_codigos": 1}
    )
    async for lo in cursor:
        stats["scanned"] += 1
        hits = [code_to_adapt[c] for c in (lo.get('skill_codigos') or []) if c in code_to_adapt]
        if not hits:
            stats["no_match"] += 1
            continue
        if len(hits) < len(lo.get('skill_codigos') or []):
            stats["partial_hits"] += 1
        await db.learning_objects.update_one(
            {"id": lo['id']},
            {"$set": {"adaptation_ids": list(dict.fromkeys(hits))[:3]}}
        )
        stats["migrated"] += 1
    return stats


async def run_full_migration(db) -> dict:
    """Entrada principal — roda todas as fases na ordem correta."""
    out: dict = {}
    out.update(await ensure_indexes(db))
    out.update(await backfill_components_escopo(db))
    out.update(await migrate_legacy_skills_to_v2(db))
    out.update(await migrate_learning_objects_skill_codigos(db))
    return out
