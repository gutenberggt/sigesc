# Diário por Vínculo Docente v1.0 — Fase 1 — Implementação

**Status:** implementação aditiva, sem conexão aos módulos pedagógicos  
**Branch:** `agent/diario-vinculo-fase1`  
**Base:** `main` em `4fc64690637b9c41fe93de9c5762e17d20054d3d`

## 1. Objetivo

Evoluir `teacher_class_assignments` para carregar, de forma opcional e auditável, a configuração do Diário por Vínculo Docente (DVD), e criar uma autorização central capaz de decidir se um usuário pode atuar em um vínculo específico.

A Fase 1 NÃO conecta o novo mecanismo aos módulos de Frequência, Notas, Conteúdo ou PDFs. Esses consumidores serão integrados gradualmente nas fases seguintes.

## 2. Estratégia de compatibilidade

`diary_settings` é **opcional**.

- vínculo legado sem `diary_settings`: continua no comportamento atual;
- ausência do campo não ativa DVD implicitamente;
- `diary_settings: {}` também **não ativa** o DVD: `enabled` tem default `false`;
- ativação exige `diary_settings.enabled=true` de forma explícita;
- novo vínculo fora do escopo continua podendo ser criado normalmente sem DVD;
- tentativa de habilitar DVD fora do escopo aprovado é bloqueada;
- AEE permanece explicitamente fora do escopo.

Não há backfill nem migração nesta fase.

## 3. Schema aditivo

Quando configurado, o vínculo pode receber:

```json
{
  "diary_settings": {
    "enabled": true,
    "schema_version": 1,
    "profile": "regular | integrator | shared",
    "student_scope": "all | group"
  }
}
```

As capabilities não são persistidas. Elas continuam derivadas do contrato canônico da Fase 0:

- `regular`: conteúdo + frequência `class_daily/official` + avaliação;
- `integrator`: conteúdo + frequência opcional `assignment_session/pdf_only`, sem avaliação;
- `shared`: conteúdo + frequência `assignment_session/official` + avaliação.

`student_scope=group` é aceito somente em `shared`.

## 4. Escopo educacional

DVD habilitável apenas para:

- Educação Infantil;
- 1º ao 5º Ano do Ensino Fundamental;
- EJA 1ª e 2ª Etapa.

Ficam fora:

- 6º ao 9º Ano;
- EJA 3ª e 4ª Etapa;
- Ensino Médio/outros;
- AEE.

A criação de um `teacher_class_assignment` nessas etapas fora do DVD não é bloqueada. O guardrail atua somente na tentativa de habilitar `diary_settings.enabled=true`.

## 5. Evolução do router

`AssignmentCreate` e `AssignmentUpdate` passam a aceitar `diary_settings` opcional.

A listagem recebe filtros aditivos:

- `diary_enabled`;
- `diary_profile`.

Criação e atualização de `diary_settings` são registradas na auditoria já existente do vínculo.

Nenhum endpoint pedagógico passa a usar o novo campo nesta fase.

## 6. Serviço central de autorização

Novo arquivo:

`backend/services/diary_assignment_access.py`

Função canônica:

`authorize_assignment_access(...)`

A autorização valida, em conjunto:

1. existência do vínculo e `deleted=false`;
2. coerência opcional com turma/componente esperados;
3. existência da turma;
4. escopo educacional aprovado e exclusão do AEE;
5. coerência entre `assignment.school_id` e a escola real da turma;
6. `diary_settings.enabled=true`;
7. vigência temporal do vínculo;
8. acesso à escola, usando a turma como fonte de verdade;
9. compatibilidade de mantenedora;
10. propriedade do vínculo pelo usuário **e manutenção de papel pedagógico compatível**;
11. capability do perfil para a ação solicitada.

O guardrail de tenant segue o padrão global do SIGESC: para qualquer usuário que não seja `super_admin`, ausência de `mantenedora_id` no usuário ou no recurso é **fail-closed** e resulta em negação.

Para `super_admin`:

- sem tenant ativo informado ao serviço: comportamento cross-tenant intencional da plataforma;
- com `active_mantenedora_id`: acesso fica restrito ao tenant ativo informado pelo consumidor.

## 7. Gestão e override

