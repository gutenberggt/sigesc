# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar completo com funcionalidades para gerenciamento de escolas, turmas, alunos, professores, notas, frequência, matrículas e pré-matrículas.

## Stack Tecnológica
- **Frontend:** React + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python)
- **Database:** MongoDB
- **Deploy:** Coolify + Docker no DigitalOcean

## Funcionalidades Implementadas

### Core
- ✅ Autenticação JWT com refresh token automático
- ✅ Gestão de escolas e mantenedoras
- ✅ Gestão de turmas com níveis de ensino
- ✅ Gestão de alunos com histórico
- ✅ Gestão de professores e usuários
- ✅ Lançamento de notas e frequência
- ✅ Geração de PDFs (boletins, fichas individuais, atas)
- ✅ Sistema de matrículas e pré-matrículas
- ✅ Notificações em tempo real (WebSocket)
- ✅ Sistema de mensagens entre usuários

### Turmas Multisseriadas (Fev 05, 2026) - NOVO
- ✅ **Backend - Modelo Class:** Adicionados campos `is_multi_grade` (bool) e `series` (List[str])
- ✅ **Backend - Modelo Enrollment:** Adicionado campo `student_series` (str) para especificar série do aluno
- ✅ **Frontend - Formulário de Turmas:** Checkbox "Turma Multisseriada" aparece quando nível de ensino tem múltiplas séries
- ✅ **Frontend - Seleção de Séries:** Quando multisseriada ativada, permite selecionar múltiplas séries via checkboxes
- ✅ **Frontend - Badge na Tabela:** Turmas multisseriadas exibem badge "Multi" com contagem de séries
- ✅ **Frontend - Modal de Matrícula:** Dropdown de série do aluno aparece ao selecionar turma multisseriada
- ✅ **Validação:** Botão de confirmar matrícula desabilitado se turma multisseriada e série não selecionada
- ✅ **Relatório por Série:** Modal de detalhes da turma exibe "Distribuição por Série" com contagem de alunos por série
- ✅ **Coluna Série na Tabela:** Lista de alunos matriculados mostra a série de cada aluno (apenas em turmas multisseriadas)

### Funcionalidades Recentes (Jan 2026)
- ✅ **Atestados Médicos:** Sistema completo para registro de atestados que bloqueia lançamento de frequência
- ✅ **Funcionalidade Offline:** Cadastro e edição de alunos offline com sincronização em background
- ✅ **Legendas em PDFs:** Legenda dinâmica para notas conceituais (Educação Infantil e 1º/2º Ano)
- ✅ **Sessão Persistente:** Token JWT com 7 dias de duração e auto-refresh
- ✅ **Permissões de Secretário:** Perfil com regras granulares de edição
- ✅ **Tratamento de Erros Global:** Utilitário `errorHandler.js` para erros de validação

### Melhorias no Cadastro de Alunos (Fev 02, 2026)
- ✅ **Campos Telefone e E-mail:** Adicionados na mesma linha do Nome Completo na identificação
- ✅ **Formatação de Telefone:** Formato (00)00000-0000 automático
- ✅ **Validação de E-mail:** Verifica formato válido de e-mail
- ✅ **Formatação de CPF:** Formato 000.000.000-00 (máx 11 dígitos)
- ✅ **Formatação de NIS/PIS/PASEP:** Formato 000.00000.00-0 (máx 11 dígitos)
- ✅ **Formatação de Número SUS:** Formato 000.0000.0000.0000 (máx 15 dígitos)
- ✅ **Autocomplete de Cidades:** Campo Naturalidade (Cidade) e Cidade da Certidão Civil com sugestões de cidades brasileiras a partir do 3º caractere
- ✅ **E-mail nos Responsáveis:** Campos de e-mail adicionados para Pai, Mãe e Outro Responsável
- ✅ **Formatação nos Responsáveis:** CPF e Telefone formatados automaticamente

### Funcionalidade de Ação do Aluno (Fev 02, 2026)
- ✅ **Campo "Ação":** Adicionado na aba Turma/Observações da página de edição de aluno
- ✅ **Opções de Ação:** Matricular, Transferir, Remanejar, Progredir
- ✅ **Lógica de Disponibilidade:** Opções habilitadas/desabilitadas com base no status do aluno:
  - **Alunos Transferidos/Desistentes:** Podem ser Matriculados
  - **Alunos Ativos:** Podem ser Transferidos, Remanejados ou Progredidos
