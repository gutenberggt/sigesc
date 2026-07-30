"""
CmdeFrequencySimulator — Simulador CMDE de homologação (Sprint 002.a).

Provider PLUGÁVEL (implementa CmdeFrequencyPort) que exercita o fluxo completo de envio
SEM depender do ambiente externo do MEC. Todo envio simulado registra: correlation_id,
cenário executado, resultado, métricas (MigMonitoring) e evento de auditoria (MigAuditService).

Cenários controlados:
  1. accept          — lote aceito integralmente (protocolo gerado)
  2. reject          — rejeição de registros (parcial, código/motivo por item)
  3. error_502/503/504 — erro temporário do gateway (recuperável)
  4. timeout         — tempo limite excedido (recuperável)
  5. invalid_response— resposta fora do contrato esperado (valid=False)

Modo caótico (chaos): escolhe o cenário por sorteio PONDERADO, porém DETERMINÍSTICO
(seed + correlation_id + índice da chamada) e AUDITÁVEL (o cenário sorteado é registrado).
Erros/timeout suportam `transient_failures`: falham N vezes por correlation_id e depois aceitam
(valida o RetryManager sem depender de transporte real).
"""
import hashlib
import time
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Set

from mig.cmde.frequency_port import CmdeFrequencyPort
from mig.cmde.dtos import CmdeFrequencyPayloadDTO, CmdeFrequencyResponseDTO, CmdeItemResultDTO
from mig.core.exceptions import MigError, MigUpstreamError, MigUnavailableError, MigTimeoutError
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.ids import generate_correlation_id

SCENARIO_ACCEPT = "accept"
SCENARIO_REJECT = "reject"
SCENARIO_ERROR_502 = "error_502"
SCENARIO_ERROR_503 = "error_503"
SCENARIO_ERROR_504 = "error_504"
SCENARIO_TIMEOUT = "timeout"
SCENARIO_INVALID = "invalid_response"

ALL_SCENARIOS = (
    SCENARIO_ACCEPT, SCENARIO_REJECT, SCENARIO_ERROR_502, SCENARIO_ERROR_503,
    SCENARIO_ERROR_504, SCENARIO_TIMEOUT, SCENARIO_INVALID,
)
_TRANSIENT = {SCENARIO_ERROR_502, SCENARIO_ERROR_503, SCENARIO_ERROR_504, SCENARIO_TIMEOUT}

