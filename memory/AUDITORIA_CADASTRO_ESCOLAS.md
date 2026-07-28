# AUDITORIA_CADASTRO_ESCOLAS.md — Auditoria do Cadastro de Escolas (SIGESC)

> **Sprint READ-ONLY · Jun/2026.** Nenhum modelo, coleção, banco, backend, frontend ou
> migração foi alterado. Este documento é **passivo** (leitura + análise + documentação).
> **Alinhado ao princípio SSoT** (`ARCHITECTURE_BASELINE.md` §3.9) e ao checklist de reuso
> (§3.1): **consolidar antes de expandir**.
>
> **Documentos auxiliares:**
> - `AUDITORIA_CAMPOS_ESCOLAS.md` — inventário campo a campo (Modelo × Interface).
> - `MATRIZ_MP_FNDE_SIGESC.md` — cruzamento normativo (Educacenso 2026 + MP/TCE).
>
> **Fontes primárias auditadas:** `backend/models.py::SchoolBase` (135 campos, linhas 356–574),
> `frontend/src/pages/SchoolsComplete.js` (formulário, 8 abas), `backend/routers/schools.py`
> (7 endpoints CRUD), diretório `backend/pdf/` (geradores de documentos).

---

## 0. Sumário executivo (TL;DR)
- **Hipótese do owner CONFIRMADA.** O modelo `SchoolBase` já é robusto (135 campos, cobrindo
  infraestrutura, acessibilidade, água, energia, segurança, conectividade, dependências,
  equipamentos, conservação e espaços escolares). **A lacuna dominante NÃO é de modelo — é de
  exposição na interface e de ausência de relatórios institucionais.**
- **55 de 135 campos (41%) do modelo estão OCULTOS na interface** — não há como o gestor
  preencher/atualizar dados que o próprio sistema já sabe armazenar.
- **~24 requisitos MP/FNDE já têm campo no modelo, faltando apenas expor na UI (🟨)**; apenas
  **~18 requisitos estão realmente ausentes do modelo (❌)** — concentrados em **obras,
  conformidade legal, potabilidade da água, tipificação de esgoto/lixo e metragem**.
- **Não existe hoje relatório/exportação institucional** de infraestrutura das escolas. Ou
  seja: mesmo com o dado preenchido, **não há como gerar rapidamente um documento para MP/TCM/FNDE**.
- **Prioridade recomendada:** (1) expor os campos ocultos na UI → (2) criar relatório
  consolidado de infraestrutura → (3) evolução pontual do modelo para os ❌. **Tudo sobre a
  coleção `schools` existente — sem novo "módulo de infraestrutura" (SSoT).**

---

## ENTREGA 1 — Inventário do Modelo (`SchoolBase`)
O modelo possui **135 campos**, organizados nos seguintes grupos (detalhe em
`AUDITORIA_CAMPOS_ESCOLAS.md`):

| Grupo | Exemplos | Cobertura |
|---|---|---|
| Identificação | `name, inep_code, sigla, cnpj, caracteristica_escolar, zona_localizacao, situacao_funcionamento, tipo_unidade, anexa_a` | Rico |
| Localização | `cep, logradouro, numero, bairro, municipio, distrito, estado, latitude, longitude` + contatos | Rico |
| Vinculação/Mantenedora | `dependencia_administrativa, orgao_responsavel, esfera_administrativa, regulamentacao, categoria_mantenedora, cnpj_mantenedora, forma_contratacao_*, possui_convenio` | Rico |
| Equipe | `gestor_principal, cargo_gestor, secretario_escolar` | OK |
| Oferta/Ensino | etapas + **todos os subníveis** + atendimentos (`aee, atendimento_integral, reforco_escolar, recomposicao_aprendizagem`) + `turnos_funcionamento, organizacao_turmas, tipo_avaliacao` | Rico |
| **Infra — Serviços** | `abastecimento_agua, energia_eletrica, saneamento, coleta_lixo` | Presente |
| **Infra — Acessibilidade** | `possui_rampas, possui_corrimao, banheiros_adaptados, sinalizacao_tatil, banheiros_acessiveis` | Presente |
| **Infra — Segurança** | `saidas_emergencia, extintores, qtd_extintores, brigada_incendio, plano_evacuacao, qtd_cameras` | Presente |
| **Infra — Conectividade** | `possui_internet, tipo_conexao, cobertura_rede` | Presente |
| **Infra — Conservação** | `estado_conservacao, possui_cercamento` | Presente |
| Dependências | `numero_salas_aula, capacidade_total_alunos, salas_recursos_multifuncionais, sala_direcao/secretaria/coordenacao/professores, numero_banheiros, possui_cozinha/refeitorio/almoxarifado/biblioteca/lab_*/quadra` | Rico |
| Equipamentos | `qtd_computadores/tablets/projetores/impressoras/televisores/lousas_digitais/…`, `possui_kits_cientificos/instrumentos_musicais` | Rico |
| Recursos | `possui_material_didatico, tamanho_acervo, participa_programas_governamentais` | Presente |
| Espaços Escolares | `possui_quadra_esportiva/patio/parque/brinquedoteca/auditorio/horta/estacionamento` | Presente |
| Permissões/Regras | `bimestre_*_limite_lancamento, pre_matricula_ativa, anos_letivos, bloquear_lancamento_anos_encerrados, usar_regra_alternativa` | OK |

