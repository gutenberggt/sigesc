"""
Feb 2026 — Diário AEE: garantir que TODOS os campos do Plano AEE são salvos
e recuperados corretamente para edição.

Bug original: vários campos do frontend (data_elaboracao, periodo_vigencia,
linha_base_*, indicadores_progresso, frequencia_revisao, criterios_ajuste,
combinados_professor_regente, adaptacoes_por_componente, escola_origem_nome,
carga_horaria_semanal como texto) eram silenciosamente descartados pelo
Pydantic com `extra="ignore"` porque não existiam em PlanoAEEBase. Resultado:
ao reabrir o plano para edição, os campos voltavam vazios.

Fix: campos adicionados ao PlanoAEEBase + PlanoAEEUpdate; carga_horaria_semanal
mudou de int para str (aceita "4 horas", "240 min", etc).
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

SUPER_CREDS = {
    "email": "gutenberg@sigesc.com",
    "password": os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007"),
}


@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=SUPER_CREDS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def setup_aee_data():
    """Cria student + professor AEE para usar nos testes."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async def setup():
        flo = await db.mantenedoras.find_one({}, {"_id": 0})
        flo_id = flo["id"]
        school = await db.schools.find_one({"mantenedora_id": flo_id}, {"_id": 0})
        school_id = school["id"]

        await db.students.delete_many({"full_name": {"$regex": "^TEST_AEE_ALUNO_PYTEST"}})
        await db.users.delete_many({"email": "test_aee_prof@pytest.com"})
        await db.planos_aee.delete_many({"criterio_elegibilidade": {"$regex": "^TEST_PYTEST"}})

        student_id = "test_aee_aluno_" + str(uuid.uuid4())[:8]
        student2_id = "test_aee_aluno2_" + str(uuid.uuid4())[:8]
        await db.students.insert_many([
            {
                "id": student_id, "full_name": "TEST_AEE_ALUNO_PYTEST_1",
                "school_id": school_id, "mantenedora_id": flo_id, "status": "active",
                "academic_year": 2026,
            },
            {
                "id": student2_id, "full_name": "TEST_AEE_ALUNO_PYTEST_2",
                "school_id": school_id, "mantenedora_id": flo_id, "status": "active",
                "academic_year": 2026,
            },
        ])

        prof_id = "test_aee_prof_" + str(uuid.uuid4())[:8]
        await db.users.insert_one({
            "id": prof_id, "email": "test_aee_prof@pytest.com",
            "full_name": "TEST_AEE_PROF", "role": "professor",
            "mantenedora_id": flo_id, "status": "active",
        })

        return {
            "student_id": student_id, "student2_id": student2_id,
            "school_id": school_id, "prof_id": prof_id, "flo_id": flo_id,
        }

    data = asyncio.get_event_loop().run_until_complete(setup())
    yield data

    async def teardown():
        await db.students.delete_many({"id": {"$in": [data["student_id"], data["student2_id"]]}})
        await db.users.delete_one({"id": data["prof_id"]})
        await db.planos_aee.delete_many({"student_id": {"$in": [data["student_id"], data["student2_id"]]}})

    asyncio.get_event_loop().run_until_complete(teardown())


