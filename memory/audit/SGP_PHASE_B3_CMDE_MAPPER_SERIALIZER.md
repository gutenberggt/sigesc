# Fase B.3 — Mapper/Serializer canônico → payload CMDEB

Data da verificação: 2026-08-14

## Objetivo

Implementar a primeira tradução efetiva do contrato canônico Student + Enrollment da B.1 para um payload provider-specific CMDEB v2, consumindo as regras fail-closed da B.2 e sem qualquer chamada HTTP, fila, scheduler, feature flag ou envio ao MEC.

## Alvo oficial desta etapa

A B.3 é deliberadamente específica para um único contrato de escrita inicialmente confirmado no ReDoc oficial de homologação CMDEB v2:

- método: `POST`;
- rota: `/api/v2/estudantes/sem-turma/cadastro/lote`;
- processamento: assíncrono por lote;
- envelope de requisição: objeto com `estudantes`, array não vazio.

Fonte oficial verificada em 2026-08-14:

`https://api-cmde2.hmg.gestaopresente.mec.gov.br/redoc`

Versão exibida: **API CMDEB 2.0.0**.

## Campos estruturais observados no contrato público

O request sample oficial de cadastro sem turma expõe, entre outros, os seguintes nomes de campo usados nesta B.3:

- `co_entidade`;
- `co_matricula_rede`;
- `data_inicio_matricula`;
- `estudante_bairro_res`;
- `estudante_cep_res`;
- `estudante_co_municipio_res`;
- `estudante_co_uf_res`;
- `estudante_cpf`;
- `estudante_dt_nascimento`;
- `estudante_email`;
- `estudante_logradouro_res`;
- `estudante_nome`;
- `estudante_nu_endereco_res`;
- `estudante_telefone`;
- `no_entidade`;
- `nu_ano_matricula`.

O sample também apresenta dimensões codificadas como sexo, raça/cor, nacionalidade, quilombola, etapa de ensino e apoio pedagógico. A existência do campo é confirmada; a equivalência semântica SIGESC → código numérico continua subordinada às tabelas B.2.

## Arquitetura implementada

Arquivo principal:

`backend/mig/cmde/student_serializer.py`

### `CmdeStudentSchoolContext`

Contexto explícito da escola vigente, porque o DTO canônico B.1 guarda `school_id`, mas não o código INEP/nome da escola. O serializer não consulta banco e não converte `school_id` interno em código oficial.

Campos:

- `school_inep_code`;
- `school_name`.

### `CmdeStudentWithoutClassRecordDTO`

DTO provider-specific que espelha o subconjunto confirmado do registro CMDEB para cadastro sem turma.

### `map_canonical_student_without_class(...)`

Função pura que recebe:

1. `CanonicalStudentEnrollmentDTO`;
2. contexto escolar opcional e explícito.

Produz `CmdeStudentWithoutClassRecordDTO` ou falha de forma explícita quando a tradução não é semanticamente segura.

### `serialize_student_without_class_batch(...)`

Produz JSON-ready no formato:

```json
{
  "estudantes": [
    {"...": "..."}
  ]
}
```

Campos `None` são omitidos. Não são criados zeros, strings vazias ou valores sentinela para esconder ausência de dado.

## Regras de segurança semântica

### 1. Nenhum ID interno é enviado

Não entram no payload de cadastro:

- `student.student_id`;
- `enrollment.enrollment_id`;
- `enrollment.school_id`;
- `enrollment.class_id`;
- `student.tenant_id`.

O código INEP da escola é fornecido exclusivamente via `CmdeStudentSchoolContext`.

### 2. IDs externos SGP não são usados no cadastro inicial

`sgp_student_id` e `sgp_enrollment_id` permanecem separados e não são serializados neste endpoint de criação. A persistência oficial de IDs externos continua pertencendo à B.5.

### 3. Dimensões B.2 bloqueadas falham fechadas

Se o canônico contiver valor para uma dimensão que o CMDE representa por código, o mapper chama a tabela B.2. Enquanto a legenda estiver `verified=False`, a criação do payload é interrompida.

Aplica-se atualmente a:

- sexo;
- raça/cor;
- nacionalidade;
- quilombola;
- apoio pedagógico;
- etapa de ensino.

Isso é intencional: não omitir silenciosamente um dado conhecido e não usar exemplos do Swagger como se fossem legenda normativa.

### 4. Deficiência continua bloqueada

`student_with_disability` não é convertido. A B.1 não deriva esse campo de `has_disability`, TDAH ou dislexia, e a B.3 mantém essa barreira.

### 5. Datas

O contrato público de requisição usa `DD/MM/AAAA` nos exemplos. O serializer aceita apenas:

- `DD/MM/AAAA`;
- `AAAA-MM-DD`.

O segundo é convertido deterministicamente para `DD/MM/AAAA`. Outros formatos falham; não há interpretação heurística.

### 6. Códigos IBGE

Somente os códigos armazenados no `StudentAddress` canônico são utilizados:

- UF: exatamente 2 dígitos;
- município: exatamente 7 dígitos.

Nunca há lookup ou inferência a partir de `state`/`city` em texto.

### 7. UTF-8

O mapper preserva o texto canônico, inclusive acentos, til e cedilha. Não há transliteração para ASCII, uppercase forçado ou mutação do SSoT.

## O que esta B.3 deliberadamente NÃO faz

- não chama `/api/v2/estudantes/sem-turma/cadastro/lote`;
- não autentica no CMDE;
- não produz ou consulta `lote_id`;
- não usa fila/worker/scheduler;
- não habilita feature flag;
- não implementa cadastro com turma, edição de estudante, enturmação, conclusão ou frequência;
- não decide obrigatoriedade/prontidão campo a campo — isso pertence à B.4;
- não completa as tabelas numéricas ainda bloqueadas — isso continua condicionado a fonte oficial inequívoca;
- não persiste IDs SGP — B.5;
- não implementa preview operacional end-to-end — B.6.

## Testes

Arquivo:

`backend/tests/test_cmde_student_serializer.py`

A suíte cobre:

1. rota alvo explícita;
2. shape exato do envelope `estudantes[]`;
3. mapeamento de campos estruturais confirmados;
4. ausência de IDs internos;
5. preservação de UTF-8;
6. omissão de `None` sem defaults;
7. bloqueio de sexo;
8. bloqueio de raça/cor;
9. bloqueio de nacionalidade;
10. bloqueio de quilombola inclusive `False`;
11. bloqueio de apoio pedagógico;
12. bloqueio de etapa de ensino;
13. barreira de deficiência;
14. validação de IBGE;
15. validação de INEP;
16. datas sem heurística;
17. rejeição de lote vazio;
18. IDs externos SGP fora do cadastro inicial.

## Critério de aceite da B.3

A fase é considerada tecnicamente concluída quando:

- o mapper/serializer é puro e provider-specific;
- produz o envelope oficial sem HTTP;
- não envia IDs internos;
- não cria defaults fictícios;
- dimensões codificadas não confirmadas falham explicitamente;
- UTF-8 é preservado;
- testes focados e gates gerais passam;
- nenhum provider real ou envio ao MEC é ativado.
