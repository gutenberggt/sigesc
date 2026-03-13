# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Prefeitura Municipal de Floresta do Araguaia. Gerencia escolas, turmas, alunos, professores, notas, frequência, documentos PDF, e mais.

## Arquitetura
- **Frontend:** React (CRA) + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python) com roteadores modulares
- **Banco:** MongoDB
- **Auth:** JWT (access + refresh tokens)

## Papéis de Usuário
- `admin`, `admin_teste` - Administradores
- `secretario`, `diretor`, `coordenador`, `auxiliar_secretaria`
- `professor`, `aluno`, `responsavel`
- `semed`, `semed3`, `ass_social`

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
- [x] Consulta Alunos (Assistência Social): label "Serie/Turma" -> "Ano/Série", valor corrigido para student_series
- [x] Consulta Alunos: corrigido "Nome da Mãe = Não informado" (loadStudentDetails agora busca registro completo via getById)
- [x] Objetos de Conhecimento infantil: campos de experiência exibidos como texto fixo separado por hífen no formulário
- [x] **Controle de Frequência - Multi-Aula (P0)**: Para turmas de Anos Finais e EJA Final, adicionado seletor "N° de Aulas" (1-6) que multiplica as colunas de frequência. Backend salva number_of_classes e status pipe-separated (ex: "P|F|P|J"). Turmas de Anos Iniciais mantêm comportamento original.

## Backlog Pendente
### P0
- [ ] Bug de exclusão de frequência (relatado pelo usuário, investigação inconclusiva)

### P1
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Implementar envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar lógica de permissões em hook usePermissions
- [ ] Extrair seletor multi-select para componente reutilizável

## Dados de Teste Criados
- Turma infantil: PRE-ESCOLA I (educacao_infantil)
- Turma anos finais: 6º ANO A (fundamental_anos_finais) com 3 alunos + 2 cursos
- 5 Campos de Experiência (BNCC)
- 2 Componentes curriculares anos finais: MATEMÁTICA, PORTUGUÊS
