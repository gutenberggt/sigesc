# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal. Inclui gerenciamento de escolas, turmas, alunos, matrículas, frequência, notas, AEE, calendário letivo, servidores, e dashboards analíticos.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## O que foi implementado

### Sessão Anterior
- Acesso `ass_social`: Corrigido bug de busca de alunos, escolas e turmas
- Validação de CPF: Corrigido endpoint `check-cpf-duplicate`
- Dashboard `ass_social`: Dados de alunos "Não matriculados" ocultados
- Cancelar Matrícula: Implementado no frontend e backend
- Plano de AEE: Módulo totalmente reformulado
- Central de Tutoriais: Página de tutorial para Diário AEE
- Correção de acentuação no tutorial
- Branding: "Gutenberg Barroso" como desenvolvedor, logo SIGESC
- Dashboard Analítico: Lógica de contagem corrigida
- Bug Edição de Escolas: Removido campo duplicado "Situação de Funcionamento"

### Sessão Atual (25/02/2026)
1. **Escolas - Recomposição da Aprendizagem:** Substituído "Aulas Complementares" por "Recomposição da Aprendizagem" na aba Ensino > Atendimentos e Programas
2. **Alunos - Filtro obrigatório:** Removido "Todas as escolas" do filtro. Alunos só são exibidos após seleção de escola ou busca por nome/CPF
3. **Alunos - Comunidade Tradicional:** Removido "Selecione", padrão automático "Não Pertence"
4. **Alunos - Matrícula em Programa:** Nova seção "Matrícula em Atendimento/Programa" na aba Turma/Observações para alunos com deficiência. Opções: AEE, Reforço Escolar, Recomposição da Aprendizagem
5. **Diário AEE:** Alunos com atendimento_programa_tipo='aee' agora aparecem no Diário AEE da escola

## Issues Pendentes
- **P0:** Deploy em produção (Coolify) - Bad Gateway após deploy (infraestrutura do servidor)
- **P3:** Inconsistência no Dashboard Analítico - Fix aplicado, pendente verificação do usuário
- **P4:** Migração CAIXA ALTA possivelmente incompleta - pendente verificação

## Tarefas Futuras
- Paginação na listagem de turmas
- Refatoração do `StudentsComplete.js`
- Envio de e-mail na pré-matrícula
- Refatoração do backend (extrair rotas do `server.py`)

## Modelos de Dados Atualizados
- **SchoolBase:** Adicionado `recomposicao_aprendizagem: Optional[bool] = False`
- **StudentBase:** Adicionado `atendimento_programa_tipo` e `atendimento_programa_class_id`
- **StudentUpdate:** Mesmos campos adicionados

## Credenciais
- Admin: `gutenberg@sigesc.com` / `@Celta2007`
