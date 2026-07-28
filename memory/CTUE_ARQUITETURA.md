# CTUE_ARQUITETURA.md — Cadastro Técnico da Unidade Escolar (CTUE)
### Entrega 1 (Arquitetura da Interface) + Entrega 2 (Wireframe) + Análise de Redundâncias

> **Sprint de PROPOSTA · Jun/2026 · READ-ONLY.** Nada foi implementado. Este documento é a
> **fonte oficial de referência** para a futura implementação. Wireframe textual = normativo;
> imagens = apoio ilustrativo (baixa fidelidade).
>
> **Base:** `AUDITORIA_CADASTRO_ESCOLAS.md`, `AUDITORIA_CAMPOS_ESCOLAS.md`, `MATRIZ_MP_FNDE_SIGESC.md`.
> **Princípio-mestre:** SSoT — a unidade escolar tem **uma única origem** para cada informação
> institucional (`schools`). Sem módulos paralelos. Ver `CTUE_PRINCIPIOS_ARQUITETURAIS.md`.
> **Boas práticas incorporadas (ERPs públicos/asset management, 2026):** navegação por
> *domínio de trabalho* (não pelo modelo de dados); formulário **seccionado com divulgação
> progressiva**; rótulos em linguagem simples; validação inline; anexos/documentos e
> georreferência como áreas de primeira classe; acessibilidade e auditabilidade.

---

## 0. Diagnóstico crítico da tela atual (visão de arquiteto de ERP)
Teste do "Secretário Municipal abrindo pela primeira vez": **hoje ele NÃO encontra as coisas
com facilidade.** Problemas concretos identificados no código (`SchoolsComplete.js`, 8 abas):
1. **Mistura de domínios** — patrimônio físico (infraestrutura) e gestão dinâmica (Turmas,
   Servidores, Permissões) convivem na mesma tela. São ciclos de vida diferentes.
2. **Dados institucionais oficiais escondidos** — Vinculação/Mantenedora, Gestor, Segurança,
   Conservação e Espaços Escolares **não têm tela**, embora existam no modelo.
3. **Agrupamento raso** — "Infraestrutura" junta água + acessibilidade + internet; "Dependências"
   mistura contagem de salas com ambientes pedagógicos.
4. **Nomenclatura técnica-interna** — `saneamento`, `coleta_lixo`, `regulamentacao` sem rótulo
   claro para o gestor.
5. **Redundâncias** — mesmo dado em dois campos (ver §4).

**Decisão arquitetural aprovada:** separar em **duas visões** de ciclo de vida distinto.

---

## 1. ENTREGA 1 — Nova arquitetura (2 visões)

### 🏛️ VISÃO 1 — CTUE (Cadastro Técnico da Unidade Escolar) — *patrimônio, muda pouco*
> A **SSoT** física/administrativa da escola. Alta estabilidade no tempo. É o que alimenta
> dossiês, painéis e respostas a órgãos de controle.

Navegação lateral (esquerda), na ordem lógica de leitura de um cadastro técnico de edificação:

