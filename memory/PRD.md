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
- Fórmula Carga Horária Mensal: Alterada de Semanal×4.33 para Semanal×5 (27/03/2026)
- Migração retroativa: endpoint `/api/admin/migrate-payroll-hours` + botão em Ferramentas de Administração (27/03/2026)
- Bug fix: Servidores com lotação "anexa" apareciam na folha de pagamento das escolas anexas (28/03/2026)
  - Reescrito filtro `_filter_anexa_items(db, items, school_id)` — verifica por employee_id + school_id (não depende de assignment_id)
  - Aplicado em: detalhe da folha, lista de folhas, dashboard summary, analytics, relatórios PDF (folha-escola, consolidado)
  - Criado endpoint `/api/admin/cleanup-anexa-payroll` — busca por (employee_id, school_id) para remover dados
  - Botão "Limpar Servidores Anexos da Folha" em Ferramentas de Administração
- Renomeado "Horas Não Cumpridas" para "Faltas" em toda a folha de pagamento: visualização, edição e PDFs (28/03/2026)
- Validação de email no formulário de Usuários: impede salvamento de emails sem formato válido (nome@email.com) com feedback visual em tempo real (01/04/2026)
- Removida validação estrita (response_model) do endpoint /api/users para evitar erro 500 por dados inconsistentes no banco (01/04/2026)
- Adicionado handler global de exceções para garantir CORS em respostas 500 (01/04/2026)

## Papéis SEMED (Reestruturado em 27/03/2026)
- **SEMED** (base): Visualização de módulos acadêmicos + Acompanhamento de Diários
- **SEMED 1** (`semed1`): SEMED + Diário AEE
- **SEMED 2** (`semed2`): SEMED 1 + RH/Folha como Analista (aprovar/devolver)
- **SEMED 3** (`semed3`): SEMED 2 + Dashboard Analítico + Pré-Matrículas (RH somente visualização)

| Módulo | SEMED | SEMED 1 | SEMED 2 | SEMED 3 |
|---|:---:|:---:|:---:|:---:|
| Base (Escolas, Turmas, Alunos, etc.) | Viz | Viz | Viz | Viz |
| Avisos | Edita | Edita | Edita | Edita |
| Acomp. Diários | Viz | Viz | Viz | Viz |
| Diário AEE | - | Viz | Viz | Viz |
| RH / Folha | - | - | Analista | Viz |
| Dashboard Analítico | - | - | - | Viz |
| Pré-Matrículas | - | - | - | Viz |
| Usuários Online | - | - | - | Viz |
| Auditoria | - | - | - | Viz |

### Diretor (Ajustado em 27/03/2026)
- **Somente visualização** em todos os módulos acadêmicos (Escolas, Turmas, Alunos, Notas, Frequência, etc.)
- **Edita**: RH/Folha e Avisos
- **Visualiza**: Diário AEE (novo acesso)

### Secretário (Ajustado em 27/03/2026)
- **Edita**: Diário AEE (novo acesso)

### Auditoria (Ajustado em 27/03/2026)
- Acesso restrito a Admin e SEMED 3 apenas

## Tela de Gestão de Papéis (Implementado em 27/03/2026)
- Botão "Matriz de Permissões" no módulo de Usuários (somente admin)
- Tabela visual 9 papéis × 18 módulos com badges: Edita (verde), Viz (azul), Analista (âmbar), — (sem acesso)
- Dropdown de troca rápida de nível SEMED na coluna "Papel" (semed→semed1→semed2→semed3)
- Restrição: papéis admin/semed/ass_social só são visíveis e criáveis por administradores
- Legenda explicativa no rodapé da matriz

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
