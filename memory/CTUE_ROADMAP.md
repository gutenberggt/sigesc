# CTUE_ROADMAP.md — Entrega 5: Roadmap Técnico de Implementação

> **Sprint de PROPOSTA · Jun/2026 · READ-ONLY.** Sequência de execução aprovável.
> Princípio de simplicidade: **máximo reuso do modelo existente, mínimo de campos novos,
> zero módulo paralelo (SSoT).** Cada fase só inicia após aprovação e testes da anterior.

## Visão geral das fases
| Fase | Entrega | Toca modelo? | Risco | Depende de |
|---|---|---|---|---|
| **A** | Reorganização da interface (CTUE 2 visões) | ❌ Não | Baixo | — |
| **B** | Painel Gerencial da Rede | ❌ Não | Baixo | A (dados expostos) |
| **C** | Dossiê Institucional (PDF verificável) | ❌ Não | Médio | A |
| **D** | Evolução do modelo (campos ausentes) | ✅ Sim (aditivo) | Médio | A, B, C |

---

## FASE A — Reorganização da Interface (Prioridade Máxima)
**Escopo:** transformar `SchoolsComplete.js` na **Visão 1 (CTUE)** com as 14 seções e separar a
**Visão 2 (Gestão Pedagógica/Operacional)**. Expor os **55 campos hoje ocultos**. Sem schema.

**Frontend**
- Refatorar `SchoolsComplete.js` (>2.600 linhas) em componentes por seção CTUE
  (`ctue/IdentificacaoSection.jsx`, `AguaSaneamentoSection.jsx`, `SegurancaSection.jsx`, …) +
  um `CTUELayout` com navegação lateral + indicador de completude.
- Alternador de **Visão 1/Visão 2** no topo. Visão 2 reaproveita abas atuais (Ensino, Turmas,
  Servidores, Permissão) e páginas existentes.
- Rótulos/microtextos de §2.3 do `CTUE_ARQUITETURA.md`; validação inline; `viewMode` preservado.
- `data-testid` por seção/campo.

**Backend:** nenhuma mudança de modelo. `SchoolUpdate` já aceita todos os campos.

**Testes:** `testing_agent` (frontend) — preencher/salvar cada seção, alternar visões, RBAC
(gestor vê só sua escola), regressão do salvamento existente. Critério: 55 campos gravam e
recarregam corretamente.

**Entregável:** CTUE navegável, todos os campos do modelo editáveis, duas visões separadas.

---

## FASE B — Painel Gerencial da Rede
**Backend**
- `GET /api/schools/network-infra-overview` (read-only, escopo por mantenedora + filtros).
- Saída com contrato **BI-ready** (espelha `bi_indicator_defs`) + listas para drill-down.
- Somente indicadores ✅ do catálogo (`CTUE_PAINEL_E_DOSSIE.md §3.3`).

**Frontend**
- Página `RedeInfraestrutura.jsx` (cards + drill-down + mapa lat/long + ranking de conformidade).
- Card no Dashboard (RBAC Secretário/SEMED).

**Testes:** `testing_agent` — reconciliação (soma dos drill-downs = total), filtros, RBAC.
Critério: números batem com o CTUE; clique abre a escola.

**Nota SSoT:** projetar o endpoint para ser **migrado ao Motor de Indicadores** (BI-2) sem
reescrever o contrato.

---

## FASE C — Dossiê Institucional
**Backend**
- `backend/pdf/dossie_institucional.py` (reuso `get_logo_image` + `verification_footer`).
- `GET /api/schools/{id}/dossie` → PDF; versão em lote por mantenedora.
- Documento verificável via `verifiable_documents` + QR + `/v/{token}` (padrão existente).

**Frontend:** botão "Gerar Dossiê" no CTUE da escola + no painel (lote).

**Testes:** extração de PDF (pdfplumber) — todas as seções presentes, quadro-resumo de
conformidade correto, QR resolve. Read-only confirmado.

**Dependência opcional:** foto da fachada → object storage (pode ficar para Fase D; dossiê
gera sem foto).

---

## FASE D — Evolução do Modelo (somente após A+B+C)
**Governança obrigatória:** `ARCHITECTURE_BASELINE.md` §3.2 (auditoria + dry-run + rollback),
padrão `with_critical_mutation`. **Todo campo aditivo, `Optional`, retrocompatível.**

**Classificação e justificativa (cada campo DEVE ter):** finalidade administrativa · exigência
(MP/FNDE/INEP/Bombeiros) · impacto backend · impacto frontend · impacto relatórios.