def test_plano_aee_saves_and_returns_all_fields(super_token, setup_aee_data):
    """Cria um plano com TODOS os campos novos preenchidos, depois GET para garantir
    que TODOS persistiram (não foram descartados como antes do fix)."""
    d = setup_aee_data
    payload = {
        "student_id": d["student_id"],
        "school_id": d["school_id"],
        "academic_year": 2026,
        "professor_aee_id": d["prof_id"],
        "professor_aee_nome": "TEST_AEE_PROF",
        "publico_alvo": "transtorno_espectro_autista",
        "criterio_elegibilidade": "TEST_PYTEST_LAUDO",
        # Campos antigamente descartados (Feb 2026)
        "escola_origem_nome": "ESCOLA ORIGEM TESTE",
        "data_elaboracao": "2026-02-15",
        "periodo_vigencia": "1º Semestre 2026",
        "linha_base_situacao_atual": "Aluno apresenta dificuldades de comunicação verbal",
        "linha_base_potencialidades": "Boa memória visual, interesse por números",
        "linha_base_dificuldades": "Interação social, transições de atividade",
        "linha_base_comunicacao": "Comunica-se majoritariamente através de gestos",
        "indicadores_progresso": "Aumento gradual no número de turnos comunicativos",
        "frequencia_revisao": "bimestral",
        "criterios_ajuste": "Revisar a cada bimestre conforme NEE evolui",
        "combinados_professor_regente": "Sinalizar transições com 5 min de antecedência",
        "adaptacoes_por_componente": "Matemática: usar manipuláveis; Português: leitura partilhada",
        "carga_horaria_semanal": "4 horas",  # Texto livre (antes era int e perdia)
        "modalidade": "individual",
        "horario_inicio": "14:00",
        "horario_fim": "15:30",
        "dias_atendimento": ["segunda", "quarta"],
        "local_atendimento": "Sala de Recursos Multifuncionais",
        "barreiras": [
            {"tipo": "comunicacao", "descricao": "Linguagem verbal limitada", "estrategias": []},
        ],
        "objetivos": [
            {"descricao": "Ampliar repertório verbal", "prazo": "medio",
             "indicadores": [], "status": "nao_iniciado"},
        ],
        "recursos_acessibilidade": [
            {"tipo": "comunicacao_alternativa", "descricao": "Prancha CAA", "disponivel": True},
        ],
        "orientacoes_sala_comum": "Permitir tempo extra de resposta",
        "adequacoes_curriculares": "Avaliação em formato visual",
        "data_inicio": "15/02/2026",
        "data_revisao": "15/04/2026",
        "status": "ativo",
    }
    r = requests.post(
        f"{BASE_URL}/api/aee/planos",
        headers={"Authorization": f"Bearer {super_token}"},
        json=payload, timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    plano = r.json()
    plano_id = plano["id"]

    # GET deve retornar TODOS os campos preservados
    r = requests.get(
        f"{BASE_URL}/api/aee/planos/{plano_id}",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    got = r.json()

    # Campos novos (antes descartados) - cada um deve aparecer no GET
    novos_campos = [
        "escola_origem_nome", "data_elaboracao", "periodo_vigencia",
        "linha_base_situacao_atual", "linha_base_potencialidades",
        "linha_base_dificuldades", "linha_base_comunicacao",
        "indicadores_progresso", "frequencia_revisao", "criterios_ajuste",
        "combinados_professor_regente", "adaptacoes_por_componente",
        "carga_horaria_semanal",
    ]
    for campo in novos_campos:
        assert campo in got, f"Campo '{campo}' não foi retornado pelo GET"
        assert got[campo] not in (None, ""), (
            f"Campo '{campo}' veio vazio no GET (esperado: '{payload[campo]}'). "
            f"Provavelmente foi descartado no save."
        )

    # carga_horaria_semanal preserva o texto digitado (uppercase é regra do SIGESC)
    assert got["carga_horaria_semanal"].upper() == "4 HORAS"

    # PUT atualiza um dos campos novos
    update_payload = {
        "indicadores_progresso": "Indicadores ATUALIZADOS pelo pytest",
        "frequencia_revisao": "trimestral",
        "carga_horaria_semanal": "5 horas",
    }
    r = requests.put(
        f"{BASE_URL}/api/aee/planos/{plano_id}",
        headers={"Authorization": f"Bearer {super_token}"},
        json=update_payload, timeout=30,
    )
    assert r.status_code == 200, r.text

    # GET valida que update persistiu E os outros campos não foram apagados
    r = requests.get(
        f"{BASE_URL}/api/aee/planos/{plano_id}",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    got2 = r.json()
    assert got2["indicadores_progresso"].upper() == "INDICADORES ATUALIZADOS PELO PYTEST"
    assert got2["frequencia_revisao"] == "trimestral"  # Literal mantém minúsculo
    assert got2["carga_horaria_semanal"].upper() == "5 HORAS"
    # Não-atualizados continuam preservados
    assert "DIFICULDADES" in got2["linha_base_situacao_atual"].upper() or \
           "COMUNICA" in got2["linha_base_situacao_atual"].upper()
    assert "TRANSI" in got2["combinados_professor_regente"].upper()


def test_atendimento_aee_full_save_and_edit(super_token, setup_aee_data):
    """Atendimento AEE: criar com todos os campos, editar, validar persistência."""
    d = setup_aee_data
    # Cria plano para vincular (usa student2 para evitar conflito com test_plano_aee)
    plano_payload = {
        "student_id": d["student2_id"], "school_id": d["school_id"],
        "academic_year": 2026, "professor_aee_id": d["prof_id"],
        "publico_alvo": "deficiencia_intelectual",
        "criterio_elegibilidade": "TEST_PYTEST_ATEND_LAUDO",
        "status": "ativo",
    }
    r = requests.post(
        f"{BASE_URL}/api/aee/planos",
        headers={"Authorization": f"Bearer {super_token}"},
        json=plano_payload, timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    plano_id = r.json()["id"]

    atend_payload = {
        "plano_aee_id": plano_id,
        "student_id": d["student2_id"],
        "school_id": d["school_id"],
        "academic_year": 2026,
        "data": "20/02/2026",
        "horario_inicio": "14:00",
        "horario_fim": "15:00",
        "presente": True,
        "objetivo_trabalhado": "Ampliar repertório de matemática",
        "atividade_realizada": "Manipulação de blocos lógicos com sequência",
        "recursos_utilizados": ["blocos lógicos", "tablet com app de contagem"],
        "nivel_apoio": "apoio_moderado",
        "resposta_estudante": "Concluiu sequências de 3 com auxílio verbal",
        "evidencias": "Foto de 3 sequências completas no caderno",
        "encaminhamento_proximo": "Aumentar para sequência de 4",
        "orientacao_sala_comum": "Permitir uso de blocos durante avaliação de matemática",
        "professor_aee_id": d["prof_id"],
        "professor_aee_nome": "TEST_AEE_PROF",
        "observacoes": "Muito engajado hoje",
    }
    r = requests.post(
        f"{BASE_URL}/api/aee/atendimentos",
        headers={"Authorization": f"Bearer {super_token}"},
        json=atend_payload, timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    atend = r.json()
    atend_id = atend["id"]
    # Duração calculada automaticamente (60 min)
    assert atend.get("duracao_minutos") == 60, f"duracao_minutos incorreta: {atend}"

    # PUT atualiza alguns campos
    update = {
        "atividade_realizada": "Atividade ATUALIZADA pelo pytest",
        "horario_fim": "15:30",
        "resposta_estudante": "Resposta ATUALIZADA",
        "nivel_apoio": "apoio_minimo",
    }
    r = requests.put(
        f"{BASE_URL}/api/aee/atendimentos/{atend_id}",
        headers={"Authorization": f"Bearer {super_token}"},
        json=update, timeout=30,
    )
    assert r.status_code == 200, r.text
    upd = r.json()
    assert "ATUALIZADA" in upd["atividade_realizada"].upper()
    assert "ATUALIZADA" in upd["resposta_estudante"].upper()
    assert upd["nivel_apoio"] == "apoio_minimo"
    # Duração recalculada (14:00 → 15:30 = 90 min)
    assert upd.get("duracao_minutos") == 90, f"duracao_minutos não recalculada: {upd}"
    # Campos não atualizados preservados (em uppercase)
    assert "MATEMÁTICA" in upd["objetivo_trabalhado"] or "MATEMA" in upd["objetivo_trabalhado"]
    assert upd["evidencias"] is not None
    assert upd["recursos_utilizados"] is not None
    assert len(upd["recursos_utilizados"]) == 2
