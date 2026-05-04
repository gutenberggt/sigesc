"""
Script de Normalização Reversa — REVERTE o efeito do antigo migrate_uppercase.py
================================================================================

Contexto (Mai/2026):
    O script migrate_uppercase.py foi rodado em produção e converteu nomes para
    CAIXA ALTA. Combinado com o CSS global `text-transform: uppercase` e o
    helper backend `format_data_uppercase()`, isso corrompeu a capitalização e
    acentuação dos nomes próprios. Após remover essas três fontes, este script
    repõe os nomes com capitalização correta.

Política (acordada com o proprietário):
    - Apenas CAMPOS NOMINAIS (nome, full_name, principal_name, mother_name, …).
      NÃO toca em descrições, observações, conteúdos ou planos AEE.
    - AEE: NÃO migrar. Dados antigos do AEE permanecem como estão.
    - Backup automático antes da migração: cria coleção
      `backup_<colecao>_<timestamp>` por dump completo via $out.
    - Adiciona campos auxiliares para busca:
        * `nome_normalizado`  (lowercase preservando acentos)
        * `nome_busca`        (lowercase + sem acentos — para busca
                               case/accent-insensitive)
    - Marca `nome_migrado: true` para rastreabilidade.
    - Dry-run por padrão: --apply para escrever de fato.
    - bulkWrite em batches de 1000 (performance).

Uso:
    # Relatório sem alterar nada (recomendado primeiro):
    python scripts/normalize_names_back.py --dry-run

    # Migração real (após revisar o relatório):
    python scripts/normalize_names_back.py --apply

    # Restringir a uma coleção:
    python scripts/normalize_names_back.py --apply --collection students

    # Pular backup (NÃO recomendado — só para reruns idempotentes):
    python scripts/normalize_names_back.py --apply --skip-backup
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

load_dotenv()

# ============================================================
# CONFIG: campos nominais por coleção (POLÍTICA RESTRITIVA)
# ============================================================
# Apenas campos que representam NOMES PRÓPRIOS de pessoas/entidades.
# NÃO incluir descrições, observações, planos, conteúdos.
NAME_FIELDS_BY_COLLECTION: Dict[str, List[str]] = {
    "students": [
        "full_name",
        "father_name",
        "mother_name",
        "guardian_name",
    ],
    "staff": [
        "full_name",
        "marital_status_spouse_name",
    ],
    "schools": [
        "name",
        "principal_name",
        "secretary_name",
        "coordinator_name",
    ],
    "classes": [
        "name",
    ],
    "courses": [
        "name",
    ],
    "users": [
        "full_name",
    ],
    "mantenedoras": [
        "nome",
    ],
}

# Campo "primário" (canônico) por coleção — usado para gerar
# `nome_normalizado` e `nome_busca`. None = pular.
PRIMARY_NAME_FIELD: Dict[str, Optional[str]] = {
    "students": "full_name",
    "staff": "full_name",
    "schools": "name",
    "classes": "name",
    "courses": "name",
    "users": "full_name",
    "mantenedoras": "nome",
}

# Preposições e conectivos que ficam minúsculos no meio do nome.
LOWER_PARTICLES = {"da", "de", "di", "do", "du", "das", "dos", "e", "em", "y"}

# Siglas educacionais e governamentais que devem permanecer em CAIXA ALTA.
# Aplicado token-a-token: se a palavra ORIGINAL estava toda em UPPER e é
# uma destas, mantém upper. Senão, capitaliza normalmente.
KNOWN_ACRONYMS = {
    "AEE", "EJA", "BNCC", "ENEM", "INEP", "MEC", "PNE", "PNAE", "PCD",
    "TGD", "TEA", "TDAH", "EMEIEF", "EMEF", "EMEI", "EJEM",
    "FUNDEB", "FUNDEF", "ABNT", "OAB", "USP", "UFPA", "ETI",
    "PMPI", "PME", "PNE", "SEMED", "SEDUC", "MEC", "INEP",
    "QA", "II", "III", "IV", "VI", "VII", "VIII", "IX",
    "CNPJ", "CPF", "RG", "NIS", "PIS", "SUS", "CEP",
}

# Limite por batch
BATCH_SIZE = 1000


# ============================================================
# HELPERS DE NORMALIZAÇÃO
# ============================================================
def strip_accents(text: str) -> str:
    """Remove acentos preservando o caractere base. NFD + filtro Mn."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def title_case_name(raw: str) -> str:
    """Capitaliza um nome próprio com regras BR.

    Regras:
      - Quebra por espaço E por hífen (preserva o hífen).
      - Cada palavra: primeira letra maiúscula, demais minúsculas.
      - Preposições (da, de, do, etc.) ficam minúsculas — exceto se forem a
        primeira palavra do nome inteiro.
      - Apóstrofos: D'Água → D'Água (capitaliza letra após apóstrofo).
      - Siglas conhecidas (AEE, BNCC, EJA, ...) permanecem em CAIXA ALTA
        quando estavam originalmente em CAIXA ALTA.
    """
    if not raw or not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s:
        return s

    def cap_token(token_orig: str, is_first: bool) -> str:
        if not token_orig:
            return token_orig
        # Hífen: trata cada lado separadamente.
        if "-" in token_orig:
            return "-".join(
                cap_token(p, is_first and i == 0)
                for i, p in enumerate(token_orig.split("-"))
            )
        # Apóstrofo: capitaliza letra após apóstrofo (D'Água, O'Brien).
        if "'" in token_orig:
            return "'".join(
                cap_token(p, is_first and i == 0)
                for i, p in enumerate(token_orig.split("'"))
            )

        token_upper = token_orig.upper()
        # Sigla conhecida → mantém UPPER (preserva AEE, BNCC, etc.)
        if token_upper in KNOWN_ACRONYMS and token_orig.isupper():
            return token_upper

        word_lower = token_orig.lower()
        if not is_first and word_lower in LOWER_PARTICLES:
            return word_lower
        # Capitalização padrão: primeira letra upper, restante lower.
        return word_lower[:1].upper() + word_lower[1:]

    # Split preservando múltiplos espaços. Para nomes de pessoas, single-space
    # é o esperado; aqui colapsamos espaços extras.
    tokens = [w for w in re.split(r"\s+", s) if w]
    cap_tokens = [cap_token(w, i == 0) for i, w in enumerate(tokens)]
    return " ".join(cap_tokens)


