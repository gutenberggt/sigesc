# Diário por Vínculo Docente — Fase 3: Meus Diários

## 1. Objetivo

A Fase 3 introduz a camada organizadora **Meus Diários** no painel do professor.

Ela não substitui Frequência, Notas/Conceitos, Registro de Conteúdos, PDFs ou AEE. Sua função é apresentar ao professor, de forma segura, os vínculos DVD que estão vigentes e explicitamente habilitados em `teacher_class_assignments`.

## 2. Fonte de verdade

A listagem DVD usa exclusivamente `teacher_class_assignments`.

O endpoint `/api/professor/diarios` nunca aceita `teacher_id` fornecido pelo cliente: o proprietário candidato é sempre derivado do usuário autenticado.

Cada assignment candidato é revalidado por `authorize_assignment_access(...)`, preservando os guardrails da Fase 1:

- vínculo existente e não excluído;
- `diary_settings.enabled=true`;
- vigência temporal;
- escola da turma;
- tenant fail-closed;
- propriedade pedagógica do professor;
- escopo educacional DVD v1;
- exclusão de AEE;
- capabilities derivadas do perfil canônico.

## 3. Compatibilidade com o legado

O endpoint já existente `/api/professor/turmas` continua usando `teacher_assignments` e não foi substituído nesta fase.

A seção **Minhas Turmas**, seus atalhos e o fluxo AEE permanecem inalterados. Isso permite que a implantação do DVD seja gradual: vínculos não habilitados continuam no comportamento atual, enquanto vínculos DVD habilitados passam a aparecer adicionalmente em **Meus Diários**.

## 4. O que o card mostra

Cada card representa exatamente um `assignment_id` e apresenta:

- escola;
- turma;
- componente, quando específico;
- vigência;
- perfil (`regular`, `integrator` ou `shared`);
- escopo de estudantes (`all` ou `group`);
- capacidades efetivas de Conteúdos, Frequência e Avaliação.

As capacidades são derivadas do contrato da Fase 0; não são duplicadas em banco.

## 5. Ações deliberadamente não habilitadas

A Fase 3 não adiciona botões operacionais dentro dos cards.

Esse bloqueio é intencional: um card só poderá abrir uma tela pedagógica quando essa tela estiver efetivamente integrada a `assignment_id`. Assim, a camada organizadora não cria um atalho para um fluxo legado que ainda não respeite a propriedade pedagógica do vínculo.

### 5.1 Conteúdos — GAP encontrado durante a Fase 3

A Fase 2 tornou `content_entries` assignment-aware e criou autorização por vínculo/snapshot histórico.

Porém, a tela atualmente usada pelo professor, `LearningObjects.js`, ainda chama `learningObjectsAPI`, cujos endpoints são `/api/learning-objects`, e o router correspondente continua lendo/escrevendo a coleção legada `learning_objects` e validando professor por `teacher_assignments`.

Consequência: a proteção criada na Fase 2 existe no backend novo, mas a UI atual de Objetos de Conhecimento ainda não está harmonizada com esse caminho canônico.

Portanto, **Meus Diários não anuncia Conteúdos como operacional por vínculo nesta fase**. Antes de habilitar o botão de Conteúdos no card, deve haver uma etapa de harmonização da tela/API atual com `content_entries`/`assignment_id`, sem criar `LearningObjectsV2.js`.

### 5.2 Frequência

A capability é exibida conforme o perfil:

- `regular`: `class_daily` / `official`;
- `integrator`: `assignment_session` / `pdf_only`, opcional;
- `shared`: `assignment_session` / `official`.

A tela operacional por vínculo permanece para a Fase 4.

### 5.3 Avaliação

A capability é exibida conforme o perfil, sem alterar o regime avaliativo da etapa. A integração operacional por `assignment_id` permanece para a Fase 5.

## 6. AEE

AEE não foi modificado. O fluxo e os cards AEE existentes no `ProfessorDashboard` permanecem exatamente separados do DVD.

## 7. Segurança

Invariantes da Fase 3:

1. professor não escolhe `teacher_id` para listar diários;
2. assignment de outro professor não entra como candidato;
3. vínculo desabilitado, expirado ou soft-deleted não aparece como diário ativo;
4. AEE e etapas fora do DVD v1 falham fechado;
5. escola e mantenedora continuam obrigatórias segundo a autorização central;
6. `blocked_total` informa que existem vínculos candidatos rejeitados sem expor dados de outro vínculo;
7. nenhum card concede capacidade que não exista no contrato canônico;
8. a existência visual de uma capability não equivale a liberação da tela operacional.

## 8. Testes

A Fase 3 adiciona `backend/tests/test_teacher_diaries_phase3.py` com proteção para:

- vínculo próprio vigente;
- enriquecimento de turma/escola/componente;
- capabilities de `regular`;
- `integrator` com frequência opcional `pdf_only` e sem avaliação;
- `shared` com `student_scope=group`;
- AEE fail-closed;
- tenant incompatível fail-closed;
- filtro de ano letivo;
- vínculo desabilitado/expirado;
- assignment de outro professor;
- vínculo class-wide sem componente inventado;
- usuário sem identidade.

O job obrigatório **Backend - Diário por Vínculo guards** foi mantido com o mesmo nome exigido pelo ruleset da `main` e passa a incluir também a suíte da Fase 3.

## 9. Fora do escopo

Não entram nesta fase:

- escrita/migração de `teacher_assignments` para `teacher_class_assignments`;
- alteração de Frequência;
- alteração de Notas/Conceitos;
- alteração de PDFs;
- backfill histórico;
- alteração do AEE;
- remoção das páginas ou atalhos atuais;
- criação de telas `V2`.

## 10. Próxima decisão técnica

Antes de habilitar **Conteúdos** dentro de Meus Diários, recomenda-se harmonizar a tela atual `LearningObjects.js` com o backend canônico `content_entries` da Fase 2. Essa harmonização deve preservar a página atual e eliminar o caminho paralelo de persistência, em vez de criar uma nova tela.
