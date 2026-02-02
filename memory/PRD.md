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

### Funcionalidades Recentes (Jan 2026)
- ✅ **Atestados Médicos:** Sistema completo para registro de atestados que bloqueia lançamento de frequência
- ✅ **Funcionalidade Offline:** Cadastro e edição de alunos offline com sincronização em background
- ✅ **Legendas em PDFs:** Legenda dinâmica para notas conceituais (Educação Infantil e 1º/2º Ano)
- ✅ **Sessão Persistente:** Token JWT com 7 dias de duração e auto-refresh
- ✅ **Permissões de Secretário:** Perfil com regras granulares de edição
- ✅ **Tratamento de Erros Global:** Utilitário `errorHandler.js` para erros de validação

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

## Correções de Deploy (Jan 28, 2026)
- ✅ Bug do `nginx.conf` com regex `{8}` corrigido
- ✅ Bug do campo `education_level` vs `nivel_ensino` corrigido
- ✅ Container antigo `backend-temp` removido
- ✅ Configuração manual do Traefik criada em `/traefik/dynamic/sigesc-backend.yaml`

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
