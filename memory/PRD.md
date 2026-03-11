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
- `auxiliar_secretaria` - Auxiliar de Secretaria - permissões idênticas ao coordenador (apenas visualização)
- `professor` - Professor(a)
- `aluno`, `responsavel` - Aluno e Responsável
- `semed`, `semed3` - SEMED (Secretaria Municipal de Educação)
- `ass_social` - Assistente Social

## Funcionalidades Implementadas
1. CRUD completo: Escolas, Turmas, Alunos, Servidores, Notas, Frequência
2. Geração de PDFs: Declarações, Boletins, Fichas Individuais, Livro de Promoção
3. Dashboard com estatísticas e mensagem de destaque configurável
4. Dashboard Analítico com gráficos
5. Sistema de anúncios
6. Calendário letivo
7. Objetos de Aprendizagem (AEE)
8. Pré-matrícula online
9. Gestão de servidores com lotações e alocações
10. Perfil de usuário
11. Acompanhamento de diários
12. Horário de aulas

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Auxiliar Secretaria: auxiliar_teste@sigesc.com / auxiliar123
- Secretário: secretario@sigesc.com / secretario123

## Tarefas Concluídas (Sessão Atual - 2026-03-11)
- [x] Corrigidos todos os erros de sintaxe do papel auxiliar_secretaria (10+ arquivos)
- [x] Corrigido bug de login (SchoolLink.get() → acesso por atributo/dict)
- [x] Criado usuário de teste auxiliar_secretaria
- [x] Validado papel auxiliar_secretaria com testing agent (100% testes passando)

## Backlog Pendente
### P1
- [ ] Corrigir contagem de "Desistências" no Dashboard Analítico (cancelled vs dropout)
- [ ] Alterar carga horária de componentes curriculares (script para produção)

### P2
- [ ] Implementar envio de e-mail de confirmação na pré-matrícula

### Refatoração
- [ ] Centralizar lógica de permissões no frontend em hook usePermissions
