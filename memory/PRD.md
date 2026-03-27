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

### Módulo RH / Folha (Fases 1-4 Completas - 27/03/2026)
**Backend**: `/app/backend/routers/hr.py`
**Frontend**: `/app/frontend/src/pages/HRPayroll.js`
**PDF Generator**: `/app/backend/hr_pdf_generator.py`
**Rota**: `/admin/hr`
**Acesso**: admin, semed, semed3, diretor, secretario
**Coleções**: payroll_competencies, school_payrolls, payroll_items, payroll_occurrences, hr_audit_logs

#### Fase 1 - Base:
- Abertura de competência + pré-folha automática
- Dashboard, lista de folhas, detalhe com tabela de servidores
- Edição de lançamentos, ocorrências, validações automáticas
- Fluxo: não_iniciada -> em_preenchimento -> enviada -> aprovada/devolvida -> fechada

#### Fase 2 - Avançado:
- Upload de documentos comprobatórios (PDF/JPG/PNG até 10MB)
- Hora-aula avançado (não cumpridas, repostas, extras)
- Substituições vinculadas com validação
- Horas complementares detalhadas (11 motivos, período, autorização)
- Histórico de alterações (auditoria) com diff campo-a-campo

#### Fase 3 - Fluxo Avançado e Notificações:
- Notificações automáticas ao devolver folha (aviso no sistema para diretor/secretário)
- WebSocket em tempo real para notificações
- Validações rigorosas no envio
- Bloqueio automático por prazo
- Reabertura de competência com justificativa obrigatória

#### Fase 4 - Relatórios PDF (Implementado em 27/03/2026):
- **Espelho Individual**: PDF com dados do servidor, carga horária, ausências, ocorrências, assinaturas
  - Endpoint: `GET /api/hr/reports/espelho/{item_id}`
  - Botão: Tela de detalhe do servidor (item-detail)
- **Folha Consolidada por Escola**: Tabela de todos servidores com totalizadores
  - Endpoint: `GET /api/hr/reports/folha-escola/{payroll_id}`
  - Botão: Tela de detalhe da folha (payroll-detail)
- **Consolidado da Rede**: Resumo de todas as escolas da competência
  - Endpoint: `GET /api/hr/reports/consolidado-rede/{competency_id}`
  - Botão: Dashboard (somente admin/semed)
- **Relatório de Auditoria**: Log de todas as alterações da competência
  - Endpoint: `GET /api/hr/reports/auditoria/{competency_id}`
  - Botão: Dashboard (somente admin/semed)

#### Painel de Indicadores Visuais (Implementado em 27/03/2026):
- **Taxa de Conformidade**: Cards com % de servidores sem pendências e % de folhas enviadas/aprovadas
- **Distribuição de Status**: Gráfico de donut (pizza) com cores por status
- **Horas da Rede**: Gráfico de barras horizontal (Previstas vs Trabalhadas vs Complementares)
- **Ausências por Escola**: Ranking das escolas com mais ausências (barras horizontais)
- **Detalhamento de Ausências**: Gráfico de barras verticais (Faltas, Atestados, Afastamentos)
- Endpoint: `GET /api/hr/dashboard/analytics?competency_id={id}` (somente admin/semed)
- Biblioteca: Recharts v3.8.1

## Correções Implementadas
- Bug fix: Benefícios do aluno (case mismatch)
- PDF Frequência: labels DIAS vs AULAS por nível
- Registros de conteúdo: incluídos na conversão CAIXA ALTA
- PDF Frequência: componente e nível completo para Anos Finais

## Papéis SEMED (Reestruturado em 27/03/2026)
- **SEMED** (base): Visualização de módulos acadêmicos + Acompanhamento de Diários
- **SEMED 1** (`semed1`): SEMED + Diário AEE
- **SEMED 2** (`semed2`): SEMED 1 + RH/Folha como Analista (aprovar/devolver)
- **SEMED 3** (`semed3`): SEMED 2 + Dashboard Analítico + Pré-Matrículas (RH somente visualização)

| Módulo | SEMED | SEMED 1 | SEMED 2 | SEMED 3 |
|---|:---:|:---:|:---:|:---:|
| Base (Escolas, Turmas, Alunos, etc.) | Viz | Viz | Viz | Viz |
| Acomp. Diários | Viz | Viz | Viz | Viz |
| Diário AEE | - | Viz | Viz | Viz |
| RH / Folha | - | - | Analista | Viz |
| Dashboard Analítico | - | - | - | Viz |
| Pré-Matrículas | - | - | - | Viz |
| Usuários Online | - | - | - | Viz |

## Tarefas Pendentes

### Outras Tarefas
- (P1) Alterar carga horária de componentes curriculares
- (P2) Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- Modularizar pdf_generator.py (+4200 linhas)
- Centralizar permissões em hook usePermissions
- Refatorar inferEducationLevel duplicado

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: coordenador@sigesc.com / coordenador123
- Secretário: secretario@sigesc.com / secretario123

## Notas Técnicas
- Token frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape`
- Background polling: usar `useRef` para initial load
- Benefits/disabilities: excluídos de uppercase
