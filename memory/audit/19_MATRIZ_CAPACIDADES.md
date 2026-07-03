# ENTREGA 19 — Matriz de Capacidades

> Auditoria READ-ONLY · Jun/2026. ✅ Completo · ⚠ Parcial/Precisa evoluir · ❌ Inexistente.
> Baseada em evidência de código (routers/services/páginas/coleções).

## 1. Núcleo de Gestão Escolar
| Capacidade | Status | Nota |
|---|---|---|
| Multi-tenancy / isolamento (RLS) | ✅ | fail-closed + auditoria |
| Gestão de Escolas | ✅ | |
| Gestão de Turmas (multisseriadas) | ✅ | |
| Gestão de Alunos / Matrículas | ✅ | vínculo triplicado (débito) |
| Responsáveis / Guardians | ⚠ | portal responsável incipiente |
| Servidores (Staff) | ✅ | |
| Folha de Pagamento / RH | ⚠ | funcional; expansão prevista |
| Componentes Curriculares | ✅ | |
| Currículo v2 / Adaptações | ⚠ | migração + cobertura em evolução |
| Grade Horária | ⚠ | WRITE≠READ (3 coleções) |
| Calendário Letivo / Eventos | ✅ | sábado letivo tratado |

## 2. Pedagógico
| Capacidade | Status | Nota |
|---|---|---|
| Notas (numérico + conceitual) | ✅ | congelamento granular |
| Frequência | ✅ | consolidação diária, futuras datas |
| Diário de Classe | ✅ | |
| Objetos de Conhecimento / Conteúdos | ✅ | |
| Snapshots de Diário (verificáveis) | ✅ | QR público |
| Dependências de estudo | ⚠ | multisseriada com seletor de série |
| AEE | ✅ ⛔ | módulo protegido |
| BNCC (independente + IA) | ❌ | tarefa futura |

## 3. Documentos & Verificação
| Capacidade | Status |
|---|---|
| Boletim Online + PDF | ✅ |
| Histórico Escolar / Reconstrução | ✅ |
| Livro de Promoção | ✅ |
| Declarações Escolares | ✅ |
| Recibos/Documentos verificáveis (QR) | ✅ |
| Atestados médicos | ✅ |

## 4. Movimentação Institucional
| Capacidade | Status |
|---|---|
| Transferência entre escolas (motor canônico) | ✅ |
| Rollback de transferência (janela 7d) | ✅ |
| Remanejamento/Progressão/Reclassificação | ✅ (com lacunas legadas anotadas) |
| Reconstrução de histórico pedagógico | ✅ |

## 5. Programas & Serviços
| Capacidade | Status |
|---|---|
| Bolsa Família (frequência/condicionalidade) | ✅ |
| Busca Ativa | ⚠ |
| Assistência Social | ⚠ |
| Vacinas / Saúde escolar | ⚠ |
| Integração MEC (Educacenso/Presença) | ⚠/❌ |

## 6. Inteligência & Analytics
| Capacidade | Status | Nota |
|---|---|---|
| Dashboard Analítico | ⚠ | existe; consolidar |
| Painel PME (todos os níveis) | ✅ | recém-expandido |
| Indicadores Externos (PME) | ✅ | RBAC aplicado |
| Ranking de Gestão | ⚠ | |
| Relatórios Mensais (agendados) | ⚠ | scheduler + e-mail |
| Motor de Indicadores (canônico/configurável) | ❌ | **inexistente** (chave p/ BI) |
| Motor de Alertas | ⚠ | `alert_rules`/`alert_engine` parcial |
| Motores de Risco (acad./freq./geral) | ⚠ | sobreposição a unificar |
| PMPI Engine | ⚠ | |
| Student Intelligence Engine (SIE) | ⚠ | parcial |
| IA generativa (Claude — planos/relatórios) | ✅ | com fallback determinístico |
| Metas Estratégicas | ❌ | `monthly_goals` incipiente |
| Camada de BI dedicada | ❌ | ver [21](21_BUSINESS_INTELLIGENCE.md) |

## 7. Plataforma & Operação
| Capacidade | Status |
|---|---|
| Autenticação/Sessão (JWT + refresh + revogação) | ✅ |
| RBAC + Matriz de Permissões dinâmica | ✅/⚠ |
| Offline-first (PWA) | ✅ |
| Sincronização offline avançada (Conteúdo/Diário) | ⚠/❌ (Fase B futura) |
| Notificações / Mensageria / WebSocket | ⚠ |
| Auditoria & Observabilidade | ✅ |
| Migrações críticas (idempotentes + rollback) | ✅ |
| CI / Gate de regressão | ✅ |
| Deploy (Coolify/Traefik) | ✅ |
| Backup/Replica set de produção | ⚠/❌ |

## Resumo
- ✅ **Completo:** ~28 capacidades (core operacional + documentos + movimentação).
- ⚠ **Parcial:** ~18 (RH, currículo v2, analytics, alertas, risco, SIE, MEC, sync avançada).
- ❌ **Inexistente:** 5 críticas para evolução — **Motor de Indicadores**, **Metas
  Estratégicas**, **BNCC+IA**, **camada de BI dedicada**, **sync offline de Conteúdo/Diário**.