**Conclusão E1:** modelo maduro. Infraestrutura, acessibilidade e segurança **já modeladas**.

---

## ENTREGA 2 — Inventário da Interface (`SchoolsComplete.js`)
Formulário com **8 abas**: `Geral · Infraestrutura · Dependências · Equipamentos · Ensino ·
Turmas · Servidores · Permissão`. **80 campos** editáveis (via `updateFormData`).

**O que cada aba expõe** está detalhado em `AUDITORIA_CAMPOS_ESCOLAS.md §3`. Pontos-chave:
- **Infraestrutura** expõe SOMENTE água, energia, 4 itens de acessibilidade e internet/tipo.
  **NÃO expõe** saneamento, coleta de lixo, cobertura de rede, **nem qualquer item de Segurança
  ou de Conservação** (seções inexistentes na tela, embora existam no modelo).
- **Dependências** não expõe salas administrativas, sala de recursos multifuncionais (AEE!),
  almoxarifado, nem os **"Espaços Escolares"** (pátio, parque, brinquedoteca, auditório, horta,
  estacionamento, quadra esportiva).
- **Equipamentos** não expõe `qtd_extintores`/`qtd_cameras` nem kits/instrumentos.
- **Geral** não expõe `sigla, situacao_funcionamento, distrito, latitude/longitude`, toda a
  **Vinculação/Mantenedora** e toda a **Equipe gestora**.
- **Recursos** (material didático, acervo, programas governamentais): **sem UI em nenhuma aba**.

**Conclusão E2:** a interface expõe **59%** do modelo. Os 41% ocultos concentram-se justamente
em infraestrutura de segurança, conservação, espaços e dados administrativos oficiais.

---

## ENTREGA 3 — Auditoria da Infraestrutura Escolar
| Dimensão | Modelo | Interface | Diagnóstico |
|---|---|---|---|
| Água (forma) | ✅ | ✅ | OK |
| Água (potabilidade) | ❌ | ❌ | **Lacuna de modelo** (MP recorrente) |
| Esgoto/saneamento | ✅ (texto) | 🟨 oculto | Existe, invisível; falta tipificar |
| Coleta de lixo | ✅ (texto) | 🟨 oculto | Existe, invisível; falta tipificar |
| Energia | ✅ | ✅ | OK |
| Acessibilidade | ✅ | parcial (falta contagem) | Bom; expor `banheiros_acessiveis` |
| Segurança/incêndio | ✅ | ❌ oculto (seção inexistente) | **Dado existe, sem tela** |
| Conservação/cercamento | ✅ | ❌ oculto (seção inexistente) | **Dado existe, sem tela** |
| Conectividade | ✅ | parcial | Expor `cobertura_rede` |
| Dependências/ambientes | ✅ (rico) | parcial | Expor salas admin, AEE, espaços |
| Obras/reformas | ❌ | ❌ | **Lacuna de modelo** |
| Conformidade legal (alvará/AVCB/vigilância) | ❌ | ❌ | **Lacuna de modelo** |
| Metragem/ano de construção/regime de ocupação | ❌ | ❌ | **Lacuna de modelo** |

**Conclusão E3:** a infraestrutura está **majoritariamente modelada**, mas **subutilizada**
por falta de telas. Lacunas reais de modelo = obras, conformidade legal, potabilidade,
tipificação de esgoto/lixo e metragem/ocupação.

---

## ENTREGA 4 — Cruzamento com exigências MP / FNDE / INEP
Matriz completa em `MATRIZ_MP_FNDE_SIGESC.md`. Consolidação:

| Situação | Requisitos | % |
|---|---|---|
| ✅ Coberto (modelo + UI) | ~13 | ~29% |
| 🟨 No modelo, falta expor na UI | ~24 | ~44% |
| ❌ Ausente (falta no modelo) | ~18 | ~27% |

**Baseline:** Censo Escolar/Educacenso 2026 (Caracterização e Infraestrutura). **Complemento
MP/TCE** (achados recorrentes): água potável/certificado de potabilidade, coleta de esgoto,
banheiros, prevenção de incêndio — todos com campo já existente no modelo (exceto potabilidade
e AVCB documental).