Gestão pode visualizar vínculos consolidados respeitando escola/tenant.

Escrita gerencial NÃO é implícita. Para um consumidor futuro permitir correção administrativa, deverá chamar o serviço com `allow_management_override=true`; mesmo assim, a capability do perfil continua obrigatória.

Exemplo: nem um coordenador com override poderá lançar notas em vínculo `integrator`.

## 8. Professor e anti-spoof

Para ações pedagógicas, conhecer ou enviar `teacher_id`/`assignment_id` não concede acesso.

O serviço resolve o documento real do vínculo e exige simultaneamente:

- `assignment.teacher_id == current_user.id`; e
- papel atual em `professor`, `coordenador` ou `apoio_pedagogico` para exercer propriedade pedagógica.

Assim, um usuário que historicamente foi professor mas passou a um papel administrativo não conserva escrita no diário apenas porque seu ID permanece no vínculo antigo.

Também pode receber `expected_class_id` e `expected_component_id`, impedindo que o frontend reutilize um assignment válido em outra turma/componente.

A escola real da turma é autoritativa. Se um documento de assignment legado ou inconsistente trouxer `school_id` divergente, o acesso falha com erro estável em vez de usar o snapshot incorreto para autorizar a escola.

## 9. Legado e ativação futura

A ausência de `diary_settings` resulta em `DVD_NOT_ENABLED` no novo serviço.

Isso é intencional: enquanto os módulos atuais ainda não chamam o serviço, nada muda; quando forem integrados, somente vínculos explicitamente ativados ou migrados entrarão no novo regime.

Configuração inválida de `diary_settings` não é silenciosamente tratada como legado: valores malformados geram erro estável de autorização.

## 10. Testes

Novo arquivo:

`backend/tests/test_diary_assignment_access_phase1.py`

A suíte específica da Fase 1 possui **24 testes** e cobre:

- vínculo legado não ativado implicitamente;
- `enabled=false` como default do payload HTTP;
- configuração malformada não mascarada como legado;
- validade temporal;
- propriedade do professor;
- perda de propriedade de escrita quando o usuário deixa de ter papel pedagógico;
- regular com todas as capabilities;
- integrador com frequência opcional `pdf_only` e sem notas;
- shared com `student_scope=group`;
- bloqueio de AEE;
- bloqueio de Anos Finais;
- visão consolidada da gestão;
- escrita gerencial somente com override explícito;
- escola e tenant;
- fail-closed quando usuário não-super_admin não possui tenant;
- fail-closed quando o recurso não possui tenant resolvível;
- exceção cross-tenant intencional do `super_admin` sem escopo;
- restrição do `super_admin` quando há tenant ativo;
- divergência entre escola do assignment e escola real da turma;
- mismatch de turma/componente.

Somada aos **54 testes da Fase 0**, a execução canônica do DVD possui **78 testes de proteção**.

## 11. CI

O workflow `CI - Build & Lint` ganha um job dedicado:

`Backend - Diário por Vínculo guards`

Ele executa automaticamente, em todo PR/push para `main`:

- `test_diary_assignment_contract_phase0.py`;
- `test_diary_assignment_access_phase1.py`.

A execução é isolada do `tests/conftest.py` de integração e define `PYTHONPATH=.` explicitamente, pois estes guards são testes unitários puros e não dependem de MongoDB.

Assim, os guardrails do DVD deixam de depender de validação manual.

## 12. O que NÃO muda nesta fase

- nenhuma coleção histórica é migrada;
- nenhuma frequência ganha `assignment_id`;
- nenhuma nota/conceito ganha `assignment_id`;
- nenhum conteúdo ganha `assignment_id`;
- nenhum PDF é alterado;
- nenhuma tela é alterada;
- nenhuma regra de avaliação é alterada;
- AEE não é alterado;
- os endpoints atuais de Frequência/Notas/Conteúdo ainda não usam a autorização central.

## 13. Gate para Fase 2

A Fase 2 só deve começar após:

- **78/78** testes Fase 0 + Fase 1 verdes no GitHub Actions;
- `ruff` e `compileall` verdes;
- regressão existente verde;
- diff revisado sem alterações pedagógicas acidentais;
- validação explícita de que vínculos legados continuam funcionando sem `diary_settings`.