DEFAULT_CHAOS_WEIGHTS = {
    SCENARIO_ACCEPT: 0.60,
    SCENARIO_REJECT: 0.15,
    SCENARIO_ERROR_503: 0.10,
    SCENARIO_ERROR_502: 0.05,
    SCENARIO_TIMEOUT: 0.05,
    SCENARIO_INVALID: 0.05,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SimulatorConfig:
    scenario: str = SCENARIO_ACCEPT             # cenário fixo (quando chaos=False)
    reject_refs: Set[str] = field(default_factory=set)  # refs (student_id) a rejeitar
    reject_every: int = 0                       # rejeita cada N-ésimo item (0 = desativado)
    transient_failures: int = 0                 # nº de falhas por correlation_id antes de aceitar
    chaos: bool = False
    chaos_seed: int = 1337
    chaos_weights: dict = field(default_factory=lambda: dict(DEFAULT_CHAOS_WEIGHTS))


class CmdeFrequencySimulator(CmdeFrequencyPort):
    provider = "cmde"

    def __init__(self, config: SimulatorConfig = None, audit: MigAuditService = None,
                 monitoring: MigMonitoring = None, environment: str = "homologacao"):
        self.config = config or SimulatorConfig()
        self.audit = audit or MigAuditService()
        self.monitoring = monitoring or MigMonitoring()
        self.environment = environment
        self._call_index = 0
        self._attempts: dict = {}               # correlation_id -> nº de tentativas

    # ---- Seleção de cenário ----
    def _pick_scenario(self, cid: str) -> str:
        if not self.config.chaos:
            return self.config.scenario
        weights = self.config.chaos_weights or DEFAULT_CHAOS_WEIGHTS
        rng = random.Random(f"{self.config.chaos_seed}:{cid}:{self._call_index}")
        scenarios = list(weights.keys())
        w = list(weights.values())
        return rng.choices(scenarios, weights=w, k=1)[0]

    # ---- Porta ----
    async def enviar_frequencia(self, payload: CmdeFrequencyPayloadDTO) -> CmdeFrequencyResponseDTO:
        self._call_index += 1
        cid = payload.correlation_id or generate_correlation_id("SIM")
        # chave de tentativas por operação+aluno (itens de um mesmo lote compartilham cid)
        akey = f"{cid}:{payload.items[0].student_id if payload.items else ''}"
        scenario = self._pick_scenario(cid)
        started = _now_iso()
        t0 = time.perf_counter()
        self.monitoring.incr("cmde_sim.request")
        self.monitoring.incr(f"cmde_sim.{scenario}")

        try:
            result = self._execute(scenario, payload, cid, akey)
        except MigError as e:
            await self._audit(scenario, payload, cid, "error", started, t0,
                              http_status=e.status_code, error_code=type(e).__name__,
                              error_message=e.message)
            raise

        if not result.valid:
            await self._audit(scenario, payload, cid, "error", started, t0, result=result,
                              http_status=result.http_status, error_code="INVALID_RESPONSE",
                              error_message="Resposta fora do contrato esperado.")
            return result

        await self._audit(scenario, payload, cid, "success", started, t0, result=result,
                          http_status=result.http_status)
        return result

    # ---- Execução por cenário ----
    def _execute(self, scenario: str, payload: CmdeFrequencyPayloadDTO,
                 cid: str, akey: str) -> CmdeFrequencyResponseDTO:
        if scenario in _TRANSIENT:
            self._attempts[akey] = self._attempts.get(akey, 0) + 1
            if self.config.transient_failures and self._attempts[akey] > self.config.transient_failures:
                return self._accept_response(payload, cid)   # recuperado após N falhas
            raise self._error_for(scenario)
        if scenario == SCENARIO_INVALID:
            return CmdeFrequencyResponseDTO(http_status=200, valid=False, protocol=None,
                                            items=[], raw={"unexpected_schema": True})
        if scenario == SCENARIO_REJECT:
            return self._reject_response(payload, cid)
        return self._accept_response(payload, cid)

    def _error_for(self, scenario: str) -> MigError:
        if scenario == SCENARIO_ERROR_502:
            return MigUpstreamError("Simulador: Bad Gateway (HTTP 502).", status_code=502)
        if scenario == SCENARIO_ERROR_503:
            return MigUnavailableError("Simulador: serviço indisponível (HTTP 503).")
        if scenario == SCENARIO_ERROR_504:
            return MigUpstreamError("Simulador: Gateway Timeout (HTTP 504).", status_code=504)
        return MigTimeoutError("Simulador: tempo limite excedido.")

    def _protocol(self, payload: CmdeFrequencyPayloadDTO, cid: str) -> str:
        suffix = hashlib.sha1(cid.encode("utf-8")).hexdigest()[:8].upper()
        return f"SIM-{payload.competencia}-{suffix}"

    def _accept_response(self, payload: CmdeFrequencyPayloadDTO, cid: str) -> CmdeFrequencyResponseDTO:
        items = [CmdeItemResultDTO(ref=i.student_id, accepted=True) for i in payload.items]
        return CmdeFrequencyResponseDTO(http_status=200, valid=True,
                                        protocol=self._protocol(payload, cid), items=items)

    def _reject_response(self, payload: CmdeFrequencyPayloadDTO, cid: str) -> CmdeFrequencyResponseDTO:
        items = []
        for idx, it in enumerate(payload.items):
            reject = (it.student_id in self.config.reject_refs) or \
                     (self.config.reject_every and (idx + 1) % self.config.reject_every == 0)
            if reject:
                items.append(CmdeItemResultDTO(ref=it.student_id, accepted=False,
                                               code="REJEITADO_SIM",
                                               reason="Registro rejeitado pelo simulador (cenário reject)."))
            else:
                items.append(CmdeItemResultDTO(ref=it.student_id, accepted=True))
        # garante ao menos 1 rejeição quando nenhum critério casou (cenário reject explícito)
        if items and not any(not i.accepted for i in items):
            items[0] = CmdeItemResultDTO(ref=items[0].ref, accepted=False, code="REJEITADO_SIM",
                                         reason="Registro rejeitado pelo simulador (cenário reject).")
        return CmdeFrequencyResponseDTO(http_status=200, valid=True,
                                        protocol=self._protocol(payload, cid), items=items)

    # ---- Auditoria + métricas ----
    async def _audit(self, scenario, payload, cid, status, started, t0, result=None,
                     http_status=None, error_code=None, error_message=None):
        sent = len(payload.items)
        accepted = sum(1 for i in result.items if i.accepted) if result else 0
        rejected = sum(1 for i in result.items if not i.accepted) if result else 0
        reasons = None
        if result:
            reasons = [{"ref": i.ref, "code": i.code, "reason": i.reason}
                       for i in result.items if not i.accepted] or None
        await self.audit.record({
            "provider": self.provider, "operation": "FREQUENCY_SEND", "tenant": payload.tenant,
            "actor": "simulator", "status": status, "started_at": started,
            "finished_at": _now_iso(), "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "environment": self.environment, "correlation_id": cid,
            "scenario": scenario, "simulated": True,
            "records_processed": sent, "records_sent": sent,
            "records_accepted": accepted, "records_rejected": rejected,
            "rejection_reasons": reasons, "http_status": http_status,
            "error_code": error_code, "error_message": error_message,
        })
