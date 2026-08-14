# Fase B.4 — Validador de Prontidão por Tipo de Lote CMDEB

Data da verificação: 2026-08-14  
Status: implementação isolada; **nenhum envio real ao MEC**.

## 1. Objetivo

Criar um gate determinístico entre o contrato canônico B.1 / tabelas B.2 / serializer B.3 e qualquer futuro preview ou provider real.

A B.4 responde, antes de gerar ou enviar um lote:

- qual tipo de lote está sendo avaliado;
- qual endpoint CMDE corresponde ao tipo;
- se cada registro está pronto;
- quais campos bloqueiam a interoperabilidade;
- quais campos são apenas recomendados para enriquecer o payload;
- quantos registros de um lote estão prontos ou bloqueados.

O validador é puro: não consulta MongoDB, não usa HTTP, não chama fila, worker, scheduler nem feature flag.

## 2. Fonte oficial consultada

Documentação oficial CMDEB v2 (MEC Gestão Presente), versão pública observada **2.0.0**, verificada em 2026-08-14:

- Swagger produção: `https://api-cmde2.gestaopresente.mec.gov.br/docs`
- ReDoc homologação: `https://api-cmde2.hmg.gestaopresente.mec.gov.br/redoc`

A documentação confirma processamento assíncrono por lote e publica, entre outros, estes contratos Student/Enrollment:

| Tipo interno B.4 | Endpoint oficial |
|---|---|
| `student_without_class_create` | `POST /api/v2/estudantes/sem-turma/cadastro/lote` |
| `student_with_class_create` | `POST /api/v2/estudantes/com-turma/cadastro/lote` |
| `student_edit` | `PUT /api/v2/estudantes/edicao/lote` |
| `enrollment_class_assignment` | `POST /api/v2/matriculas/enturmacao/lote` |
| `enrollment_class_assignment_edit` | `PUT /api/v2/matriculas/enturmacao/edicao/lote` |
| `enrollment_edit` | `PUT /api/v2/matriculas/edicao/lote` |
| `enrollment_movement` | `PUT /api/v2/matriculas/movimentacao/lote` |
| `enrollment_confirm_completion` | `PUT /api/v2/matriculas/confirmar-conclusao/lote` |

## 3. Escopo implementado na B.4

O único perfil de prontidão efetivamente habilitado nesta etapa é:

`student_without_class_create`

Isso acompanha exatamente o serializer implementado na B.3. Os demais endpoints oficiais são registrados para roteamento futuro, porém retornam `unsupported_lot_type` até que possuam contrato canônico/serializer/testes próprios.

Tipo completamente desconhecido retorna `unknown_lot_type`.

Essa escolha é intencionalmente fail-closed.

## 4. Perfil mínimo de prontidão — cadastro de estudante sem turma

A B.4 não usa exemplos da documentação como pretexto para inventar defaults. O perfil mínimo do MIG exige informação suficiente para identificar o estudante, a matrícula, a escola e a territorialidade sem inferência aproximada.

### 4.1 Bloqueadores por ausência

- `student.full_name`;
- `student.cpf`;
- `student.birth_date`;
- `enrollment.enrollment_number`;
- `enrollment.enrollment_date`;
- `enrollment.academic_year`;
- `school.school_inep_code`;
- endereço estruturado `student.address`;
- `student.address.state_ibge_code`;
- `student.address.city_ibge_code`.

Os códigos IBGE são exigidos no gate SIGESC para impedir inferência de município/UF por texto livre no momento de interoperabilidade.

### 4.2 Validações de formato

- CPF: 11 dígitos;
- código INEP: 8 dígitos;
- código IBGE UF: 2 dígitos;
- código IBGE município: 7 dígitos;
- CEP, quando informado: 8 dígitos;
- datas: apenas `DD/MM/AAAA` ou `AAAA-MM-DD`;
- ano da matrícula: intervalo operacional 1900–2100.

A B.4 valida estrutura/formato; não substitui eventual validação cadastral externa de CPF ou regras de negócio do MEC.

## 5. Avisos não bloqueantes

Quando ausentes, os itens abaixo geram `recommended_missing`, mas não tornam o registro automaticamente inapto:

- nome da escola;
- CEP;
- bairro;
- logradouro;
- número do endereço.

A distinção evita declarar como obrigatória uma propriedade que a documentação pública não apresentou de forma inequívoca como requisito interno do objeto, ao mesmo tempo em que permite medir qualidade do payload.

