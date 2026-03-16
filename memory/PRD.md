# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Prefeitura Municipal de Floresta do Araguaia.

## Arquitetura
- **Frontend:** React (CRA) + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python) com roteadores modulares
- **Banco:** MongoDB
- **Auth:** JWT (access + refresh tokens)

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007

## Tarefas Concluídas
### Sessão 2026-03-11
- [x] Validado papel "Auxiliar de Secretaria"
- [x] Bug fix: Ano/Série em PDFs para turmas multisseriadas
- [x] Corrigida contagem "Desistências" no Dashboard
- [x] Ordenação ignorando acentos (collation MongoDB pt)
- [x] Filtro "Todas as Escolas" para admin
- [x] Seletor de cor para mensagem de destaque
- [x] Removida coluna "Matrícula" da frequência

### Sessão 2026-03-12
- [x] Objetos de Conhecimento para Educação Infantil (multi-select Campo de Experiência)

### Sessão 2026-03-13
- [x] Consulta Alunos (Assistência Social): label "Serie/Turma" -> "Ano/Série", valor usa student_series
- [x] Consulta Alunos: corrigido "Nome da Mãe = Não informado" (busca registro completo via getById)
- [x] Objetos de Conhecimento infantil: campos exibidos como texto fixo separado por hífen
- [x] Controle de Frequência Multi-Aula para Anos Finais/EJA (seletor N° de Aulas, colunas múltiplas)
- [x] Alinhamento contagem de alunos (Dashboard usa mesma lógica da listagem de escolas)

### Sessão 2026-03-16
- [x] **Declaração de Transferência** - Novo documento PDF com texto sobre transferência, menção ao Histórico Escolar em 30 dias, e assinatura do secretário(a)
- [x] **Correção Ano Letivo** - Todos os defaults "2025" corrigidos para ano dinâmico (2026) em: api.js, DocumentGeneratorModal.js, StudentsComplete.js, e backend endpoints

## Backlog Pendente
### P0
- [ ] Bug de exclusão de frequência (relatado pelo usuário)

### P1
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Implementar envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar lógica de permissões em hook usePermissions
- [ ] Extrair seletor multi-select para componente reutilizável
