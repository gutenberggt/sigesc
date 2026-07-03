# 000.1 · 2 — Mapa de Dependências

> Grafo de dependências entre módulos/coleções para prever regressões antes de
> qualquer refatoração. READ-ONLY.

## 1. Grafo macro (quem depende de quem)
```
                         ┌───────────────┐
                         │ auth / tenant │  (base de TUDO: contexto + RLS)
                         └───────┬───────┘
                                 │
                 ┌───────────────┼───────────────────────────┐
                 ▼               ▼                           ▼
            ┌────────┐     ┌──────────┐               ┌────────────┐
            │ schools│────►│ classes  │◄──────────────│  courses/   │
            └────────┘     └────┬─────┘   curriculum  │  currículo  │
                                │                     └─────┬──────┘
        ┌───────────────────────┼───────────────┐          │
        ▼                       ▼               ▼          ▼
   ┌──────────┐          ┌────────────┐   ┌──────────┐  ┌─────────────────────┐
   │enrollments│◄────────│  students  │   │teacher_  │  │ grade horária       │
   └────┬─────┘  vínculo │(class_id)  │   │assignments│ │ (class_schedules /  │
        │  ▲ (class_      └─────┬──────┘   └────┬─────┘  │ teacher_class_asgn /│
        │  │  students)        │                │        │ teacher_allocations)│
        │  └────── class_students (3ª via) ─────┘        └─────────┬───────────┘
        ▼                                                          ▼
  ┌──────────────────────────────────────────────┐        ┌──────────────┐
  │ grades · attendance · content_entries · diary │◄───────│ calendário   │
  └───────────────┬───────────────────────────────┘        │ (dias letivos)│
                  │                                          └──────────────┘
                  ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ CONSUMIDORES DE 2ª ORDEM                                             │
  │  documents/PDF · diary_dashboard · pme_anos_finais · monthly_reports │
  │  bolsa_familia · risk engines → alerts → interventions → pmpi → IA   │
  │  school_transfer / history_reconstruction (motor canônico + rollback)│
  └────────────────────────────────────────────────────────────────────┘
```

## 2. Serviços/coleções compartilhados (alto reuso → alto raio de regressão)
| Recurso | Consumidores | Regressão se mudar |
|---|---|---|
| `students` | 173 refs — quase tudo | **Altíssima** |
| `classes` | 158 refs | **Altíssima** |
| `enrollments` | 108 refs | Alta |
| `attendance` | 82 — freq., BF, risco, diário, PDFs | Alta |
| `grades` | 63 — boletim, promoção, PME, risco | Alta |
| `tenant_scope.apply_tenant_filter` | todas as queries | **Crítica (segurança)** |
| `AuthMiddleware` | todos os endpoints | **Crítica** |
| `with_critical_mutation` | dedup, backfill, migração, transfer | Média (bem testado) |
| `school_calendar_helper` | diário, frequência, carga horária | Alta |
| builders `pdf/*` + `*_renderer` | todos os documentos | Média |

## 3. Componentes frontend reutilizados (regressão de UI)
- `Layout` + `StatusIndicator` + `SessionMonitor` → todas as páginas autenticadas.
- `usePermissions` → todo controle de visibilidade/RBAC no front.
- `components/grades/*` (`GradesTable`, `gradeHelpers`) → Notas, Boletim, Promoção, Ficha.
- Contexts `Auth`/`Mantenedora`/`Offline` → toda a árvore.

## 4. Alterações que podem gerar regressões (alerta prévio)
| Se mexer em… | Risco de quebrar… |
|---|---|
| `enrollments`/`students.class_id`/`class_students` (D2) | notas, frequência, promoção, PME, transferência, diário |
| grade horária (D1) | diário, frequência (sábado letivo), carga horária, relatórios |
| `tenant_scope` | isolamento de TODOS os tenants (segurança) |
| `AuthMiddleware`/refresh | sessão de todos os usuários + offline |
| `grade_calculator`/`gradeHelpers` | boletim, promoção, livro, ficha (consistência de status) |
| `school_calendar_helper` | tudo que depende de dia letivo |

## 5. Recomendação de sequenciamento seguro
1. Itens **isolados** primeiro (D6, D10, D9, D11) — baixo raio de regressão.
2. **D7** (RBAC) com cobertura de testes por router antes de tocar.
3. **D1/D2** somente com: (a) feature-flag/dual-write controlado, (b) snapshot+rollback,
   (c) suíte de regressão dedicada expandida (hoje há 27 testes de transfer; ampliar p/ vínculo/grade).