| # | Seção CTUE | Campos existentes hoje (reuso) | Fase D (aditivo) |
|---|---|---|---|
| 1 | **Identificação** | `name, inep_code, sigla, cnpj, caracteristica_escolar, situacao_funcionamento, tipo_unidade, anexa_a, zona_localizacao` | — |
| 2 | **Localização & Georreferência** | `cep, logradouro, numero, complemento, bairro, distrito, municipio, estado, latitude, longitude` + contatos (`ddd_telefone, telefone, celular, email, site`) | — |
| 3 | **Gestão & Vinculação** | Gestor: `gestor_principal, cargo_gestor, secretario_escolar` · Vinculação: `dependencia_administrativa, esfera_administrativa, orgao_responsavel, regulamentacao, categoria_mantenedora, cnpj_mantenedora, forma_contratacao_estadual, forma_contratacao_municipal, possui_convenio` | — |
| 4 | **Infraestrutura Física** | `numero_salas_aula, capacidade_total_alunos, numero_banheiros, sala_direcao, sala_secretaria, sala_coordenacao, sala_professores, possui_almoxarifado` | `area_terreno_m2, area_construida_m2, ano_construcao, regime_ocupacao, predio_compartilhado` |
| 5 | **Ambientes Pedagógicos** | `possui_biblioteca, possui_lab_ciencias, possui_lab_informatica, salas_recursos_multifuncionais (AEE), possui_quadra*, possui_patio, possui_parque, possui_brinquedoteca, possui_auditorio, possui_horta, possui_cozinha, possui_refeitorio, possui_estacionamento` | `sala_leitura, area_verde, patio_coberto/descoberto` |
| 6 | **Acessibilidade** | `possui_rampas, possui_corrimao, banheiros_adaptados, banheiros_acessiveis, sinalizacao_tatil` | `vias_acessiveis, dependencias_acessiveis` |
| 7 | **Água, Saneamento & Energia** | `abastecimento_agua, energia_eletrica, saneamento, coleta_lixo` | `agua_potavel, certificado_potabilidade, tipo_esgotamento, tipo_destinacao_lixo` |
| 8 | **Segurança** | `saidas_emergencia, extintores/qtd_extintores, brigada_incendio, plano_evacuacao, qtd_cameras, possui_cercamento` | `avcb_bombeiros` (documento) |
| 9 | **Conectividade** | `possui_internet, tipo_conexao, cobertura_rede` | — |
| 10 | **Equipamentos & Patrimônio** | `qtd_computadores, qtd_tablets, qtd_projetores, qtd_impressoras, qtd_televisores, qtd_projetores_multimidia, qtd_aparelhos_som, qtd_lousas_digitais, possui_kits_cientificos, possui_instrumentos_musicais, possui_material_didatico, tamanho_acervo, participa_programas_governamentais` | — |
| 11 | **Conservação** | `estado_conservacao` | `necessita_reforma, itens_criticos` |
| 12 | **Obras** *(Fase D)* | — | `obras: List[Obra] (situacao, tipo, valor, fonte_recurso PAR/FNDE/PDDE, datas)` |
| 13 | **Documentação** *(Fase D)* | `regulamentacao` | `alvara_funcionamento, licenca_sanitaria, habite_se, avcb` (bool + validade + anexo) |
| 14 | **Observações Técnicas** *(Fase D)* | — | `observacoes_tecnicas` (texto livre auditável) |

> **Fotografia da escola** (pedida no dossiê) → depende de object storage; entra na **Fase D**
> como `foto_fachada` (upload). Ver roadmap.

### 🔄 VISÃO 2 — Gestão Pedagógica & Operacional — *dinâmico, muda sempre*
> Não faz parte do CTUE. Reúne o que já existe hoje (abas/páginas) sem misturar com o patrimônio.

| Área | Origem atual | Observação |
|---|---|---|
| Oferta de Ensino | `SchoolsComplete` aba "Ensino" (etapas/subníveis/atendimentos, `turnos_funcionamento, organizacao_turmas, tipo_avaliacao`) | Migra da tela técnica p/ a visão operacional |
| Calendário | módulo calendário existente | link |
| Turmas | aba "Turmas" / páginas de turmas | mantém |
| Matrículas | módulo matrículas/alunos | link |
| Servidores / Quadro | aba "Servidores" | mantém |
| Horários / Componentes | grade horária / currículo v2 | link |
| Permissões & Regras | aba "Permissão" (`bimestre_*`, `pre_matricula_ativa`, `anos_letivos`, `bloquear_lancamento_anos_encerrados`, `usar_regra_alternativa`) | mantém |
| Indicadores Pedagógicos | Painel PME etc. | **consome do Motor de Indicadores (SSoT)** |

**Ganho de UX:** o Secretário abre "CTUE" para saber *como a escola é* (patrimônio) e
"Gestão" para saber *como a escola opera* (pedagógico). Dois ciclos, duas telas, uma origem.

---

## 2. ENTREGA 2 — Wireframe (fonte oficial de implementação)