def normalize_search(text: str) -> str:
    """Normaliza para busca: lowercase + sem acentos + espaços colapsados."""
    if not text:
        return text
    cleaned = strip_accents(text).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_lower(text: str) -> str:
    """Normalizado para ordenação (lowercase preservando acentos)."""
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip().lower()


# ============================================================
# DETECÇÃO: precisa migrar?
# ============================================================
def is_likely_uppercase(value: str) -> bool:
    """Retorna True se a string parece estar em CAIXA ALTA forçada.

    Heurística: tem pelo menos 2 letras E todas as letras estão em
    maiúsculas (ignora acentos). Strings como "1º ANO" também caem aqui
    (queremos converter para "1º Ano").
    """
    if not value or not isinstance(value, str):
        return False
    letters = [c for c in strip_accents(value) if c.isalpha()]
    if len(letters) < 2:
        return False
    return all(c.isupper() for c in letters)


# ============================================================
# BACKUP
# ============================================================
async def backup_collection(db, col_name: str, timestamp: str) -> str:
    """Cria backup_<col>_<timestamp> via $out (dump completo). Retorna nome."""
    backup_name = f"backup_{col_name}_{timestamp}"
    pipeline = [{"$match": {}}, {"$out": backup_name}]
    await db[col_name].aggregate(pipeline).to_list(length=None)
    count = await db[backup_name].count_documents({})
    print(f"   📦 Backup: {backup_name} ({count} docs)")
    return backup_name


# ============================================================
# CORE
# ============================================================
async def process_collection(
    db,
    col_name: str,
    fields: List[str],
    primary_field: Optional[str],
    apply: bool,
) -> Dict[str, int]:
    """Processa uma coleção: lê docs, calcula update, faz bulkWrite por batches."""
    collection = db[col_name]
    total = await collection.count_documents({})
    print(f"\n📂 {col_name}: {total} documentos · campos: {fields}")
    if total == 0:
        return {"scanned": 0, "to_update": 0, "updated": 0, "skipped": 0}

    # Projeção: _id + campos nominais + campo primário (já incluído nos fields)
    projection = {"_id": 1}
    for f in fields:
        projection[f] = 1
    if primary_field and primary_field not in projection:
        projection[primary_field] = 1

    cursor = collection.find({}, projection)

    scanned = 0
    to_update = 0
    skipped = 0
    updated = 0
    bulk_ops: List[UpdateOne] = []
    samples_shown = 0

    async for doc in cursor:
        scanned += 1
        new_set: Dict[str, Any] = {}

        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            if not is_likely_uppercase(v):
                # Já está em capitalização razoável — pula esse campo.
                continue
            new_v = title_case_name(v)
            if new_v != v:
                new_set[f] = new_v

        # Primary: sempre que o campo primário mudou OU não existir,
        # recomputa nome_normalizado + nome_busca a partir do valor final.
        if primary_field:
            current_primary = new_set.get(primary_field, doc.get(primary_field))
            if isinstance(current_primary, str) and current_primary.strip():
                new_norm = normalize_lower(current_primary)
                new_busca = normalize_search(current_primary)
                if doc.get("nome_normalizado") != new_norm:
                    new_set["nome_normalizado"] = new_norm
                if doc.get("nome_busca") != new_busca:
                    new_set["nome_busca"] = new_busca

        if not new_set:
            skipped += 1
            continue

        new_set["nome_migrado"] = True
        new_set["nome_migrado_at"] = datetime.now(timezone.utc).isoformat()
        to_update += 1

        if samples_shown < 3:
            sample_field = primary_field or fields[0]
            old_v = doc.get(sample_field, "")
            new_v = new_set.get(sample_field, old_v)
            if old_v != new_v:
                print(f"   • {old_v!r} → {new_v!r}")
                samples_shown += 1

        if apply:
            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": new_set}))
            if len(bulk_ops) >= BATCH_SIZE:
                result = await collection.bulk_write(bulk_ops, ordered=False)
                updated += result.modified_count
                bulk_ops.clear()

    if apply and bulk_ops:
        result = await collection.bulk_write(bulk_ops, ordered=False)
        updated += result.modified_count
        bulk_ops.clear()

    if apply and primary_field:
        # Índice para busca eficiente. Nome de índice estável → idempotente.
        try:
            await collection.create_index(
                [("mantenedora_id", 1), ("nome_busca", 1)],
                name="ix_tenant_nome_busca",
                background=True,
            )
        except Exception as e:
            # Algumas coleções podem não ter mantenedora_id. Cai pra index simples.
            print(f"   ⚠️  Índice composto falhou ({e}); criando simples")
            await collection.create_index(
                [("nome_busca", 1)],
                name="ix_nome_busca",
                background=True,
            )

    print(
        f"   📊 scanned={scanned} · to_update={to_update} · "
        f"skipped(unchanged)={skipped} · "
        f"{'updated=' + str(updated) if apply else 'DRY-RUN — nada gravado'}"
    )
    return {
        "scanned": scanned,
        "to_update": to_update,
        "updated": updated,
        "skipped": skipped,
    }


