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
- Matrículas e transferências
- Frequência e notas
- Boletins e fichas individuais
- Registros de conteúdo (learning objects)
- Diário de classe e AEE
- Calendário letivo
- Analytics / Ranking de escolas

### Módulo RH / Folha (Fase 1 + Fase 2 - Implementado em 26/03/2026)
**Backend**: `/app/backend/routers/hr.py`
**Frontend**: `/app/frontend/src/pages/HRPayroll.js`
**Modelos**: Adicionados ao final de `/app/backend/models.py`
**Rota**: `/admin/hr`
**Acesso**: admin, semed, semed3, diretor, secretario
**Coleções**: payroll_competencies, school_payrolls, payroll_items, payroll_occurrences, hr_audit_logs
**Uploads**: /app/backend/uploads/hr/

#### Fase 1 - Base:
- Abertura de competência mensal + pré-folha automática
- Dashboard com resumo por status
- Lista de folhas por escola
- Detalhe da folha com tabela de servidores
- Edição de lançamentos (horas, aulas, complementares)
- Registro de ocorrências (faltas, atestados, afastamentos)
- Validações automáticas
- Fluxo de status: não_iniciada → em_preenchimento → enviada → aprovada/devolvida → fechada

#### Fase 2 - Avançado:
- Upload de documentos comprobatórios (PDF/imagem até 10MB)
- Indicador visual de documentos anexados (coluna "Docs" e ícone de clipe)
- Hora-aula avançado: aulas não cumpridas, repostas, extras, substituição
- Horas complementares detalhadas: tipo/motivo parametrizado, período, autorizado por
- Substituições vinculadas com validação (exige servidor substituído, sem duplicata)
- Subtipos de afastamento/licença parametrizados
- Histórico de alterações (auditoria) com diff campo-a-campo
- Endpoint de enums parametrizáveis (/api/hr/enums)
- Seletor de servidores para substituição (/api/hr/school-employees)
- Validação: aulas não cumpridas sem falta/atestado, total aulas > previstas

## Correções desta sessão (26/03/2026)
- Bug fix: Benefícios do aluno (case mismatch uppercase/checkboxes)
- PDF Frequência: labels DIAS vs AULAS por nível
- Registros de conteúdo: incluídos na conversão CAIXA ALTA
- PDF Frequência: componente e nível completo para Anos Finais

## Tarefas Pendentes

### Módulo RH - Fases Futuras
- **Fase 3** (P1): Fluxo de aprovação avançado (validações rigorosas, bloqueio por prazo)
- **Fase 4** (P2): Relatórios (espelho individual, consolidado por escola/rede, auditoria)

### Outras Tarefas
- (P1) Alterar carga horária de componentes curriculares
- (P2) Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- Modularizar pdf_generator.py (+4200 linhas)
- Centralizar permissões em hook usePermissions
- Extrair multi-select reutilizável
- Unificar função duplicada inferEducationLevel

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: coordenador@sigesc.com / coordenador123
- Secretário: secretario@sigesc.com / secretario123

## Notas Técnicas
- Token no frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape`
- Background polling: usar `useRef` para initial load
- Benefits/disabilities: excluídos de uppercase (valores predefinidos)
