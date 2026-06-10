# ROADMAP — Student Intelligence Engine (SIE)

> Inteligência estruturada por aluno. A IA (fase futura) consome ESTA estrutura,
> nunca o contrário. Tudo multi-tenant (ver `tenant_scope.py`).

## FASE 0 — Motor baseado em REGRAS (entregue Jun/2026)

### Coleções (todas com `mantenedora_id`)
- `sie_config` — parâmetros por mantenedora (nota de corte, frequência mínima, pesos, faixas).
- `student_risk_scores` — score corrente por aluno/ano: `academic_risk`, `attendance_risk`, `overall_risk`, `risk_level`, `factors` (explicabilidade), breakdowns, `trend_status`.
- `student_diagnostics` — diagnóstico ESTRUTURADO (status por dimensão, contagens). Texto é consequência.
- `student_snapshots` — 1 por dia → série temporal (gráficos de evolução).
- `student_alerts` — sinais materializados p/ notificações sem recalcular.

### Motores (puros, testáveis — `backend/services/`)
- `academic_risk_engine.py` — notas 50 / recuperação 20 / reprovação 20 / tendência 10.
- `attendance_risk_engine.py` — presença anual 70 / faltas recentes 30.
- `overall_risk_engine.py` — acadêmico 55% + frequência 45% + `classify_risk`.
- `diagnostic_engine.py` — diagnóstico estruturado + fatores legíveis.
- `alert_engine.py` — attendance_drop / academic_decline / multiple_recoveries / failing / critical_overall.
- `sie_service.py` — orquestração (carrega notas+frequência do banco, chama motores, config defaults+merge).

### Classificação (4 níveis)
`0–24 low` · `25–49 moderate` · `50–74 high` · `75–100 critical`

### Endpoints (`/api/sie`, `routers/student_intelligence.py`)
- `GET/PUT /config`
- `GET /students/{id}` (ao vivo) · `POST /students/{id}/compute` (persiste)
- `GET /students/{id}/snapshots`
- `POST /compute?school_id=&class_id=&academic_year=` (lote)
- `GET /risk?school_id=&class_id=&level=&academic_year=`
- `GET /alerts?severity=&alert_type=&resolved=`

### Defaults (configuráveis por tenant via sie_config)
passing_grade 6.0 · attendance_min_pct 75 · recent_window_days 30 ·
caps {recovery_max 3, failed_max 2, trend_drop_max 3, recent_absence_max 0.5}

## PRÓXIMAS FASES (backlog)
- **FASE 1 — Frontend MVP**: painel do aluno (Risco Geral/Acadêmico/Frequência, tendência, componentes críticos, recuperações, fatores) + lista priorizada por risco + agendar `POST /compute` (cron diário) + notificações a partir de `student_alerts`.
- **FASE 2 — IA Assistente**: camada LLM consumindo `student_diagnostics`/`student_risk_scores` para recomendações e linguagem natural.
