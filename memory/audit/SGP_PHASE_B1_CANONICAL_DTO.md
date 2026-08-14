# Fase B.1 — DTO Canônico Student + Enrollment para o MIG

Data: 2026-08-14  
Status: **implementação em branch; sem envio real ao MEC/SGP/CMDE**

## 1. Objetivo

Criar uma representação canônica e agnóstica de provider para os dados de `Student` + `Enrollment` utilizados pela camada MIG antes de qualquer tradução para o contrato CMDE.

A B.1 implementa somente o primeiro item da Fase B definida em `SGP_STUDENT_CANONICAL_MAPPING.md`.

## 2. Decisão arquitetural

O contrato foi criado em:

`backend/mig/core/canonical_student.py`

A localização em `mig/core` é intencional. Os DTOs existentes em `mig/cmde/dtos.py` permanecem específicos do provider CMDE; o novo contrato canônico não contém código, enum, payload ou regra específica do MEC.

Fluxo arquitetural alvo:

`SIGESC SSoT -> DTO canônico MIG -> tabelas de conversão -> mapper/provider CMDE`

A B.1 implementa apenas os dois primeiros elementos até o DTO canônico. As tabelas e o mapper ficam para B.2/B.3.

## 3. Contratos introduzidos

- `CanonicalStudentAddressDTO`
- `CanonicalStudentDTO`
- `CanonicalEnrollmentDTO`
- `CanonicalStudentEnrollmentDTO`
- `build_canonical_student_enrollment(...)`

Versão inicial do contrato:

`student-enrollment.v1`

## 4. Invariantes

1. Nenhum campo CMDE é armazenado no DTO canônico.
2. Nenhum valor desconhecido é substituído por zero, `False`, string vazia ou outro default fictício.
3. String vazia de origem é normalizada para `None`.
4. `None` permanece semanticamente distinto de `False`.
5. Endereço legado que não seja objeto estruturado não é interpretado nem convertido.
6. Códigos IBGE somente são transportados quando já estão explicitamente armazenados no endereço; não há inferência por texto de UF/município.
7. Categorias históricas de comunidade tradicional presentes em `color_race` não são aceitas como raça/cor canônica.
8. `traditional_community` permanece dimensão separada e `quilombola` somente é derivado de `comunidade_tradicional` canônica.
9. `has_disability`, TDAH, dislexia ou outros transtornos não geram `student_with_disability` na B.1. O campo permanece `None` até existir tabela oficial confirmada.
10. IDs internos e externos são campos distintos e nunca se substituem.
11. O vínculo Student/Enrollment é validado: `enrollment.student_id` deve coincidir com `student.id`.
12. A série efetiva usa `Enrollment.student_series` quando presente e, somente na ausência, `Class.grade_level`.

## 5. IDs externos

`Enrollment` já possui `sgp_enrollment_id` no modelo atual e o DTO apenas o transporta quando existente.

O modelo `Student` ainda não possui persistência formal de `sgp_student_id`. A B.1 inclui o campo opcional no contrato para manter separação semântica entre ID interno e externo, mas **não altera o modelo Student, não cria índice e não grava esse ID**. A persistência formal pertence à B.5.

## 6. Endereços legados

Após o fechamento operacional da A2, o backfill IBGE atualizou 2.315 registros estruturados e identificou 3.679 registros com endereço legado não estruturado.

A B.1 não tenta migrar esses 3.679 registros. Quando um `student.address` não é um objeto estruturado, `CanonicalStudentDTO.address` fica `None`. O validador de prontidão da B.4 será responsável por indicar a ausência de dados necessários para cada tipo de lote.

## 7. Campos deliberadamente não resolvidos na B.1

- códigos oficiais de sexo, raça/cor, nacionalidade, localização e situação da matrícula;
- tabela oficial de deficiência/condições;
- regra contratual de matrícula integral;
- códigos de etapa de ensino CMDE;
- responsável legal e código de vínculo;
- qualquer dado clínico/saúde;
- prontidão por tipo de lote;
- persistência formal de `sgp_student_id`;
- envio, fila, scheduler ou provider real.

## 8. Testes de aceitação

Arquivo:

`backend/tests/test_mig_canonical_student.py`

Coberturas:

1. projeção estável de registro completo;
2. desconhecidos permanecem `None` e não recebem defaults fictícios;
3. comunidade tradicional não vira raça/cor;
4. `has_disability` + TDAH/dislexia não criam deficiência oficial;
5. códigos IBGE não são inferidos por texto;
6. IDs internos e externos permanecem separados;
7. série efetiva segue regra determinística;
8. matrícula vinculada a outro estudante é rejeitada.

## 9. Fora de escopo / próximos passos

### B.2
Tabelas explícitas SIGESC -> CMDE, baseadas somente no contrato oficial vigente.

### B.3
Mapper CMDE consumindo o DTO canônico e as tabelas B.2, sem defaults fictícios.

### B.4
Validador de prontidão por tipo de lote, incluindo endereço estruturado/IBGE e demais obrigatoriedades contratuais.

### B.5
Persistência separada e governada dos IDs externos SGP.

### B.6
Preview/dry-run end-to-end antes de qualquer provider real.

## 10. Segurança operacional

A B.1 não altera feature flags, não habilita scheduler, não envia requisições externas e não modifica dados de produção.