### 2.1 Mockups ilustrativos (apoio, baixa fidelidade)
- **Tela CTUE reorganizada:** ![CTUE form wireframe](https://static.prod-images.emergentagent.com/jobs/5fa73956-fad0-4535-9a86-1a00fceaa609/images/09f209b278e328cc8c95cb22273d8dd6848ad7c0fca5ec6c6dd250b25cdc4de7.jpeg)
- **Dossiê Institucional (capa):** ![Dossiê wireframe](https://static.prod-images.emergentagent.com/jobs/5fa73956-fad0-4535-9a86-1a00fceaa609/images/3a20b15834ee7915c4b0cf8926569c7ca79eb5f82c2a6af4991df23bf00d37b9.jpeg)

### 2.2 Wireframe textual NORMATIVO — Tela CTUE
```
┌───────────────────────────────────────────────────────────────────────────┐
│  ESCOLA: «Nome da Unidade»            [ CTUE (Técnico) ] [ Gestão Operac. ]  │  ← alternador de VISÃO
│  INEP: 12345678 · Situação: Em atividade · Zona: Urbana        [Editar/Salvar]│
├──────────────────┬────────────────────────────────────────────────────────┤
│  NAV LATERAL      │  CONTEÚDO (seção selecionada)                            │
│  (progresso %)    │                                                          │
│  ● 1 Identificação│  ┌── Cabeçalho da seção: "7. Água, Saneamento & Energia" │
│  ○ 2 Localização  │  │   badge de completude: 3/4 campos ✓                   │
│  ○ 3 Gestão       │  ├────────────────────────────────────────────────────┐ │
│  ○ 4 Infra Física │  │  Abastecimento de Água*    [ Rede pública ▾ ]        │ │
│  ○ 5 Ambientes    │  │  Energia Elétrica*         [ Rede pública ▾ ]        │ │
│  ○ 6 Acessibilid. │  │  Esgotamento Sanitário*    [ ______________ ]        │ │  ← hoje "saneamento"
│  ○ 7 Água/Saneam. │  │  Destinação de Resíduos    [ ______________ ]        │ │  ← hoje "coleta_lixo"
│  ○ 8 Segurança    │  │  ─ Fase D ─────────────────────────────────────────  │ │
│  ○ 9 Conectivid.  │  │  Água potável?  ☐   Certificado de potabilidade ☐    │ │  (aditivo)
│  ○ 10 Equip./Patr.│  └──────────────────────────────────────────────────────┘ │
│  ○ 11 Conservação │                                                          │
│  ○ 12 Obras (D)   │  [ ◀ Seção anterior ]           [ Próxima seção ▶ ]      │
│  ○ 13 Document.(D)│                                                          │
│  ○ 14 Obs. Técn.(D)  Barra inferior fixa: [Cancelar]           [Salvar CTUE] │
└──────────────────┴────────────────────────────────────────────────────────┘
```
**Regras de UX (normativas):**
- Navegação lateral por seção + **indicador de completude** por seção (ex.: 3/4) e global (%).
- **Divulgação progressiva:** campos "Fase D" ficam num subgrupo claramente rotulado; campos raros/avançados recolhidos.
- **Rótulos em linguagem de gestão** (ver §3), com microtexto de ajuda (ex.: "Esgotamento Sanitário — como o esgoto da escola é tratado").
- **Validação inline** e *smart defaults* da mantenedora (já existe `getDefaultLocation`).
- Modo `viewMode` (somente leitura) preservado. Acessibilidade: ordem de tabulação lógica, alto contraste.
- `data-testid` por seção e por campo (ex.: `ctue-section-agua`, `ctue-field-saneamento`).

### 2.3 Nomenclatura proposta (rótulo de tela ↔ campo do modelo)
| Rótulo atual/interno | Rótulo proposto (gestão) | Campo |
|---|---|---|
| Saneamento | **Esgotamento Sanitário** | `saneamento` |
| Coleta de lixo | **Destinação de Resíduos** | `coleta_lixo` |
| Regulamentação | **Ato de Autorização/Reconhecimento** | `regulamentacao` |
| Salas de recursos multifuncionais | **Sala de Recursos (AEE)** | `salas_recursos_multifuncionais` |
| Cobertura de rede | **Qualidade do Sinal de Internet** | `cobertura_rede` |
| Estado de conservação | **Estado de Conservação do Prédio** | `estado_conservacao` |

---

## 3. ENTREGA (transversal) — Análise de Redundâncias (proposta, NÃO executar)

### R1 · `possui_quadra` × `possui_quadra_esportiva`
- **Campos:** dois booleanos para o mesmo ambiente (quadra).
- **Motivo:** criados em momentos distintos ("Dependências" e "Espaços Escolares").
- **Riscos:** valores divergentes na mesma escola; contagem dupla em relatórios/painel.
- **Consolidação:** manter **`possui_quadra`** como canônico; `possui_quadra_esportiva` → derivado/deprecado.
- **Migração:** backfill `possui_quadra = possui_quadra OR possui_quadra_esportiva`; congelar escrita no deprecado.
- **Backend:** `SchoolUpdate` ignora o deprecado (mantém aceitar p/ retrocompat, sem persistir).
- **Frontend:** um único checkbox "Quadra Esportiva".
- **Relatórios:** painel/dossiê passam a ler só o canônico.
- **Retrocompat:** leitura tolerante (coerção no `field_validator`), dado antigo preservado.

### R2 · `extintores` (int) × `qtd_extintores` (int)
- **Campos:** duas contagens de extintores.
- **Motivo:** duplicação em "Infra-Segurança" vs "Equipamentos-Segurança".
- **Riscos:** números conflitantes; ambiguidade em vistoria.
- **Consolidação:** canônico **`qtd_extintores`**; `extintores` deprecado.
- **Migração:** `qtd_extintores = coalesce(qtd_extintores, extintores)`.
- **Backend/Frontend/Relatórios/Retrocompat:** idem R1.

### R3 · `banheiros_adaptados` (bool) × `banheiros_acessiveis` (int)
- **Campos:** existência (bool) e quantidade (int) de banheiros acessíveis.
- **Motivo:** dado relacionado modelado duas vezes.
- **Riscos:** bool=true com contagem 0 (incoerência).
- **Consolidação:** **`banheiros_acessiveis` (int)** é a fonte; `banheiros_adaptados` vira **derivado** (`> 0`).
- **Migração:** onde `banheiros_adaptados=true` e contagem nula → registrar como "≥1" (revisão manual sinalizada).
- **Backend:** expor bool como propriedade computada; frontend mostra contagem + selo "Acessível".
- **Retrocompat:** mantém aceitar o bool na escrita, sem duplicar verdade.

### R4 · `educacao_infantil_bercario` (retrocompat) × `_bercario_i` / `_bercario_ii`
- **Campos:** flag antiga agregada × novos subníveis.
- **Motivo:** evolução do detalhamento de berçário (já anotado "Retrocompatibilidade" no modelo).
- **Riscos:** oferta mostrada em duplicidade.
- **Consolidação:** canônicos **`_bercario_i` / `_bercario_ii`**; agregada = derivada (`i OR ii`).
- **Migração:** backfill do agregado a partir dos subníveis; congelar escrita direta no agregado.
- **Impactos:** este campo é **Visão 2 (Oferta)**, não CTUE — tratar junto da reorg de Oferta.

### R5 · `aulas_complementares` (legado) × `recomposicao_aprendizagem`
- **Campos:** atendimento antigo × conceito atual.
- **Motivo:** renomeação de política pedagógica (modelo marca "Legado").
- **Consolidação:** **`recomposicao_aprendizagem`** canônico; `aulas_complementares` deprecado.
- **Impactos:** Visão 2 (Oferta/Atendimentos).

### R6 · `niveis_ensino_oferecidos` (lista) × flags booleanas de etapa/subnível
- **Campos:** lista textual × ~30 booleanos (`educacao_infantil`, `fundamental_*ano`, etc.).
- **Motivo:** duas representações da mesma oferta.
- **Riscos:** dessincronização (lista diz uma coisa, flags outra).
- **Consolidação:** eleger **os booleanos** como fonte (granular, já usados pela UI) e **derivar** a lista, OU vice-versa — decidir na reorg da Oferta (Visão 2). Não é CTUE.
- **Nota:** também há campos **legados** em `SchoolUpdate` (`address`, `contacts`) já marcados "serão ignorados" — apenas documentar.

> **Regra:** nada é removido antes da aprovação. A consolidação segue a governança de migração
> `ARCHITECTURE_BASELINE.md` §3.2 (auditoria + dry-run + rollback), padrão `with_critical_mutation`.

---

## 4. Alinhamento SSoT / Motor de Indicadores
- CTUE = **origem única** dos dados físicos/administrativos. Painel (Entrega 3) e Dossiê
  (Entrega 4) **apenas consomem** — nunca recalculam nem armazenam cópias.
- Indicadores do painel devem, quando o **Motor de Indicadores** (BI-2) estiver ativo, ser
  **produzidos por ele** (baseline §3.9). Até lá, agregador read-only com **contrato BI-ready**.

*Fonte oficial de implementação. Última atualização: Jun/2026 — Sprint Proposta CTUE.*
