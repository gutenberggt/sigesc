# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Prefeitura Municipal de Floresta do Araguaia. Gerencia escolas, turmas, alunos, professores, notas, frequência, documentos PDF, e mais.

## Arquitetura
- **Frontend:** React (CRA) + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python) com roteadores modulares
- **Banco:** MongoDB
- **Auth:** JWT (access + refresh tokens)

## Papéis de Usuário
- `admin`, `admin_teste` - Administradores com acesso total
- `secretario` - Secretário(a) escolar
- `diretor` - Diretor(a) escolar
- `coordenador` - Coordenador(a) - apenas visualização
- `auxiliar_secretaria` - Auxiliar de Secretaria - permissões idênticas ao coordenador
- `professor` - Professor(a)
- `aluno`, `responsavel` - Aluno e Responsável
- `semed`, `semed3` - SEMED (Secretaria Municipal de Educação)
- `ass_social` - Assistente Social

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Auxiliar Secretaria: auxiliar_teste@sigesc.com / auxiliar123
- Secretário: secretario@sigesc.com / secretario123

## Tarefas Concluídas
### Sessão 2026-03-11
- [x] Validado papel "Auxiliar de Secretaria" (10+ erros de sintaxe corrigidos, 100% testes passando)
- [x] Corrigido bug login SchoolLink.get() para auxiliar_secretaria
- [x] BUG FIX: Ano/Série em documentos PDF para turmas multisseriadas
- [x] Corrigida contagem de "Desistências" no Dashboard Analítico
- [x] Card "Alunos(as)" do admin agora mostra contagem filtrada pelo ano corrente via analytics API
- [x] Ordenação de listas ignorando acentos (collation MongoDB pt)
- [x] Filtro "Todas as Escolas" para administradores na página de alunos
- [x] Seletor de cor para mensagem de destaque do Dashboard
- [x] Removida coluna "Matrícula" da página "Controle de Frequência"

### Sessão 2026-03-12
- [x] Funcionalidade "Objetos de Conhecimento" para Educação Infantil (100% testes passando - 11/11)
  - Multi-select de "Campo de Experiência" para turmas infantis
  - Detecção automática do nível de ensino da turma
  - Seleção "Todos" / individual com contagem
  - Formulário de criação com seletor de campo específico
  - Badge com nome do campo na lista de registros
  - Click-outside handler para fechar dropdown
  - Reset de estado ao trocar turma

## Backlog Pendente
### P0
- [ ] Bug de exclusão de frequência (relatado pelo usuário, investigação inconclusiva)

### P1
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Implementar envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar lógica de permissões no frontend em hook usePermissions
- [ ] Extrair seletor multi-select para componente reutilizável

## Dados de Teste Criados
- Turma infantil: PRE-ESCOLA I (id: 2df28f9e-1b80-4bbb-828a-d5a477639854, educacao_infantil)
- 5 Campos de Experiência (BNCC): O EU O OUTRO E O NÓS, CORPO GESTOS E MOVIMENTOS, TRAÇOS SONS CORES E FORMAS, ESCUTA FALA PENSAMENTO E IMAGINAÇÃO, ESPAÇOS TEMPOS QUANTIDADES RELAÇÕES E TRANSFORMAÇÕES