- ✅ **Modal de Matricular:** Permite selecionar escola e turma de destino
- ✅ **Modal de Transferir:** Permite informar motivo da transferência
- ✅ **Modal de Remanejar:** Permite selecionar nova turma na mesma escola
- ✅ **Modal de Progredir:** Permite avançar para próxima série ou emitir histórico escolar
- ✅ **Registro no Histórico:** Todas as ações são registradas com tipo (matricula, transferencia_saida, remanejamento, progressao)

### Patches de Segurança - FASE 3 (Fev 02, 2026)
- ✅ **PATCH 3.1 - Idle Timeout:** Access token expira em 15 minutos, mas é renovado automaticamente enquanto o usuário está ATIVO. O frontend detecta atividade (mouse, teclado, scroll) e renova proativamente a cada 10 minutos. Usuários inativos por 15 minutos precisam fazer login novamente
- ✅ **PATCH 3.2 - Rotação de Tokens:** Cada uso do refresh token gera um novo par de tokens e revoga o antigo. Impede reutilização de tokens vazados
- ✅ **PATCH 3.3 - Blacklist de Tokens:** Sistema de revogação com endpoints `/api/auth/logout` (sessão atual) e `/api/auth/logout-all` (todas as sessões). Logout no frontend agora revoga tokens no servidor

### Patches de Segurança - FASE 2 (Fev 02, 2026)
- ✅ **PATCH 2.1 - Filtragem de Dados Sensíveis:** Campos como CPF, RG, NIS, dados bancários e senhas são automaticamente removidos dos dados de sincronização offline
- ✅ **PATCH 2.2 - Paginação no Sync:** Endpoint `/api/sync/pull` agora suporta paginação (`page`, `pageSize`) para evitar sobrecarga de memória. Padrão: 100 itens, máximo: 500
- ✅ **PATCH 2.3 - Rate Limiting no Sync:** Limites implementados - máximo 5 coleções por pull e 100 operações por push

### Patches de Segurança - FASE 1 (Fev 02, 2026)
- ✅ **PATCH 1.1 - Download de Backup:** Rotas `/api/download-backup` e `/api/download-uploads` desativadas por padrão. Requerem `ENABLE_BACKUP_DOWNLOAD=true` no `.env` e autenticação de admin
- ✅ **PATCH 1.2 - Anti-Traversal:** Rota `/api/uploads/{file_path}` protegida contra path traversal (`../`), paths absolutos e acesso fora do diretório de uploads
- ✅ **PATCH 1.3 - Upload Restrito:** Rota `/api/upload` restrita a roles autorizados (admin, admin_teste, secretario, diretor, coordenador)

### Correções e Melhorias (Jan 30, 2026)
- ✅ **Botão "Início":** Adicionado na página de Gestão de Pré-Matrículas para navegação rápida
- ✅ **Cache Offline:** Melhorada a inicialização do banco IndexedDB com tratamento de erros de versão
- ✅ **Banco de Dados Local:** Sistema de auto-recuperação quando há conflitos de versão do Dexie

### Permissões de Secretário (Jan 29, 2026)
- ✅ **Visualização:** Secretário pode ver TODOS os alunos de todas as escolas
- ✅ **Edição de Alunos:** Pode editar alunos ATIVOS apenas da sua escola; alunos NÃO ATIVOS de qualquer escola
- ✅ **Geração de Documentos:** Botão "Documentos" visível apenas para alunos da escola vinculada ao secretário
- ✅ **Filtro de Turmas:** Página de turmas filtrada para mostrar apenas turmas das escolas do secretário
- ✅ **Estatísticas Dashboard:** Cards de estatísticas filtrados para escolas do secretário

## Tarefas Pendentes (Backlog)

### P0 - Crítico
- [ ] **Deploy em Produção:** Resolver Gateway Timeout após redeploy via Coolify

### P1 - Alta Prioridade
- [ ] **Refatoração Backend FASE 4:** Extrair rotas restantes e implementar App Factory em `app_factory.py`
- [ ] **Email de Confirmação na Pré-Matrícula:** Enviar email para responsável
- [ ] **Destaque de Aluno Recém-Criado:** Implementar highlight via URL na lista

