# SIGESC - Sistema Integrado de Gestão Escolar

## Arquitetura
- **Frontend:** React (CRA) + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python) + MongoDB
- **Auth:** JWT

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007

## Tarefas Concluídas
### Sessão 2026-03-11
- [x] Papel "Auxiliar de Secretaria", Bug PDFs multisseriadas, Dashboard analytics
- [x] Ordenação sem acentos, filtro "Todas as Escolas", seletor de cor mensagem, removida coluna Matrícula

### Sessão 2026-03-12
- [x] Objetos de Conhecimento para Educação Infantil (multi-select Campo de Experiência)

### Sessão 2026-03-13
- [x] Consulta Alunos: "Serie/Turma" → "Ano/Série", corrigido "Nome da Mãe"
- [x] Objetos de Conhecimento: campos como texto fixo separado por hífen
- [x] Frequência Multi-Aula para Anos Finais/EJA
- [x] Alinhamento contagem de alunos no Dashboard

### Sessão 2026-03-16
- [x] Declaração de Transferência (novo documento PDF)
- [x] Correção Ano Letivo (2025 → dinâmico)
- [x] Bug cor mensagem destaque (campo faltante no modelo Pydantic)
- [x] Multi-select de componentes para Anos Iniciais
- [x] `inferEducationLevel()` - detecção robusta do nível de ensino (funciona com ou sem campo education_level)
- [x] Removido campo "Período" da frequência

### Sessão 2026-03-17
- [x] **Resumo de frequência**: 3 campos informativos (Previstos/Registrados/Restantes) com dias ou aulas conforme nível de ensino
- [x] Layout otimizado: Ano Letivo e Turma reduzidos, campos informativos na mesma linha
- [x] Endpoint `GET /api/attendance/attendance-summary/{class_id}` com cálculo de dias/aulas
- [x] **Bug fix**: Corrigido bug no box informativo de frequência que não mostrava dados em produção (coleção `school_calendar` → `calendario_letivo`, adicionado cálculo de dias letivos a partir dos períodos bimestrais)
- [x] **Alertas professor**: Filtro no endpoint `/api/attendance/alerts` para limitar professor às turmas vinculadas via `teacher_assignments`
- [x] **Bug fix**: Corrigido botão "Gerar PDF" em Detalhes da Turma (import faltante de `generate_class_details_pdf` e `logger`)
- [x] **Data da Ação**: Campo de data adicionado aos modais de Matricular, Transferir, Remanejar, Progredir e Cancelar. Migração executada para registros antigos (matrículas: 15/jan, transferências: 10/mar, cancelamentos: 18/jan)
- [x] **Alunos inativos no diário**: Alunos transferidos, remanejados, progredidos, desistentes e cancelados permanecem na listagem da turma de origem com label (Transferido), (Remanejado), etc. Edição de frequência e notas bloqueada a partir da data da ação
- [x] **Remanejamento preserva origem**: Ao remanejar/progredir, matrícula na turma de origem é mantida com status `relocated`/`progressed`, nova matrícula criada na turma destino. Histórico grava `class_id` da turma de ORIGEM
- [x] **Ação "Desistir"**: Nova ação no dropdown com status `dropout`, enrollment atualizado, histórico registrado

### Sessão 2026-03-19
- [x] **10 ajustes no PDF de Objetos de Conhecimento**:
  - Brasão maior (2.5x2.8cm) posicionado à esquerda com texto institucional ao lado
  - Tabela info reestruturada: Professor(a) em células mescladas (Turma+Série/Ano)
  - Total de Registros abaixo de Turno, Total de Aulas abaixo de Nível
  - Data no formato DD/MM (sem ano) na tabela de conteúdos
  - Coluna CONTEÚDO reduzida a 3/4, METODOLOGIA ampliada
  - Registros em ordem cronológica (não mais por componente)
  - Numeração de página "Página X de Y" usando NumberedCanvas

## Backlog Pendente
### P0
- [x] ~~Bug de exclusão de frequência~~ (RESOLVIDO)

### P1
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar permissões em hook usePermissions
- [ ] Extrair multi-select para componente reutilizável
- [ ] Modularizar pdf_generator.py (dividir por tipo de relatório)