# ============================================================
# CLI
# ============================================================
async def run(args: argparse.Namespace) -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL/DB_NAME não definidos no ambiente.")
        return 2

    apply = args.apply
    dry_run = not apply

    print("=" * 70)
    print("🔄 NORMALIZAÇÃO DE NOMES (reverter CAPS de migrate_uppercase.py)")
    print("=" * 70)
    print(f"DB: {db_name}")
    print(f"Modo: {'DRY-RUN (sem escrita)' if dry_run else 'APLICAR (escreve)'}")
    if args.collection:
        print(f"Coleção restrita: {args.collection}")
    print()

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    cols_to_run = (
        [args.collection]
        if args.collection
        else list(NAME_FIELDS_BY_COLLECTION.keys())
    )

    # Backup (somente se apply e não --skip-backup)
    if apply and not args.skip_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        print(f"🛟 BACKUP — timestamp {ts}")
        for col in cols_to_run:
            if col not in NAME_FIELDS_BY_COLLECTION:
                continue
            try:
                await backup_collection(db, col, ts)
            except Exception as e:
                print(f"   ❌ Falha no backup de {col}: {e}")
                print("      Abortando para preservar segurança.")
                return 3
        print()

    totals = {"scanned": 0, "to_update": 0, "updated": 0, "skipped": 0}
    for col in cols_to_run:
        if col not in NAME_FIELDS_BY_COLLECTION:
            print(f"⚠️  Coleção '{col}' não está na whitelist — ignorando.")
            continue
        fields = NAME_FIELDS_BY_COLLECTION[col]
        primary = PRIMARY_NAME_FIELD.get(col)
        try:
            stats = await process_collection(db, col, fields, primary, apply)
            for k, v in stats.items():
                totals[k] += v
        except Exception as e:
            print(f"   ❌ Erro em {col}: {e}")

    print()
    print("=" * 70)
    print("📈 RESUMO")
    print("=" * 70)
    print(f"  Total escaneados      : {totals['scanned']}")
    print(f"  Docs a atualizar      : {totals['to_update']}")
    print(f"  Docs sem mudança      : {totals['skipped']}")
    if apply:
        print(f"  Docs realmente escritos: {totals['updated']}")
        print()
        print("✅ Migração concluída. Backups disponíveis com prefixo `backup_<col>_*`.")
    else:
        print()
        print("ℹ️  DRY-RUN concluído. Nenhum dado foi modificado.")
        print("   Para aplicar: python scripts/normalize_names_back.py --apply")
    print("=" * 70)

    client.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Normaliza nomes de volta para capitalização correta."
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--apply",
        action="store_true",
        help="Aplica as mudanças (escreve no banco). Sem essa flag, dry-run.",
    )
    grp.add_argument(
        "--dry-run",
        action="store_true",
        help="(default) Apenas relatório, não escreve nada.",
    )
    p.add_argument(
        "--collection",
        type=str,
        help="Restringe a uma coleção (students, staff, schools, classes, courses, users, mantenedoras).",
    )
    p.add_argument(
        "--skip-backup",
        action="store_true",
        help="Pula backup automático (NÃO recomendado).",
    )
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
