# ENTREGA 11 — Mapa de Rotas (Frontend)

> Auditoria READ-ONLY · Jun/2026. **86 `<Route>`** em `App.js` (react-router-dom 7).
> Proteção por `<ProtectedRoute allowedRoles={[...]}>`. Classificação 🟢🟡🔴⚫.

## 1. Rotas públicas (sem autenticação) — 🟢
| Rota | Página | Uso |
|---|---|---|
| `/login` | `Login.js` | login + diagnóstico offline + banner PWA |
| `/` | `LandingPage.jsx` | página inicial pública |
| `/sobre` | `LandingPage.jsx` | institucional |
| `/pre-matricula` | `PreMatricula.jsx` | pré-matrícula pública |
| `/confirm-email-change` | `ConfirmEmailChange.js` | confirmação de troca de e-mail |
| `/verificar`, `/verificar/:code` | `VerifyPublic.jsx` | verificação pública de documento |
| `/v/:token` | verificação | recibo/transferência (QR) |
| `/verify/boletim/:token` | `VerifyBulletin.jsx` | valida boletim |
| `/verify/diary/:token` | `VerifyDiarySnapshot.jsx` | valida diário |
| `/verify/historico/:token` | `VerifyHistory.jsx` | valida histórico |
| `*` | fallback | rota não encontrada |

## 2. Rotas autenticadas gerais — 🟢
| Rota | Página | Público |
|---|---|---|
| `/dashboard` | `Dashboard.js` | gestão (menu por RBAC) |
| `/profile`, `/profile/:userId` | `UserProfile.js` | todos autenticados |
| `/avisos` | `Announcements.js` | todos |
| `/tutoriais` + subpáginas | `TutorialsPage.jsx` | conforme trilha |

## 3. Rotas administrativas / gestão (`/admin/*`) — 🟢🟡
Escopo por `allowedRoles` (super_admin, admin, admin_teste, gerente, secretario,
diretor, coordenador, apoio_pedagogico, auxiliar_secretaria, semed*). Exemplos:
`/admin/schools`, `/admin/classes`, `/admin/students`(+`/:studentId/historico`),
`/admin/courses`, `/admin/grades`, `/admin/attendance`, `/admin/learning-objects`,
`/admin/diary-calendar`, `/admin/diary-dashboard`, `/admin/grade-integrity`,
`/admin/bulletins`, `/admin/calendar`, `/admin/events`, `/admin/hr`, `/admin/staff`,
`/admin/bolsa-familia`(+`/busca-ativa`), `/admin/pre-matriculas`, `/admin/promotion`,
`/admin/declaracoes`, `/admin/document-validator`, `/admin/content-review`,
`/admin/text-improvement`, `/admin/curriculo/{importar,adaptacoes,cobertura}`,
`/admin/intervencoes`, `/admin/plano-acao`, `/admin/ranking-gestores`,
`/admin/relatorios-mensais`, `/admin/reconstrucao-historico`.

### Restritos à alta gestão (super_admin / admin / gerente)
- `/admin/mantenedora`, `/admin/mantenedoras`, `/admin/tenant` (multi-tenant)
- `/admin/mec` (integração MEC)
- `/admin/audit-logs`, `/admin/logs`, `/admin/online-users`
- `/admin/permission-matrix`, `/admin/tools`
- `/admin/auditoria-matriculas` (super_admin/admin/gerente)
- `/admin/transferencias`(+`/nova`) — **super_admin** (operação destrutiva)
- `/admin/users`

## 4. Rotas do Professor (`/professor/*`) — 🟢
| Rota | Página |
|---|---|
| `/professor` | `ProfessorDashboard.js` (Acesso Rápido + turmas) |
| `/professor/notas` | lançamento de notas |
| `/professor/frequencia` | frequência |
| `/professor/objetos-conhecimento` | conteúdos |
| `/professor/calendario` | calendário |
| `/professor/perfil` | perfil |
| `/professor/turma/:classId/diario` | diário da turma |
| `/professor/turma/:classId/alunos` | alunos da turma |
> Nota (Jun/2026): "Livro de Promoção" (`/admin/promotion`) agora acessível ao
> professor, **restrito ao vínculo** (escolas/turmas/componentes que leciona).

## 5. Rotas do Aluno / Responsável — 🟡
| Rota | Página |
|---|---|
| `/aluno` | `AlunoDashboard.jsx` |
| `/aluno/boletim` | `BoletimAluno.jsx` |

## 6. Rotas SEMED / Analíticas — 🟡
| Rota | Página |
|---|---|
| `/semed/panel` | `SemedPanel.jsx` |
| `/admin/analytics` | `AnalyticsDashboard.jsx` |
| `/pme/anos-finais` | `PmeAnosFinais.jsx` (Análise PME — todos os níveis) |
| `/pme/anos-finais/indicadores` | `PmeExternalIndicators.jsx` |
| `/pmpi/engine` | `PmpiEngine.jsx` |
| `/action-plans` | `ActionPlans.jsx` |

## 7. Rotas de Serviços Comunitários — 🟡
`/ass-social` (`AssocialDashboard.js`, admin), `/vacinas` (`VaccineDashboard.js`, admin).

## 8. Observações
- **Lazy loading:** rotas carregadas via `lazy()` com wrapper anti-`ChunkLoadError`
  (reload único guardado em sessionStorage) — importante para PWA pós-deploy.
- **Consistência de nomenclatura:** mistura de PT (`/admin/declaracoes`,
  `/admin/reconstrucao-historico`) e EN (`/admin/grade-integrity`,
  `/admin/bulletins`). Oportunidade de padronização (baixa prioridade).
- **RBAC frontend ≈ backend:** a proteção de rota é a **primeira** barreira; a
  autorização definitiva é no backend (ver [12](12_PERMISSOES.md)).
