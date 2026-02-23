# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema completo de gestão escolar para secretarias de educação municipal, incluindo:
- Gestão de escolas, turmas e alunos
- Controle de frequência e notas
- Diário de classe digital
- Pré-matrícula online
- Relatórios e dashboards
- Módulo AEE (Atendimento Educacional Especializado)

## User Personas
- **Admin/SEMED:** Acesso total ao sistema
- **Secretário:** Gestão de escola específica
- **Diretor:** Visão administrativa da escola
- **Coordenador:** Acompanhamento pedagógico
- **Professor:** Diário de classe e notas
- **Ass. Social:** Consulta de dados de alunos para acompanhamento social

## Arquitetura
- **Frontend:** React + Tailwind CSS + Shadcn/UI
- **Backend:** FastAPI + Python
- **Database:** MongoDB
- **Autenticação:** JWT

## Funcionalidades Implementadas

### Core
- [x] CRUD completo de escolas, turmas, alunos
- [x] Sistema de autenticação com múltiplos papéis
- [x] Controle de frequência
- [x] Sistema de notas por bimestre
- [x] Pré-matrícula online
- [x] Relatórios e PDF generation

### Módulos Especiais
- [x] Diário AEE completo
- [x] Dashboard Assistente Social (Fev/2026)
- [x] Cálculo de frequência com dias letivos
- [x] Sistema de auditoria

### Recente (Fev/2026)
- [x] Papel "Ass. Social" implementado
- [x] Dashboard com busca de alunos por nome/CPF
- [x] Cálculo de frequência: ((Dias Letivos - Faltas) / Dias Letivos) × 100
- [x] Bug fix: Permissão de acesso para ass_social em students, schools, classes

## Issues Conhecidos

### P0 - Crítico
- [x] Containers sem conexão automática à rede Coolify (corrigido 23/02/2026 - nomes fixos no docker-compose)

### P1 - Alto
- [ ] Migração para CAIXA ALTA pode estar incompleta

### P2 - Médio
- [x] Feedback em tempo real para CPF duplicado (corrigido 23/02/2026)
- [ ] Refatoração do StudentsComplete.js

## Backlog
- [ ] E-mail de confirmação na pré-matrícula
- [ ] Continuar refatoração do backend (extrair rotas do server.py)

## Credenciais de Teste
- **Admin:** gutenberg@sigesc.com / @Celta2007

---
*Última atualização: 23/02/2026*
