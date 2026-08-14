# Fase B.2 — Tabelas explícitas SIGESC → CMDEB

Data da verificação: 2026-08-14

## Objetivo

Criar a camada provider-specific de conversão entre o contrato canônico da B.1 e os códigos numéricos exigidos pelo CMDEB v2, sem acoplar o domínio SIGESC ao MEC e sem inventar equivalências.

## Fonte oficial consultada

- API CMDEB v2 — Swagger/ReDoc oficial do MEC Gestão Presente.
- Versão publicada observada: 2.0.0.
- A API pública confirma processamento assíncrono por lotes e endpoints de estudantes, matrículas, frequência, instituições, turmas, componentes e profissionais.
- O endpoint `GET /api/v2/estudantes` publica explicitamente a legenda de `situacoes_matricula`.

## Catálogo oficial de situação da matrícula

| Código CMDE | Descrição oficial |
|---:|---|
| 0 | Em andamento |
| 1 | Informação Incorreta |
| 2 | Transferência para outra unidade escolar dentro da mesma rede |
| 3 | Transferência para outra unidade escolar em outra rede pública |
| 4 | Transferência para outra unidade escolar em outra rede privada |
| 5 | Transferência para outra rede não identificada |
| 6 | Evasão |
| 7 | Abandono |
| 8 | Óbito Informado |
| 9 | Reclassificação |
| 10 | Aprovado |
| 11 | Concluinte |
| 12 | Reprovado |
| 21 | Transferência entre modalidades (EM <> EJA) |
| 22 | Trancamento de matrícula em curso técnico |

## Conversão SIGESC habilitada

A B.2 habilita somente uma equivalência automática neste momento:

- `Enrollment.status = active` → `estudante_matricula_situacao = 0` (Em andamento).

Isso é semanticamente direto e confirmado pela documentação oficial.

## Estados SIGESC deliberadamente não convertidos automaticamente

- `completed`: o CMDE distingue pelo menos `Aprovado (10)` e `Concluinte (11)`; o status genérico não contém informação suficiente.
- `transferred`: o CMDE possui códigos 2, 3, 4, 5 e 21; é necessário conhecer destino/rede/modalidade.
- `dropout`: o CMDE distingue `Evasão (6)` de `Abandono (7)`.
- `relocated`: não é automaticamente sinônimo de uma das modalidades de transferência CMDE.
- `progressed`: não é automaticamente sinônimo de `Aprovado (10)` nem `Reclassificação (9)`.
- `cancelled`: não há equivalência genérica segura com `Informação Incorreta (1)`.

Qualquer tentativa de converter esses valores gera erro explícito `CmdeCodeMappingError`.

## Dimensões registradas, mas bloqueadas até legenda oficial inequívoca

A API v2 pública expõe os campos e exemplos de payload para as dimensões abaixo, porém a verificação B.2 não encontrou uma legenda pública inequívoca suficiente para habilitar conversão automática:

- `student.sex` → `estudante_sexo`;
- `student.color_race` → `estudante_raca_cor`;
- `student.nationality` → `estudante_nacionalidade`;
- `student.quilombola` → `estudante_quilombola`;
- `student.address.geographic_location` → `turma_localizacao`;
- `student.address.differentiated_location` → localização diferenciada;
- `enrollment.needs_pedagogical_support` → `estudante_apoio_pedagogico`;
- nível+série → `estudante_etapa_de_ensino`.

### Motivo para bloqueio conservador

Exemplos não são usados como legenda normativa. A documentação pública, por exemplo, apresenta `estudante_nacionalidade=1` em payload de cadastro e `estudante_nacionalidade=76` em exemplo de resposta; também há valores diferentes para `estudante_quilombola` entre exemplos. Inferir significado a partir desses exemplos violaria o princípio central do MIG de não inventar dados.

## Arquitetura implementada

Arquivo: `backend/mig/cmde/code_tables.py`.

- `CmdeCodeTable`: descrição imutável de uma dimensão.
- `CMDE_ENROLLMENT_STATUS_CATALOG`: catálogo oficial completo publicado pela API.
- `CMDE_CODE_TABLES`: registro das dimensões da B.1 que exigem tradução CMDE.
- `convert_cmde_code(...)`: conversão fail-closed; `None` permanece `None` e valores não confirmados falham explicitamente.

A B.1 (`mig/core/canonical_student.py`) permanece agnóstica de provider e não recebe códigos MEC.

## Testes

`backend/tests/test_cmde_code_tables.py` valida:

1. `active → 0`;
2. `None` nunca vira default;
3. catálogo oficial de situação da matrícula;
4. statuses SIGESC ambíguos falham;
5. dimensões sem legenda confirmada ficam bloqueadas;
6. `prefere_nao_informar` não é coerced para código binário;
7. tabela/valor desconhecido falham explicitamente;
8. registro B.2 cobre todas as dimensões planejadas da B.1.

## Fora de escopo

- construir payload oficial de estudante/matrícula (B.3);
- readiness validator (B.4);
- persistência de `sgp_student_id` (B.5);
- envio real ou ativação de provider;
- inferência de deficiência a partir de TDAH/dislexia/`has_disability`;
- conversão automática dos endereços legados.

## Critério para ampliar as tabelas

Uma conversão só poderá sair de `verified=False` quando houver legenda oficial inequívoca do CMDEB ou outra fonte normativa oficial explicitamente aplicável ao campo da API. A alteração deve vir acompanhada de teste unitário e registro da fonte/data de verificação.
