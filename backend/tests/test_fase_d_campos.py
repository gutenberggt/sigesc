"""Valida Fase D: modelo aceita novos campos, Dossiê renderiza e SSoT permanece estável."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SchoolCreate, SchoolUpdate
from services import ctue_conformity_service as ctue
from pdf.dossie_institucional import generate_dossie_pdf

NEW_FIELDS = {
    "area_terreno_m2": 1200.5, "area_construida_m2": 640.0, "ano_construcao": 1998,
    "regime_ocupacao": "Próprio", "predio_compartilhado": True,
    "vias_acessiveis": True, "dependencias_acessiveis": False,
    "agua_potavel": True, "certificado_potabilidade": False,
    "tipo_esgotamento": "Rede coletora", "tipo_destinacao_lixo": "Coleta periódica",
    "avcb_bombeiros": True, "necessita_reforma": True, "itens_criticos": "Telhado com infiltração",
    "alvara_funcionamento": True, "licenca_sanitaria": False, "habite_se": True,
}

# 1. Modelo aceita novos campos
sc = SchoolCreate(name="Teste Fase D", **NEW_FIELDS)
d = sc.model_dump()
for k, v in NEW_FIELDS.items():
    assert d[k] == v, f"SchoolCreate perdeu {k}: {d.get(k)} != {v}"
su = SchoolUpdate(**NEW_FIELDS).model_dump(exclude_unset=True)
for k, v in NEW_FIELDS.items():
    assert su[k] == v, f"SchoolUpdate perdeu {k}"
print("OK 1: SchoolCreate/SchoolUpdate aceitam os 17 campos Fase D")

# 2. SSoT estável: conformidade/completude iguais com e sem novos campos
base_school = {
    "name": "Escola X", "inep_code": "12345678", "situacao_funcionamento": "Em atividade",
    "zona_localizacao": "urbana", "abastecimento_agua": "Rede pública", "energia_eletrica": "Rede pública",
    "saneamento": "Rede pública", "possui_rampas": True, "banheiros_acessiveis": 2,
    "qtd_extintores": 3, "plano_evacuacao": True, "brigada_incendio": True,
    "numero_salas_aula": 8, "capacidade_total_alunos": 200, "numero_banheiros": 4,
    "estado_conservacao": "bom", "possui_internet": True, "gestor_principal": "Fulano",
    "dependencia_administrativa": "Municipal",
}
r_before = ctue.evaluate(base_school, profile="default")
school_with = {**base_school, **NEW_FIELDS}
r_after = ctue.evaluate(school_with, profile="default")
assert r_before["conformidade_geral"] == r_after["conformidade_geral"], \
    f"Conformidade mudou: {r_before['conformidade_geral']} -> {r_after['conformidade_geral']}"
assert r_before["completude_geral"] == r_after["completude_geral"], \
    f"Completude mudou: {r_before['completude_geral']} -> {r_after['completude_geral']}"
assert r_before["selo_geral"] == r_after["selo_geral"]
print(f"OK 2: SSoT estável — conf={r_after['conformidade_geral']}% comp={r_after['completude_geral']}% (inalterado)")

# 3. Dossiê renderiza com novos campos
pdf = generate_dossie_pdf(school_with, r_after)
assert isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF" and len(pdf) > 3000
print(f"OK 3: Dossiê PDF gerado ({len(pdf)} bytes) com campos Fase D")

print("\nTODOS OS TESTES PASSARAM ✅")
