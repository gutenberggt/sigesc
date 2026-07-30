"""Valida o Dossiê da Rede: dados SSoT consolidados + geração do PDF."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ctue_conformity_service as ctue
from pdf.dossie_rede import generate_network_dossie_pdf

schools = [
    {"id": "s1", "name": "Escola Central", "status": "active", "zona_localizacao": "urbana",
     "abastecimento_agua": "Rede pública", "energia_eletrica": "Rede pública", "saneamento": "Rede pública",
     "possui_rampas": True, "banheiros_acessiveis": 2, "possui_internet": True, "possui_biblioteca": True,
     "possui_lab_informatica": True, "possui_quadra": True, "possui_cozinha": True, "qtd_extintores": 4,
     "plano_evacuacao": True, "brigada_incendio": True, "numero_salas_aula": 12, "capacidade_total_alunos": 400,
     "numero_banheiros": 6, "estado_conservacao": "bom", "gestor_principal": "Ana", "dependencia_administrativa": "Municipal",
     "educacao_infantil": True, "fundamental_anos_iniciais": True, "updated_at": "2026-06-01T00:00:00+00:00",
     "alvara_funcionamento": True, "avcb_bombeiros": True,
     "obras": [{"tipo": "Reforma", "situacao": "Em execução"}, {"tipo": "Cercamento / Muro", "situacao": "Concluída"}],
     "documentos": [{"categoria": "Planta Baixa"}]},
    {"id": "s2", "name": "Escola Rural do Campo", "status": "active", "zona_localizacao": "rural",
     "abastecimento_agua": "Poço artesiano", "numero_salas_aula": 3, "capacidade_total_alunos": 90,
     "gestor_principal": "Beto", "dependencia_administrativa": "Municipal", "fundamental_anos_iniciais": True},
    {"id": "s3", "name": "Escola Sem Cadastro", "status": "inactive"},
]

data = ctue.build_network_dossie(schools, profile="mp")
assert data["executive"]["total"] == 3
assert len(data["ranking"]) == 3
assert data["ranking"][0]["conformidade"] >= data["ranking"][-1]["conformidade"], "ranking deve estar desc"
assert any(i["indicador"] == "Internet" for i in data["infraestrutura"])
assert data["obras"]["total_intervencoes"] == 2
assert any(d["documento"] == "AVCB (Corpo de Bombeiros)" for d in data["documentacao"])
assert data["diagnostico"]["pontos_fortes"] and data["diagnostico"]["fragilidades"]
print("OK dados:", "total", data["executive"]["total"],
      "| conf_media", data["executive"]["conformidade_media"],
      "| obras", data["obras"]["total_intervencoes"],
      "| prioridades", len(data["priorities"]),
      "| plano", len(data["plano_acao"]))

pdf = generate_network_dossie_pdf(data, {"nome": "SEMED Teste", "municipio": "Floresta do Araguaia"}, exercicio="2026")
assert isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF" and len(pdf) > 5000
print(f"OK PDF Dossiê da Rede gerado ({len(pdf)} bytes)")
print("\nTODOS OS TESTES PASSARAM ✅")
