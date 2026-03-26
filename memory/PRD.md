# SIGESC - Sistema Integrado de Gestão Escolar

## Visão Geral
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal.

## Arquitetura
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Motor (MongoDB async)
- **Banco**: MongoDB
- **PDF**: ReportLab + PyPDF2

## Módulos Implementados

### Módulo Acadêmico (Completo)
- Cadastro de escolas, turmas, alunos, servidores
- Matrículas e transferências, frequência e notas
- Boletins e fichas individuais
- Registros de conteúdo, diário de classe e AEE
- Calendário letivo, Analytics / Ranking de escolas

### Módulo RH / Folha (Fases 1 + 2 + 3 - Implementado em 26/03/2026)
**Backend**: `/app/backend/routers/hr.py`
**Frontend**: `/app/frontend/src/pages/HRPayroll.js`
**Rota**: `/admin/hr`
**Acesso**: admin, semed, semed3, diretor, secretario
**Coleções**: payroll_competencies, school_payrolls, payroll_items, payroll_occurrences, hr_audit_logs

#### Fase 1 - Base:
- Abertura de competência + pré-folha automática
- Dashboard, lista de folhas, detalhe com tabela de servidores
- Edição de lançamentos, ocorrências, validações automáticas
- Fluxo: não_iniciada → em_preenchimento → enviada → aprovada/devolvida → fechada

#### Fase 2 - Avançado:
- Upload de documentos comprobatórios (PDF/JPG/PNG até 10MB)
- Hora-aula avançado (não cumpridas, repostas, extras)
- Substituições vinculadas com validação
- Horas complementares detalhadas (11 motivos, período, autorização)
- Histórico de alterações (auditoria) com diff campo-a-campo

#### Fase 3 - Fluxo Avançado e Notificações:
- Notificações automáticas ao devolver folha (aviso no sistema para diretor/secretário da escola)
- WebSocket em tempo real para notificações
- Validações rigorosas no envio (servidores sem lançamento, ocorrências sem documento, pendências)
- Bloqueio automático por prazo (data limite de lançamento da competência)
- Reabertura de competência com justificativa obrigatória e log de auditoria
- Alertas de envio exibidos na folha (warnings detalhados)

## Correções desta sessão (26/03/2026)
- Bug fix: Benefícios do aluno (case mismatch)
- PDF Frequência: labels DIAS vs AULAS por nível
- Registros de conteúdo: incluídos na conversão CAIXA ALTA
- PDF Frequência: componente e nível completo para Anos Finais

## Tarefas Pendentes

### Módulo RH - Fase Futura
- **Fase 4** (P2): Relatórios (espelho individual, consolidado por escola/rede, auditoria completa)

### Outras Tarefas
- (P1) Alterar carga horária de componentes curriculares
- (P2) Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- Modularizar pdf_generator.py (+4200 linhas)
- Centralizar permissões em hook usePermissions

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: coordenador@sigesc.com / coordenador123
- Secretário: secretario@sigesc.com / secretario123

## Notas Técnicas
- Token frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape`
- Background polling: usar `useRef` para initial load
- Benefits/disabilities: excluídos de uppercase
