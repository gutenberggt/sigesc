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
- [x] **Tabela agrupada por data**: Registros consolidados por data em uma única linha (4 colunas: DATA | COMPONENTES+CONTEÚDO | METODOLOGIA | AULAS). Metodologias duplicadas deduplicadas.
- [x] **Cancelamento de matrícula**: Ao cancelar, deleta matrícula, remove aluno de frequências/notas, seta status 'inactive' e limpa escola/turma

### Sessão 2026-03-21
- [x] **Bloqueio de notas por data de matrícula/movimentação**: Backend retorna `blocked_before_enrollment` e `blocked_after_action` por aluno. Frontend desabilita inputs por bimestre conforme regras:
  - Bimestres antes da matrícula → bloqueado para professor, liberado para admin/secretário
  - Bimestres após transferência/desistência → bloqueado para todos
  - Exibe data de matrícula do aluno na listagem
  - Corrigido bug: variável `enrollment_dates` não definida no endpoint
- [x] **Bug fix: enrollment_date não salva na matrícula**: Ao usar ação "Matricular" (re-ativação de aluno), o `enrollment_date` não era propagado para o enrollment nem para o student. Corrigido frontend (envia enrollment_date no updateData) e backend (usa a data informada pelo usuário ao criar enrollment).
- [x] **Bloqueio de frequência por data**: Avisos e desabilitação antes da matrícula e após transferência (sessão anterior)
- [x] **PDF Relatório de Notas**: Endpoint e botão corrigidos
- [x] **Filtro Ano/Série em Notas**: Para turmas multisseriadas
- [x] **Campo Data da Matrícula**: Na edição do aluno (aba Turma/Observações)
- [x] **Limpeza retroativa de matrículas**: Rota de manutenção e botão admin


### Sessão 2026-02-XX
- [x] **Geração de documentos para alunos transferidos**: Boletim Escolar e Ficha Individual agora podem ser gerados para alunos com status `transferred`. O resultado exibe "TRANSFERIDO(A)" no campo de resultado final do PDF. Impressão em lote também inclui alunos transferidos.
- [x] **Ficha Individual dupla para remanejamento**: Quando o aluno foi remanejado dentro da mesma escola, a Ficha Individual gera 2 páginas: Página 1 com dados da turma de destino (notas e frequências combinadas) e Página 2 com dados da turma de origem (apenas notas/frequências da origem). Detecta automaticamente matrículas com status `relocated` na mesma escola e ano letivo.
## Backlog Pendente
### P0
- [x] ~~Bug de exclusão de frequência~~ (RESOLVIDO)
- [x] ~~Bloqueio de notas por data de matrícula/movimentação~~ (RESOLVIDO)
- [x] ~~Geração de Boletim/Ficha Individual para alunos transferidos~~ (RESOLVIDO)

### P1
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar permissões em hook usePermissions
- [ ] Extrair multi-select para componente reutilizável
- [ ] Modularizar pdf_generator.py (dividir por tipo de relatório)