### P2 - Média Prioridade
- [ ] **Refatoração Frontend:** Decompor o "god component" StudentsComplete.js
- [ ] **Expansão Offline:** Estender funcionalidade offline para módulo de matrículas
- [ ] **Padronização de Erros:** Aplicar errorHandler.js em componentes restantes

### P3 - Baixa Prioridade
- [ ] **Limpeza de Código:** Remover arquivo obsoleto Courses.js
- [ ] **Relatórios Gerenciais:** Criar relatórios para atestados médicos

## Última Atualização
**Data:** 07 de Fevereiro de 2026
**Funcionalidade:** Score V2.1 - Novo Sistema de Ranking de Escolas

### Score V2.1 - Implementado (Fev 07, 2026):
Sistema de pontuação de 0-100 pontos para ranking de escolas, baseado em indicadores objetivos.

#### Composição do Score (100 pontos):

**BLOCO APRENDIZAGEM (45 pts):**
- ✅ **Nota Média (25 pts):** `(média_final / 10) × 100`
- ✅ **Taxa de Aprovação (10 pts):** `(aprovados / total_avaliados) × 100`
- ✅ **Ganho/Evolução (10 pts):** `clamp(50 + delta×25, 0, 100)` - Mede evolução entre bimestres

**BLOCO PERMANÊNCIA/FLUXO (35 pts):**
- ✅ **Frequência Média (25 pts):** `(P + J) / total × 100`
- ✅ **Retenção/Anti-evasão (10 pts):** `100 - (dropouts / matrículas) × 100`

**BLOCO GESTÃO/PROCESSO (20 pts):**
- ✅ **Cobertura Curricular (10 pts):** `(aulas_com_registro / aulas_previstas) × 100` (proxy)
- ✅ **SLA Frequência - 3 dias úteis (5 pts):** `(lançamentos_no_prazo / total) × 100`
- ✅ **SLA Notas - 7 dias (5 pts):** `(lançamentos_no_prazo / total) × 100`

**INDICADOR INFORMATIVO (não entra no score):**
- ✅ **Distorção Idade-Série:** % de alunos com 2+ anos acima da idade esperada para a série

#### Endpoint Atualizado:
- `GET /api/analytics/schools/ranking?academic_year=YYYY&limit=N&bimestre=B`
  - Retorna: `score`, `score_aprendizagem`, `score_permanencia`, `score_gestao`
  - Retorna: `indicators` com todos os indicadores detalhados
  - Retorna: `raw_data` com dados brutos para auditoria
  - Retorna: `grade_evolution` com médias bimestrais (b1, b2, b3, b4)

#### Frontend Atualizado:
- ✅ Tabela de ranking com todas as colunas de indicadores
- ✅ Cores indicativas (verde/amarelo/vermelho) por faixa de desempenho
- ✅ Breakdown por bloco (Aprendizagem | Permanência | Gestão)
- ✅ Legenda explicativa dos indicadores
- ✅ Tooltip com descrição de cada coluna
- ✅ **Gráfico de Radar** comparando Top 5 escolas nos 3 blocos
- ✅ **Barras de progresso** mostrando % de aproveitamento por bloco
- ✅ **Modal de Drill-Down** com detalhamento completo ao clicar em uma escola:
  - Resumo dos 3 blocos com pontuação e percentual
  - Detalhamento dos 8 indicadores com contribuição individual
  - Gráfico de evolução das notas por bimestre (AreaChart)
  - Indicador informativo de Distorção Idade-Série
  - Dados brutos (matrículas, aprovados, evasões, objetos de conhecimento)

### Arquivos Modificados:
- `/app/backend/routers/analytics.py` - Endpoint `/schools/ranking` completamente reescrito
- `/app/frontend/src/pages/AnalyticsDashboard.jsx` - Nova tabela de ranking com Score V2.1

---

### Implementações Anteriores (Fev 05, 2026):
1. **Ordenação Alfabética**
   - ✅ Escolas, turmas e alunos ordenados alfabeticamente nos filtros do Dashboard Analítico
   