## 6. Integração com as tabelas B.2

Se um valor canônico está presente e sua equivalência CMDE ainda não está oficialmente habilitada, a prontidão falha com `unverified_mapping`.

Dimensões cobertas:

- sexo;
- raça/cor;
- nacionalidade;
- quilombola;
- apoio pedagógico;
- etapa de ensino;
- localização geográfica;
- localização diferenciada;
- estudante com deficiência.

### 6.1 Localização geográfica e diferenciada

A B.4 adiciona explicitamente o gate para `student.address.geographic_location` e `student.address.differentiated_location`.

Isso impede que um valor conhecido pelo SIGESC seja simplesmente omitido do payload enquanto as tabelas B.2 correspondentes estiverem bloqueadas. O valor `None` continua representando dado desconhecido e não recebe default.

## 7. Integração com o serializer B.3

Depois das verificações específicas, e somente se nenhum bloqueador já tiver sido encontrado, a B.4 chama o mapper B.3 como última guarda de compatibilidade.

Se o serializer ainda recusar o registro, o relatório recebe `serialization_blocked`.

A B.4 não retorna o payload. A geração visual/operacional do payload pertence à Fase B.6 (preview/dry-run).

## 8. Diagnóstico e minimização de dados

O relatório por registro contém:

- `student_id` interno;
- `enrollment_id` interno;
- tipo de lote;
- endpoint;
- versões do contrato/serializer/readiness;
- `ready`;
- contagem de bloqueios e avisos;
- lista de problemas com `code`, `field`, `severity` e `message`.

O diagnóstico deliberadamente **não inclui nome, CPF, endereço ou valor que causou o erro**. Isso reduz exposição desnecessária em logs, dashboards e auditorias técnicas.

## 9. Relatório de lote

`validate_cmde_batch_readiness(...)` agrega os relatórios por registro e informa:

- total de registros;
- quantos estão prontos;
- quantos estão bloqueados;
- prontidão global do lote;
- erro explícito para lote vazio.

O lote só é `ready=True` quando existe pelo menos um registro e todos os registros estão prontos.

## 10. Arquitetura implementada

Arquivo principal:

`backend/mig/cmde/readiness.py`

Componentes:

- `CmdeLotType`;
- `CMDE_LOT_ENDPOINTS`;
- `IMPLEMENTED_READINESS_LOT_TYPES`;
- `CmdeReadinessIssue`;
- `CmdeRecordReadinessReport`;
- `CmdeBatchReadinessReport`;
- `validate_cmde_record_readiness(...)`;
- `validate_cmde_batch_readiness(...)`.

## 11. Testes

Arquivo:

`backend/tests/test_cmde_readiness.py`

A suíte cobre:

1. registro pronto no perfil atual;
2. campos mínimos ausentes;
3. CPF e datas inválidos;
4. INEP ausente/inválido;
5. endereço não estruturado;
6. códigos IBGE ausentes/inválidos;
7. CEP informado com formato inválido;
8. warnings para dados complementares ausentes;
9. bloqueio das dimensões B.2 ainda não verificadas;
10. localização geográfica/diferenciada não omitidas silenciosamente;
11. deficiência fail-closed;
12. IDs externos SGP não obrigatórios no cadastro inicial;
13. tipo oficial ainda não implementado;
14. tipo desconhecido;
15. contagens agregadas do lote;
16. lote vazio;
17. diagnóstico sem nome/CPF;
18. catálogo de endpoints Student/Enrollment.

## 12. Fora de escopo

- provider HTTP real;
- autenticação/token Bearer;
- submissão de lote;
- polling/consulta de status;
- fila/worker/scheduler;
- feature flags de envio;
- persistência de IDs externos SGP (B.5);
- preview/dry-run operacional (B.6);
- criação de perfil de prontidão para endpoints que ainda não possuem serializer próprio;
- correção automática de cadastro;
- inferência de códigos CMDE a partir de exemplos.

## 13. Critérios de aceite da B.4

- nenhum tipo de lote desconhecido passa como pronto;
- nenhum tipo oficial ainda não implementado recebe validação aproximada;
- ausência, formato inválido e conversão não verificada são distinguidos;
- valores conhecidos de localização não são omitidos silenciosamente;
- IBGE ausente nunca é inferido no gate;
- relatório não expõe nome/CPF;
- lote vazio não é pronto;
- B.4 não gera payload nem executa efeitos externos;
- registro classificado como pronto no perfil atual também é aceito pelo mapper B.3.