| Campo/estrutura | Classe | Justificativa (órgão) |
|---|---|---|
| `agua_potavel`, `certificado_potabilidade` | **Obrigatório** | MP/TCE — potabilidade é achado recorrente |
| `tipo_esgotamento` (enum) | **Obrigatório** | Educacenso + MP — tipificação do esgoto |
| `avcb_bombeiros` (+ validade) | **Obrigatório** | Corpo de Bombeiros — segurança |
| `obras: List[Obra]` (situação/tipo/valor/`fonte_recurso`/datas) | **Obrigatório** | FNDE/PAR/PDDE + TCM |
| `regime_ocupacao`, `predio_compartilhado` | **Recomendado** | Educacenso — local de funcionamento |
| `tipo_destinacao_lixo` (enum) | **Recomendado** | Educacenso |
| `alvara_funcionamento`, `licenca_sanitaria`, `habite_se` | **Recomendado** | Vigilância/Prefeitura |
| `area_terreno_m2`, `area_construida_m2`, `ano_construcao` | **Recomendado** | Planejamento/obras |
| `foto_fachada` (object storage) | **Recomendado** | Dossiê institucional |
| `observacoes_tecnicas` (texto) | **Opcional** | Registro livre auditável |
| `sala_leitura`, `area_verde`, `patio_coberto/descoberto` | **Opcional** | Educacenso (refino) |
| `fornece_alimentacao` | **Opcional** | Educacenso |

**Critério de inclusão (gate):** só entra campo que responda a **necessidade objetiva** de
gestão ou órgão de controle. "Pode ser útil" = rejeitado. Detalhado em
`CTUE_PRINCIPIOS_ARQUITETURAIS.md`.

**Pós-Fase D:** expor novos campos no CTUE (seções Obras/Documentação/Observações), habilitar
indicadores ⛔ do painel e completar o quadro-resumo do dossiê.

---

## Consolidação de redundâncias (paralelo, sob §3.2)
Executar as consolidações R1–R6 (`CTUE_ARQUITETURA.md §3`) preferencialmente **junto à Fase A**
(frontend) e **Fase D** (backfill de campos canônicos), sempre com dry-run + rollback. Nada
removido sem aprovação; leitura tolerante a legado mantida.

---

## Marcos de aprovação (gates humanos)
1. Aprovar propostas (este pacote) → inicia **A**.
2. Homologar **A** → inicia **B**.
3. Homologar **B** → inicia **C**.
4. Homologar **C** + aprovar a matriz de campos → inicia **D**.

*Entrega 5. Última atualização: Jun/2026 — Sprint Proposta CTUE.*

---

## Fase D — Campos Estruturais (ENTREGUE · Jun/2026)
**Estratégia aprovada pelo owner: opção (a) — modelo + UI, SEM ativar o motor de conformidade.**
- 17 novos campos adicionados a `SchoolBase`/`SchoolUpdate` (informativos):
  Infra Física (area_terreno_m2, area_construida_m2, ano_construcao, regime_ocupacao, predio_compartilhado);
  Acessibilidade (vias_acessiveis, dependencias_acessiveis);
  Água (agua_potavel, certificado_potabilidade, tipo_esgotamento, tipo_destinacao_lixo);
  Segurança (avcb_bombeiros); Conservação (necessita_reforma, itens_criticos);
  Documentação (alvara_funcionamento, licenca_sanitaria, habite_se).
- UI: campos nas abas Infraestrutura, Dependências ("Dados Estruturais do Prédio") e
  Documentação ("Situação Documental"). Nova categoria doc: "Certificado de Potabilidade da Água".
- Dossiê PDF exibe os campos quando preenchidos (helper _tri para tri-estado).
- **SSoT intocado**: `ctue_conformity_service` e `ctue_rulesets.json` NÃO alterados. Percentuais
  de Conformidade/Completude/Maturidade permanecem idênticos (validado: 70%/60% e 2%/5% estáveis).
- **Preparação futura**: metadados em `/app/backend/config/ctue_fase_d_fields.json` permitem
  incorporar cada campo ao ruleset sem mudança estrutural — ativação dependerá de decisão administrativa.
- Testes: `backend/tests/test_fase_d_campos.py` (modelo + SSoT estável + PDF) e ciclo E2E de
  persistência validado via UI.

---

## Dossiê Institucional da Rede Municipal (ENTREGUE · Jun/2026)
Um único PDF consolidado da rede, gerado com um clique no Painel Gerencial ("Dossiê da Rede").
- **SSoT rigoroso**: `ctue.build_network_dossie()` consome `build_network_panel()` + `evaluate()` por
  escola. Nenhum cálculo/indicador novo — apenas consolidação/ordenação de dados existentes.
- 12 seções: Capa, Apresentação, Panorama Geral, Distribuição da Rede, Ranking de Conformidade,
  Ranking de Prioridades (mesma Fila de Ações Prioritárias), Infraestrutura da Rede, Obras,
  Documentação, Diagnóstico Executivo (texto determinístico, sem IA), Plano de Ação (consolida a
  Fila de Prioridades), Conclusão.
- Endpoint: `GET /api/ctue/network-dossie?profile=&exercicio=` (StreamingResponse PDF, escopo
  multi-tenant como o network-panel). PDF: `pdf/dossie_rede.py`.
- Frontend: botão "Dossiê da Rede" em `NetworkPanel.jsx` respeitando o perfil selecionado.
- Testes: `backend/tests/test_dossie_rede.py` (dados + PDF) e verificação das 12 seções (6 págs).