2. **Bloqueio de Alunos Transferidos**
   - ✅ Alunos com status "transferido" têm frequência e notas bloqueadas para edição pelo professor
   - ✅ Badge "🔒 Bloqueado" exibido na lista de alunos
   
3. **Remanejamento - Cópia de Dados**
   - ✅ 100% dos dados de frequência E notas são copiados para turma destino
   - ✅ Dados na turma de origem ficam bloqueados para o professor
   - ✅ Endpoint `/api/students/{id}/copy-data` criado
   
4. **Progressão - Cópia de Dados**
   - ✅ 100% dos dados de frequência são copiados para turma destino
   - ✅ Dados na turma de origem ficam bloqueados para o professor
   
5. **Bloqueio de Alunos Falecidos**
   - ✅ Alunos com status "falecido/deceased" têm frequência e notas bloqueadas para professor

## Arquitetura de Deploy

### Coolify + Traefik
O Traefik não detecta automaticamente os labels dos containers. Foi necessário criar configuração manual:

```yaml
# /traefik/dynamic/sigesc-backend.yaml (dentro do container coolify-proxy)
http:
  routers:
    sigesc-backend:
      rule: "Host(`api.sigesc.aprenderdigital.top`)"
      service: sigesc-backend-service
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
  services:
    sigesc-backend-service:
      loadBalancer:
        servers:
          - url: "http://backend:8001"
```

### Domínios
- **Frontend:** https://sigesc.aprenderdigital.top
- **Backend API:** https://api.sigesc.aprenderdigital.top

## Arquivos Importantes

### Backend
- `/app/backend/server.py` - Servidor principal FastAPI
- `/app/backend/models.py` - Modelos Pydantic
- `/app/backend/pdf_generator.py` - Geração de PDFs
- `/app/backend/routers/medical_certificates.py` - API de atestados

### Frontend
- `/app/frontend/src/pages/StudentsComplete.js` - Gestão de alunos
- `/app/frontend/src/pages/PreMatriculaManagement.jsx` - Gestão de pré-matrículas
- `/app/frontend/src/pages/Attendance.js` - Lançamento de frequência
- `/app/frontend/src/utils/errorHandler.js` - Tratamento de erros
- `/app/frontend/src/db/database.js` - Banco de dados local (IndexedDB/Dexie)
- `/app/frontend/src/contexts/OfflineContext.jsx` - Contexto de funcionalidade offline
- `/app/frontend/nginx.conf` - Configuração do Nginx

## Credenciais de Teste
- **Admin:** gutenberg@sigesc.com / @Celta2007
- **Secretários de teste:**
  - ROSIMEIRE: rosimeireazevedo@sigesc.com (vinculada à escola "C M E I PROFESSORA NIVALDA MARIA DE GODOY")
  - ADRIANA: adrianapereira@sigesc.com (vinculada à escola "E M E I E F PAROQUIAL CURUPIRA")

## Documentação de Infraestrutura
- `/app/memory/TRAEFIK_FIX_GUIDE.md` - Guia completo para resolver o problema do Traefik no Coolify
- `/app/docker-compose.coolify.yml` - Docker Compose otimizado para deploy no Coolify

## Backlog

### P0 - Crítico
- ⚠️ **Configuração do Traefik no Coolify:** A configuração manual atual é frágil. Aplicar o guia `/app/memory/TRAEFIK_FIX_GUIDE.md` para solução permanente. **NOTA:** Este é um problema de infraestrutura externa que requer acesso ao servidor de produção.

### P1 - Próximas
- Email de confirmação após pré-matrícula
- Highlight do aluno recém-criado na lista
- Padronizar valores de status dos alunos no banco de dados ("transferred" vs "Transferido")

### P2 - Futuras (FASE 4 Concluída)
- ✅ **Routers Extraídos:** students, grades, attendance, calendar, staff, announcements
- ✅ **Rotas Legadas Removidas:** 28 rotas duplicadas removidas do server.py
- ✅ **Redução de Código:** server.py reduzido de 7588 para 6470 linhas (~15%)
- ✅ **App Factory:** Criado `/app/backend/app_factory.py` com padrão Factory
- Refatoração do `SchoolsComplete.js`
- Expansão offline para matrículas
- Padronização de erros em todos componentes

### P3 - Backlog
- Remover `Courses.js` obsoleto
- Relatórios gerenciais de atestados médicos