**Conclusão E4:** **~44% dos requisitos já estão no banco** (só precisam de UI). O SIGESC está
**mais perto do que parecia** de responder MP/FNDE — a barreira é UX + relatório, não dados.

---

## ENTREGA 5 — Proposta de Evolução (SSoT — tudo sobre `schools`, sem módulo novo)
> Respeita `ARCHITECTURE_BASELINE.md` §3.1 (reuso) e §3.7 (não duplicar representação).
> **Não criar** "Módulo de Infraestrutura" — a infraestrutura é atributo da escola.

**Fase A — UX / Exposição (baixo risco, alto impacto) — SEM mudança de modelo**
1. Na aba **Infraestrutura**, criar as seções **Serviços** (adicionar `saneamento`,
   `coleta_lixo`), **Segurança** (`saidas_emergencia, extintores, brigada_incendio,
   plano_evacuacao, qtd_cameras`) e **Conservação** (`estado_conservacao, possui_cercamento`);
   adicionar `cobertura_rede` em Conectividade e `banheiros_acessiveis` em Acessibilidade.
2. Na aba **Dependências**, expor salas administrativas, `salas_recursos_multifuncionais`
   (AEE), `possui_almoxarifado` e a seção **Espaços Escolares** (pátio/parque/brinquedoteca/
   auditório/horta/estacionamento/quadra esportiva).
3. Na aba **Geral**, expor `sigla, situacao_funcionamento, distrito, latitude/longitude`,
   **Vinculação/Mantenedora** e **Equipe gestora**.
4. Nova aba (ou seção) **Recursos**: `possui_material_didatico, tamanho_acervo,
   participa_programas_governamentais, turnos_funcionamento, organizacao_turmas, tipo_avaliacao`.

**Fase B — Relatório Institucional (SSoT de leitura) — NOVO endpoint de leitura + PDF**
5. `GET /api/schools/{id}/infra-report` (e versão consolidada por mantenedora) →
   **relatório de infraestrutura** (tela + PDF em `backend/pdf/`) no padrão institucional já
   existente (brasão/cabeçalho), respondendo em 1 clique demandas de MP/TCM/FNDE. Apenas
   **consome** dados de `schools` (sem recálculo — coerente com o futuro Motor de Indicadores).

**Fase C — Evolução pontual do modelo (os ❌) — requer governança de migração (§3.2)**
6. Adicionar a `SchoolBase` (aditivo, retrocompatível, tudo `Optional`):
   - Água: `agua_potavel: bool`, `certificado_potabilidade: bool` (+ validade).
   - Esgoto: `tipo_esgotamento: Literal[...]`; Lixo: `tipo_destinacao_lixo: Literal[...]`.
   - Ocupação: `regime_ocupacao: Literal['proprio','alugado','cedido',...]`, `predio_compartilhado: bool`.
   - Metragem: `area_terreno_m2`, `area_construida_m2`, `ano_construcao`.
   - Conformidade: `alvara_funcionamento`, `licenca_sanitaria`, `avcb_bombeiros`, `habite_se` (bool + validade/anexo).
   - Obras: sub-documento `obras: List[Obra]` (situação, tipo, valor, `fonte_recurso` PAR/FNDE/PDDE, datas).
   - Alimentação: `fornece_alimentacao: bool`.
7. Migração aditiva (nenhum campo existente alterado) → risco baixo; ainda assim seguir §3.2
   (auditoria + dry-run + rollback), consistente com o padrão `with_critical_mutation`.

**Ordem recomendada:** A → B → C (entrega valor imediato antes de tocar no schema).

---

## ENTREGA 6 — Resultado esperado (Go/No-Go)
- **Confirmação da hipótese:** ✅ A oportunidade principal é **interface + relatórios**, não
  ampliação massiva do modelo. Ampliação de modelo é **cirúrgica** (Fase C, ~18 campos/subdocs).
- **Prontidão para órgãos de controle:** **parcial hoje** — dado majoritariamente existe, mas
  há dois bloqueios: (a) campos não editáveis na UI ficam vazios na prática; (b) não há
  relatório/exportação. **Resolver A+B destrava resposta rápida a MP/FNDE/TCM.**
- **SSoT preservado:** toda evolução ocorre sobre a coleção `schools`; nenhum módulo paralelo;
  relatórios apenas **consomem** o dado.
- **Nada foi alterado nesta sprint** (READ-ONLY). Aguardando decisão do owner para priorizar
  Fase A / B / C.

---

### Ação pendente do owner
Aprovar a ordem A → B → C (ou repriorizar). Nenhuma implementação inicia sem o "sim" explícito,
conforme as regras de sprint e a governança de migração (§3.2).

*Última atualização: Jun/2026 — Sprint READ-ONLY Auditoria do Cadastro de Escolas – SIGESC.*
