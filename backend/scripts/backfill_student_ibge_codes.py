"""Backfill seguro dos códigos IBGE no endereço dos estudantes.

O script usa a Unidade Mantenedora do tenant como fonte apenas quando o endereço
já existente é compatível com a UF/Município da mantenedora. Códigos já
informados nunca são sobrescritos.

Uso:
    python3 -m scripts.backfill_student_ibge_codes          # dry-run
    python3 -m scripts.backfill_student_ibge_codes --apply  # aplica as escritas

Opções úteis:
    --tenant <mantenedora_id>  restringe a uma mantenedora
    --limit 100                limita a quantidade de estudantes analisados
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import unicodedata

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('/app/backend/.env')


def _digits(value: object, length: int) -> str:
    digits = re.sub(r'\D', '', str(value or ''))[:length]
    return digits if len(digits) == length else ''


def _text(value: object) -> str:
    normalized = unicodedata.normalize('NFD', str(value or ''))
    normalized = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    return ' '.join(normalized.strip().lower().split())


def _same_or_blank(current: object, expected: object) -> bool:
    current_text = _text(current)
    expected_text = _text(expected)
    return not current_text or bool(expected_text and current_text == expected_text)


def _structured_address(student: dict) -> dict | None:
    """Normaliza endereço vazio e rejeita formatos legados não estruturados.

    Endereços ausentes ou valores vazios continuam equivalentes a um objeto vazio,
    preservando o comportamento anterior. Strings/listas/objetos não vazios são
    considerados legados e não são interpretados automaticamente.
    """
    address = student.get('address')
    if not address:
        return {}
    if isinstance(address, dict):
        return address
    return None


def build_student_ibge_patch(student: dict, mantenedora: dict) -> dict:
    """Retorna somente os campos IBGE ausentes que podem ser preenchidos com segurança."""
    address = _structured_address(student)
    if address is None:
        return {}

    state_matches = _same_or_blank(address.get('state'), mantenedora.get('estado'))
    city_matches = _same_or_blank(address.get('city'), mantenedora.get('municipio'))

    current_state_code = _digits(address.get('state_ibge_code'), 2)
    current_city_code = _digits(address.get('city_ibge_code'), 7)
    mantenedora_state_code = _digits(mantenedora.get('codigo_ibge_uf'), 2)
    mantenedora_city_code = _digits(mantenedora.get('codigo_ibge_municipio'), 7)

    if not mantenedora_state_code and mantenedora_city_code:
        mantenedora_state_code = mantenedora_city_code[:2]

    patch = {}
    if not current_state_code and mantenedora_state_code and state_matches:
        patch['address.state_ibge_code'] = mantenedora_state_code
    if (
        not current_city_code
        and mantenedora_city_code
        and state_matches
        and city_matches
    ):
        patch['address.city_ibge_code'] = mantenedora_city_code

    return patch


async def run(*, apply: bool, tenant: str | None, limit: int | None) -> None:
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]

    mantenedora_query = {'id': tenant} if tenant else {}
    mantenedoras = await db.mantenedoras.find(mantenedora_query, {'_id': 0}).to_list(1000)
    mantenedoras_by_id = {item.get('id'): item for item in mantenedoras if item.get('id')}

    if tenant and tenant not in mantenedoras_by_id:
        raise SystemExit(f'Mantenedora não encontrada: {tenant}')

    all_mantenedoras = mantenedoras
    if tenant:
        all_mantenedoras = [mantenedoras_by_id[tenant]]
    fallback_mid = all_mantenedoras[0]['id'] if len(all_mantenedoras) == 1 else None

    schools_cursor = db.schools.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1})
    schools = await schools_cursor.to_list(10000)
    school_to_mid = {item.get('id'): item.get('mantenedora_id') for item in schools if item.get('id')}

    missing_query = {
        '$or': [
            {'address.state_ibge_code': {'$exists': False}},
            {'address.state_ibge_code': None},
            {'address.state_ibge_code': ''},
            {'address.city_ibge_code': {'$exists': False}},
            {'address.city_ibge_code': None},
            {'address.city_ibge_code': ''},
        ]
    }
    if tenant:
        missing_query['mantenedora_id'] = tenant

    cursor = db.students.find(
        missing_query,
        {
            '_id': 1,
            'id': 1,
            'full_name': 1,
            'mantenedora_id': 1,
            'school_id': 1,
            'address': 1,
        },
    )
    if limit:
        cursor = cursor.limit(limit)

    scanned = 0
    eligible = 0
    updated = 0
    skipped_no_tenant = 0
    skipped_no_config = 0
    skipped_incompatible = 0
    skipped_legacy_address = 0

    async for student in cursor:
        scanned += 1
        mid = (
            student.get('mantenedora_id')
            or school_to_mid.get(student.get('school_id'))
            or fallback_mid
        )
        if not mid:
            skipped_no_tenant += 1
            continue

        mantenedora = mantenedoras_by_id.get(mid)
        if not mantenedora:
            # Quando não há filtro por tenant, a lista inicial contém todas as mantenedoras.
            mantenedora = await db.mantenedoras.find_one({'id': mid}, {'_id': 0})
            if mantenedora:
                mantenedoras_by_id[mid] = mantenedora
        if not mantenedora:
            skipped_no_config += 1
            continue

        if _structured_address(student) is None:
            skipped_legacy_address += 1
            continue

        patch = build_student_ibge_patch(student, mantenedora)
        if not patch:
            skipped_incompatible += 1
            continue

        eligible += 1
        if apply:
            result = await db.students.update_one({'_id': student['_id']}, {'$set': patch})
            updated += result.modified_count

    mode = 'APLICADO' if apply else 'DRY-RUN'
    print(f'\n{mode} — Backfill IBGE dos estudantes')
    print(f'Analisados: {scanned}')
    print(f'Elegíveis para preenchimento: {eligible}')
    print(f'Atualizados: {updated if apply else 0}')
    print(f'Sem tenant identificável: {skipped_no_tenant}')
    print(f'Sem configuração de mantenedora: {skipped_no_config}')
    print(f'Endereço legado não estruturado: {skipped_legacy_address}')
    print(f'Ignorados por incompatibilidade ou ausência de código-fonte: {skipped_incompatible}')
    if not apply and eligible:
        print('\nNenhuma escrita foi feita. Execute novamente com --apply para persistir.')

    client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backfill seguro de códigos IBGE dos estudantes')
    parser.add_argument('--apply', action='store_true', help='persiste as alterações; sem esta opção é dry-run')
    parser.add_argument('--tenant', help='restringe a execução a uma mantenedora_id')
    parser.add_argument('--limit', type=int, help='limita a quantidade de estudantes analisados')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    asyncio.run(run(apply=args.apply, tenant=args.tenant, limit=args.limit))
