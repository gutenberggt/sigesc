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

## Tarefas Concluídas (Sessão Atual - 2026-03-11)
- [x] Validado papel "Auxiliar de Secretaria" (10+ erros de sintaxe corrigidos, 100% testes passando)
- [x] Corrigido bug login SchoolLink.get() para auxiliar_secretaria
- [x] **BUG FIX: Ano/Série em documentos PDF para turmas multisseriadas**
  - Boletim, Ficha Individual e Declarações agora usam `enrollment.student_series` em vez de `class_info.grade_level`
  - Corrigidos 7 pontos em `documents.py` e `pdf_generator.py`
  - Testado com aluno em turma multisseriada: "ANO/ETAPA" exibe série correta do aluno

## Backlog Pendente
### P1
- [ ] Corrigir contagem de "Desistências" no Dashboard Analítico (cancelled vs dropout)
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Implementar envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar lógica de permissões no frontend em hook usePermissions
