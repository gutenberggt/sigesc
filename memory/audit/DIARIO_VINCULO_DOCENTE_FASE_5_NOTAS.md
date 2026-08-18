# Diário por Vínculo Docente — Fase 5: Notas/Conceitos

## Objetivo

Integrar Notas/Conceitos ao Diário por Vínculo Docente (DVD) sem substituir `Grades.js`, sem criar uma coleção paralela de notas e sem alterar os regimes de avaliação já existentes no SIGESC.

## Modelo de autoria

A coleção canônica continua sendo `grades`, com um documento por estudante/turma/componente/ano letivo. Como o mesmo documento contém vários períodos (`b1`…`b4` e recuperações), a autoria pedagógica não é representada por um `assignment_id` único no documento.

A Fase 5 adiciona `grade_ownership`, um mapa por dado avaliativo. Cada campo novo recebe um snapshot imutável do vínculo responsável, incluindo `assignment_id`, professor, turma, componente efetivamente avaliado, escola, mantenedora, profile e versão do contrato.

Campos cobertos: `b1`, `b2`, `b3`, `b4`, `rec_s1`, `rec_s2`, `recovery` e `observations`. `final_average` e `status` continuam derivados pelo motor atual e não recebem autoria manual.

## Invariantes

- `regular`: pode lançar Notas/Conceitos.
- `integrator`: continua sem capability de avaliação.
- `shared/all`: exige um único `teacher_class_assignment` explicitamente marcado com `grades_official_owner=true` para a responsabilidade oficial de avaliação.
- `shared/group`: permanece fail-closed até existir fonte canônica e auditável dos membros do grupo.
- O backend deriva/revalida o vínculo; `assignment_id` recebido do cliente nunca é autoridade.
- Um vínculo só pode reivindicar um campo quando sua vigência intersecta o período pedagógico correspondente.
- Os períodos usam `calendario_letivo`, com prioridade calendário da escola e fallback para calendário geral; datas padrão só são usadas quando não há configuração institucional.
- Valor legado não-nulo sem proveniência nunca é apropriado automaticamente por professor.
- Professor não altera campo pertencente a outro vínculo.
- Correção gerencial preserva a autoria pedagógica existente; `updated_by`/`last_updated_by` são operacionais.
- Nota migrada continua sujeita ao congelamento granular já existente.
- Academic Event Lock e Dependência de Estudos permanecem obrigatórios.
- Nenhum regime de avaliação, escala conceitual ou regra de cálculo é convertido pela Fase 5.

## Leitura e privacidade

Para professor comum, os endpoints DVD mascaram valores e snapshots de autoria pertencentes a outros vínculos. Consultas consolidadas permanecem disponíveis aos perfis gerenciais autorizados.

Quando a média/situação agregada depende de campo pertencente a outro vínculo, o PDF/visão individual do professor não expõe o resultado agregado como se fosse exclusivamente seu.

## Offline

O `sync/push` de `grades` do professor não grava mais a coleção diretamente quando o DVD se aplica: create/update passam pelo mesmo motor de ownership da API; delete offline DVD é recusado.

O `sync/pull` do professor consulta e pagina somente documentos que possuam pelo menos um campo cujo snapshot pertença ao professor autenticado. A filtragem ocorre antes da paginação e permanece tenant-scoped.

Se existir `grade_ownership` histórico mas não houver vínculo ativo compatível para nova escrita, o professor recebe bloqueio fail-closed (`DVD_HISTORICAL_OWNERSHIP_REQUIRES_ACTIVE_ASSIGNMENT`); reconciliação/correção deve ser gerencial.

## PDF

O gerador/layout existente de notas é preservado. A Fase 5 altera somente a seleção dos dados enviados ao gerador quando há contexto DVD, filtrando os campos pelo `assignment_id` autorizado.

## Compatibilidade

- `Grades.js` permanece a tela canônica.
- `/grades` permanece o router canônico.
- Não existe `GradesV2`.
- Sem `assignment_id` e fora de cenário DVD protegido, o fluxo legado permanece.
- O card de “Meus Diários” habilita Avaliação apenas quando a capability permitir; `shared/group` e `shared` sem responsável oficial ficam bloqueados.
- O parâmetro `assignment_id` presente na navegação de “Meus Diários” ainda não é propagado por todas as chamadas internas de `Grades.js`; o backend autorresolve o vínculo próprio apenas quando ele é unívoco. Ambiguidade falha fechado e não é arbitrada.

## Fora do escopo

- backfill automático de `grade_ownership` histórico;
- autoatribuição de autoria por `created_by`/`updated_by`;
- média automática entre co-docentes;
- definição de membros de `shared/group`;
- alteração de AEE;
- alteração dos geradores/layouts PDF;
- alteração dos regimes de avaliação existentes.

## Validação

A Fase 5 só poderá sair de Draft após os required checks da `main`, os guards acumulados DVD, startup completo com MongoDB efêmero/Uvicorn e Gate de Transferência passarem no mesmo head final do PR.