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

### Módulo RH / Folha (Fase 1 - Implementado em 26/03/2026)
**Backend**: `/app/backend/routers/hr.py`
**Frontend**: `/app/frontend/src/pages/HRPayroll.js`
**Modelos**: Adicionados ao final de `/app/backend/models.py`
**Rota**: `/admin/hr`
**Acesso**: admin, semed, semed3, diretor, secretario

#### Funcionalidades da Fase 1:
- Abertura de competência mensal
- Geração automática de pré-folha (baseada em school_assignments)
- Dashboard com resumo por status
- Lista de folhas por escola
- Detalhe da folha com tabela de servidores
- Edição de lançamentos (horas, aulas, complementares)
- Registro de ocorrências (faltas, atestados, afastamentos, etc.)
- Validações automáticas (excesso de carga, complementar sem motivo, etc.)
- Recálculo automático de totalizadores por ocorrências
- Fluxo de status: não_iniciada → em_preenchimento → enviada → aprovada/devolvida → fechada

#### Coleções MongoDB:
- `payroll_competencies`: Competências mensais
- `school_payrolls`: Folha por escola/competência
- `payroll_items`: Linha do servidor na folha
- `payroll_occurrences`: Ocorrências (faltas, atestados, etc.)

## Correções desta sessão (26/03/2026)
- Bug fix: Benefícios do aluno não salvavam (case mismatch entre uppercase e checkboxes)
- Adequação: Labels do PDF frequência (DIAS PREVISTOS/REGISTRADOS para Ed. Infantil e Anos Iniciais)
- Adequação: Registros de conteúdo incluídos na conversão CAIXA ALTA
- Adequação: Nomes completos dos níveis de ensino no PDF frequência
- Adequação: Componente curricular exibido no PDF de frequência para Anos Finais

## Tarefas Pendentes

### Módulo RH - Fases Futuras
- **Fase 2** (P1): Lançamento detalhado (hora-aula avançado, upload de documentos, substituições vinculadas)
- **Fase 3** (P1): Fluxo de aprovação avançado (análise pela Secretaria, validações mais rigorosas)
- **Fase 4** (P2): Relatórios (espelho individual, consolidado por escola, consolidado da rede, auditoria)

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

## Notas Técnicas Importantes
- Token no frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape` para dados textuais do banco
- Background polling: páginas devem usar `useRef` para initial load para não desmontar com setLoading
- Benefits/disabilities: são campos com valores predefinidos, excluídos de uppercase
