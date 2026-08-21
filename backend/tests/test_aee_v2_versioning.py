"""Fase 2 — persistência sidecar, snapshots imutáveis e versionamento AEE v2."""

import asyncio
from copy import deepcopy
from pathlib import Path

import pytest
from pymongo.errors import DuplicateKeyError

from aee_v2.contracts import (
    AEEAccessibilityResource,
    AEEPAEE,
    AEEPEI,
    AEESupportAssessment,
    AEEStudyCase,
)
from aee_v2.repository import AEEV2Conflict, AEEV2Repository
from aee_v2.versioning import (
    activation_validation,
    bootstrap_documents,
    verify_snapshot_hash,
)


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self._limit = None

    def sort(self, keys):
        for key, direction in reversed(keys):
            self.docs.sort(key=lambda d: d.get(key, 0), reverse=direction < 0)
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length=None):
        n = self._limit or length
        return deepcopy(self.docs[:n] if n else self.docs)


class FakeCollection:
    def __init__(self, kind):
        self.kind = kind
        self.docs = []

    async def create_index(self, *args, **kwargs):
        return kwargs.get("name", "index")

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _project(doc, projection):
        result = deepcopy(doc)
        if not projection:
            return result
        includes = [k for k, v in projection.items() if v and k != "_id"]
        if includes:
            return {k: deepcopy(doc.get(k)) for k in includes if k in doc}
        for key, enabled in projection.items():
            if not enabled:
                result.pop(key, None)
        return result

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    async def insert_one(self, doc):
        if self.kind == "heads":
            if any(d.get("legacy_plano_id") == doc.get("legacy_plano_id") for d in self.docs):
                raise DuplicateKeyError("duplicate head")
        else:
            if any(d.get("id") == doc.get("id") for d in self.docs):
                raise DuplicateKeyError("duplicate snapshot id")
            key = (
                doc.get("legacy_plano_id"),
                doc.get("document_version"),
                doc.get("revision"),
            )
            if any(
                (
                    d.get("legacy_plano_id"),
                    d.get("document_version"),
                    d.get("revision"),
                ) == key
                for d in self.docs
            ):
                raise DuplicateKeyError("duplicate version/revision")
        self.docs.append(deepcopy(doc))
        return object()

    async def find_one_and_update(
        self,
        query,
        update,
        projection=None,
        return_document=None,
    ):
        for index, doc in enumerate(self.docs):
            if not self._matches(doc, query):
                continue
            changed = deepcopy(doc)
            for key, value in update.get("$set", {}).items():
                changed[key] = value
            for key, value in update.get("$inc", {}).items():
                changed[key] = changed.get(key, 0) + value
            self.docs[index] = changed
            return self._project(changed, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor(
            self._project(doc, projection)
            for doc in self.docs
            if self._matches(doc, query)
        )


class FakeDB:
    def __init__(self):
        self.collections = {
            "aee_dossier_v2_heads": FakeCollection("heads"),
            "aee_dossier_v2_snapshots": FakeCollection("snapshots"),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.fixture
def legacy_plan():
    return {
        "id": "legacy-plan-1",
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "professor_aee_id": "prof-1",
        "professor_aee_nome": "Professora AEE",
        "publico_alvo": "transtorno_espectro_autista",
        "criterio_elegibilidade": "Fundamentação pedagógica inicial.",
        "linha_base_situacao_atual": "Demanda inicial e contexto.",
        "linha_base_potencialidades": "Potencialidades observadas.",
        "linha_base_dificuldades": "Demandas de apoio.",
        "linha_base_comunicacao": "Comunicação observada.",
        "barreiras": [{"tipo": "comunicacional", "descricao": "Barreira comunicacional"}],
        "objetivos": [{"descricao": "Ampliar participação"}],
        "recursos_acessibilidade": [
            {"tipo": "rotina_visual", "descricao": "Rotina visual", "disponivel": True}
        ],
        "orientacoes_sala_comum": "Articulação com sala comum.",
        "adequacoes_curriculares": "Acessibilidade curricular.",
        "indicadores_progresso": "Monitoramento contínuo.",
        "data_revisao": "2026-12-01",
        "status": "ativo",
        "created_by": "prof-1",
    }


@pytest.fixture
def actor():
    return {
        "id": "prof-1",
        "role": "professor",
        "full_name": "Professora AEE",
        "email": "prof@example.test",
    }


def ready_study_case():
    return AEEStudyCase(
        state="complete",
        fundamentacao_pedagogica_identificacao="Fundamentação pedagógica.",
        demanda_inicial_contexto="Demandas e barreiras iniciais.",
        barreiras_contexto=["Barreira comunicacional"],
        potencialidades="Potencialidades identificadas.",
        demandas_apoio="Demandas de apoio identificadas.",
        comunicacao_participacao="Comunicação e participação observadas.",
        estrategias_recursos_acessibilidade=["Rotina visual"],
        participacao_estudante="Participou do processo conforme suas formas de expressão.",
        contribuicoes_familia="Família contribuiu com histórico e necessidades atuais.",
    )


def ready_paee():
    not_needed = AEESupportAssessment(
        status="not_needed",
        justificativa="Avaliado pedagogicamente e não indicado neste momento.",
    )
    return AEEPAEE(
        state="complete",
        barreiras_prioritarias=["Barreira comunicacional"],
        objetivos=[],
        materiais_recursos=[
            AEEAccessibilityResource(
                tipo="rotina_visual",
                descricao="Rotina visual",
                disponivel=True,
            )
        ],
        tecnologia_assistiva=not_needed,
        comunicacao_aumentativa_alternativa=not_needed.model_copy(deep=True),
        profissional_apoio_escolar=not_needed.model_copy(deep=True),
        tradutor_interprete_libras=not_needed.model_copy(deep=True),
        guia_interprete=not_needed.model_copy(deep=True),
        demandas_formacao_educacao_especial_inclusiva=[
            "Avaliado: não há demanda adicional identificada neste momento."
        ],
        acionamentos_rede_protecao=[
            "Avaliado: não há acionamento da rede de proteção indicado neste momento."
        ],
        indicadores_progresso="Monitoramento contínuo.",
    )


def ready_pei():
    return AEEPEI(
        state="complete",
        atividades_aee=["Atividades articuladas ao PAEE"],
        articulacao_sala_comum="Planejamento colaborativo com sala comum.",
        acessibilidade_curricular="Acessibilização curricular definida.",
        acessibilidade_didatico_pedagogica="Estratégias didático-pedagógicas definidas.",
        acessibilidade_avaliativa="Estratégias avaliativas acessíveis definidas.",
        estrategias_acompanhamento_monitoramento="Acompanhamento contínuo.",
        devolutivas_familia=["Devolutiva registrada à família."],
    )


def test_bootstrap_is_sidecar_and_snapshot_hash_is_tamper_evident(legacy_plan, actor):
    original = deepcopy(legacy_plan)
    head, snapshot = bootstrap_documents(legacy_plan, actor=actor)

    assert legacy_plan == original
    assert head["legacy_plano_id"] == "legacy-plan-1"
    assert head["active_snapshot_id"] is None
    assert head["working_snapshot_id"] == snapshot["id"]
    assert snapshot["document_version"] == 1
    assert snapshot["revision"] == 1
    assert snapshot["dossier"]["lifecycle"]["status"] == "draft"
    assert verify_snapshot_hash(snapshot) is True

    tampered = deepcopy(snapshot)
    tampered["dossier"]["study_case"]["potencialidades"] = "conteúdo adulterado"
    assert verify_snapshot_hash(tampered) is False


def test_activation_requires_complete_sections_and_required_fields(legacy_plan, actor):
    _, snapshot = bootstrap_documents(legacy_plan, actor=actor)
    from aee_v2.contracts import AEEDossierV2

    dossier = AEEDossierV2.model_validate(snapshot["dossier"])
    assert activation_validation(dossier).ready is False

    dossier.study_case = ready_study_case()
    dossier.paee = ready_paee()
    dossier.pei = ready_pei()
    validation = activation_validation(dossier)
    assert validation.ready is True, validation.blockers


def test_repository_full_cycle_keeps_active_v1_while_v2_is_working(legacy_plan, actor):
    async def scenario():
        repo = AEEV2Repository(FakeDB())
        state = await repo.bootstrap(legacy_plan, actor=actor)
        assert state.effective_source == "legacy"
        assert state.head.head_revision == 1
        assert state.working_snapshot.document_version == 1

        state = await repo.save_section(
            "legacy-plan-1",
            section_name="study_case",
            section=ready_study_case(),
            expected_head_revision=state.head.head_revision,
            expected_working_snapshot_id=state.working_snapshot.id,
            actor=actor,
        )
        state = await repo.save_section(
            "legacy-plan-1",
            section_name="paee",
            section=ready_paee(),
            expected_head_revision=state.head.head_revision,
            expected_working_snapshot_id=state.working_snapshot.id,
            actor=actor,
        )
        state = await repo.save_section(
            "legacy-plan-1",
            section_name="pei",
            section=ready_pei(),
            expected_head_revision=state.head.head_revision,
            expected_working_snapshot_id=state.working_snapshot.id,
            actor=actor,
        )
        active = await repo.activate(
            "legacy-plan-1",
            expected_head_revision=state.head.head_revision,
            expected_working_snapshot_id=state.working_snapshot.id,
            actor=actor,
        )
        assert active.effective_source == "sidecar_active"
        assert active.working_snapshot is None
        assert active.active_snapshot.document_version == 1
        active_id = active.active_snapshot.id

        revision = await repo.start_revision(
            "legacy-plan-1",
            expected_head_revision=active.head.head_revision,
            actor=actor,
        )
        assert revision.active_snapshot.id == active_id
        assert revision.active_snapshot.document_version == 1
        assert revision.working_snapshot.document_version == 2
        assert revision.working_snapshot.revision == 1
        assert revision.working_snapshot.dossier.lifecycle.status == "review"
        assert revision.head.next_document_version == 3

        history = await repo.list_snapshots("legacy-plan-1")
        assert len(history) >= 6
        assert all("dossier" not in item for item in history)

    asyncio.run(scenario())


def test_optimistic_lock_rejects_stale_head_revision(legacy_plan, actor):
    async def scenario():
        repo = AEEV2Repository(FakeDB())
        state = await repo.bootstrap(legacy_plan, actor=actor)
        old_revision = state.head.head_revision
        old_snapshot = state.working_snapshot.id

        await repo.save_section(
            "legacy-plan-1",
            section_name="study_case",
            section=ready_study_case(),
            expected_head_revision=old_revision,
            expected_working_snapshot_id=old_snapshot,
            actor=actor,
        )

        with pytest.raises(AEEV2Conflict):
            await repo.save_section(
                "legacy-plan-1",
                section_name="paee",
                section=ready_paee(),
                expected_head_revision=old_revision,
                expected_working_snapshot_id=old_snapshot,
                actor=actor,
            )

    asyncio.run(scenario())


def test_persistence_router_never_writes_or_deletes_legacy_plan_collection():
    router_source = (
        Path(__file__).resolve().parents[1] / "routers" / "aee_v2_persistence.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "db.planos_aee.insert_",
        "db.planos_aee.update_",
        "db.planos_aee.delete_",
        "db.planos_aee.replace_",
        "db.planos_aee.find_one_and_update",
        "db.planos_aee.find_one_and_delete",
    )
    for token in forbidden:
        assert token not in router_source

def test_fase4_student_and_family_participation_are_independent_requirements(legacy_plan, actor):
    _, snapshot = bootstrap_documents(legacy_plan, actor=actor)
    from aee_v2.contracts import AEEDossierV2

    dossier = AEEDossierV2.model_validate(snapshot["dossier"])
    dossier.study_case.participacao_estudante = "Participação registrada."
    dossier.study_case.contribuicoes_estudante = None
    dossier.study_case.contribuicoes_familia = None
    codes = {item["code"] for item in activation_validation(dossier).blockers}
    assert "STUDY_CASE_STUDENT_PARTICIPATION" not in codes
    assert "STUDY_CASE_FAMILY_PARTICIPATION" in codes


def test_fase4_ta_aac_capacity_is_required_when_need_is_identified(legacy_plan, actor):
    _, snapshot = bootstrap_documents(legacy_plan, actor=actor)
    from aee_v2.contracts import AEEDossierV2

    dossier = AEEDossierV2.model_validate(snapshot["dossier"])
    dossier.paee.tecnologia_assistiva = AEESupportAssessment(
        status="needed",
        justificativa="Necessidade identificada pedagogicamente.",
    )
    codes = {item["code"] for item in activation_validation(dossier).blockers}
    assert "PAEE_TECNOLOGIA_ASSISTIVA_CAPACITY" in codes

    dossier.paee.tecnologia_assistiva.capacidade_disponibilizacao = "Disponibilização prevista pela escola."
    codes = {item["code"] for item in activation_validation(dossier).blockers}
    assert "PAEE_TECNOLOGIA_ASSISTIVA_CAPACITY" not in codes


def test_fase4_training_and_network_are_independent_assessments(legacy_plan, actor):
    _, snapshot = bootstrap_documents(legacy_plan, actor=actor)
    from aee_v2.contracts import AEEDossierV2

    dossier = AEEDossierV2.model_validate(snapshot["dossier"])
    dossier.paee.demandas_formacao_educacao_especial_inclusiva = ["Nenhuma demanda adicional."]
    dossier.paee.acionamentos_rede_protecao = []
    codes = {item["code"] for item in activation_validation(dossier).blockers}
    assert "PAEE_TRAINING_ASSESSMENT" not in codes
    assert "PAEE_NETWORK_ASSESSMENT" in codes


def test_fase4_pei_requires_activities_and_common_room_articulation(legacy_plan, actor):
    _, snapshot = bootstrap_documents(legacy_plan, actor=actor)
    from aee_v2.contracts import AEEDossierV2

    dossier = AEEDossierV2.model_validate(snapshot["dossier"])
    dossier.pei.atividades_aee = ["Atividade prevista"]
    dossier.pei.articulacao_sala_comum = None
    codes = {item["code"] for item in activation_validation(dossier).blockers}
    assert "PEI_AEE_ACTIVITIES" not in codes
    assert "PEI_COMMON_ROOM_ARTICULATION" in codes


def test_fase4_annual_review_date_is_required_for_activation(legacy_plan, actor):
    dossier = bootstrap_documents(legacy_plan, actor=actor)[1]["dossier"]
    from aee_v2.contracts import AEEDossierV2

    parsed = AEEDossierV2.model_validate(dossier)
    parsed.lifecycle.review_at = None
    codes = {item["code"] for item in activation_validation(parsed).blockers}
    assert "ANNUAL_REVIEW_DATE" in codes


def test_fase4_lifecycle_update_is_versioned_and_preserves_status_version(legacy_plan, actor):
    async def scenario():
        from aee_v2.versioning import AEEV2LifecycleFields

        repo = AEEV2Repository(FakeDB())
        state = await repo.bootstrap(legacy_plan, actor=actor)
        old_status = state.working_snapshot.dossier.lifecycle.status
        old_version = state.working_snapshot.dossier.lifecycle.version
        old_snapshot = state.working_snapshot.id

        state = await repo.save_lifecycle(
            "legacy-plan-1",
            section=AEEV2LifecycleFields(
                effective_from="2026-02-10",
                review_at="2026-12-15",
                periodo_vigencia_legacy="Ano letivo 2026",
            ),
            expected_head_revision=state.head.head_revision,
            expected_working_snapshot_id=old_snapshot,
            actor=actor,
        )

        assert state.working_snapshot.id != old_snapshot
        assert state.working_snapshot.operation == "update_lifecycle"
        assert state.working_snapshot.changed_section == "lifecycle"
        assert state.working_snapshot.dossier.lifecycle.review_at == "2026-12-15"
        assert state.working_snapshot.dossier.lifecycle.status == old_status
        assert state.working_snapshot.dossier.lifecycle.version == old_version

    asyncio.run(scenario())
