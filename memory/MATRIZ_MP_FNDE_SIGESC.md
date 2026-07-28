# MATRIZ_MP_FNDE_SIGESC.md — Cruzamento normativo (Censo/Educacenso/INEP + MP/TCM)

> **Sprint READ-ONLY (Jun/2026).** Documento auxiliar da `AUDITORIA_CADASTRO_ESCOLAS.md`.
> **Objetivo:** determinar se o SIGESC já possui os dados para responder rapidamente a
> demandas de MP, FNDE, TCM e INEP — e onde estão as lacunas.
> **Baseline oficial:** Censo Escolar / Educacenso 2026 (questionário da escola —
> Caracterização e Infraestrutura). **Complemento:** achados recorrentes de MP/TCE
> (água potável, esgoto, banheiros, incêndio).

## Legenda de status
- ✅ **Coberto** — campo existe no modelo **e** é editável na interface.
- 🟨 **No modelo, oculto na UI** — dado existe, mas não há como preencher/atualizar pela tela.
- ❌ **Ausente** — não existe no modelo (nem na UI).

## 1. Abastecimento de água (Educacenso · MP/TCE recorrente)
| Requisito oficial | Campo SIGESC | Status |
|---|---|---|
| Forma de abastecimento (rede/poço/cisterna) | `abastecimento_agua` | ✅ |
| Fornecimento de **água potável** para consumo | — | ❌ |
| **Certificado/laudo de potabilidade** (MP/TCE) | — | ❌ |
| "Não há abastecimento" (flag explícita) | (via texto) | 🟨 |

## 2. Esgotamento sanitário (Educacenso · MP recorrente)
| Requisito oficial | Campo SIGESC | Status |
|---|---|---|
| Existência de esgotamento sanitário | `saneamento` (texto) | 🟨 |
| **Tipo** (rede pública/fossa séptica/fossa rudimentar/inexistente) | — | ❌ |

## 3. Energia elétrica (Educacenso)
| Requisito | Campo | Status |
|---|---|---|
| Abastecimento de energia (rede/gerador/solar/não há) | `energia_eletrica` | ✅ |

## 4. Destinação do lixo (Educacenso)
| Requisito | Campo | Status |
|---|---|---|
| Existência de coleta de lixo | `coleta_lixo` (texto) | 🟨 |
| **Tipo de destinação** (coleta periódica/queima/enterra/joga) | — | ❌ |

## 5. Acessibilidade (Educacenso · Lei 13.146/LBI · MP)
| Requisito | Campo | Status |
|---|---|---|
| Rampas | `possui_rampas` | ✅ |
| Corrimão/guarda-corpo | `possui_corrimao` | ✅ |
| **Banheiro acessível (existência)** | `banheiros_adaptados` | ✅ |
| **Banheiro acessível (quantidade)** | `banheiros_acessiveis` | 🟨 |
| Sinalização tátil/piso tátil | `sinalizacao_tatil` | ✅ |
| Vias/dependências acessíveis (Censo detalhado) | (parcial) | 🟨/❌ |

## 6. Segurança e prevenção de incêndio (Bombeiros/AVCB · MP)
| Requisito | Campo | Status |
|---|---|---|
| Extintores | `extintores` / `qtd_extintores` | 🟨 |
| Saídas de emergência | `saidas_emergencia` | 🟨 |
| Brigada de incêndio | `brigada_incendio` | 🟨 |
| Plano de evacuação | `plano_evacuacao` | 🟨 |
| Videomonitoramento | `qtd_cameras` | 🟨 |
| Cercamento/muro | `possui_cercamento` | 🟨 |
| **AVCB / laudo dos Bombeiros (documento)** | — | ❌ |

## 7. Conservação e obras (FNDE/PAR/PDDE · MP/TCM)
| Requisito | Campo | Status |
|---|---|---|
| Estado de conservação | `estado_conservacao` | 🟨 |
| **Obra/reforma em andamento (situação)** | — | ❌ |
| **Fonte do recurso (PAR/FNDE/PDDE)** | — | ❌ |
| **Área do terreno / construída (m²)** | — | ❌ |
| **Ano de construção do prédio** | — | ❌ |
| **Regime de ocupação (próprio/alugado/cedido)** | — | ❌ |
| **Prédio compartilhado** | — | ❌ |

## 8. Conformidade legal (Vigilância/Prefeitura · MP)
| Requisito | Campo | Status |
|---|---|---|
| Alvará de funcionamento | — | ❌ |
| Licença sanitária (Vigilância) | — | ❌ |
| Habite-se | — | ❌ |
| Regulamentação (autorização/reconhecimento do ato) | `regulamentacao` | 🟨 |

## 9. Dependências físicas (Educacenso — ambientes existentes)
| Ambiente | Campo | Status |
|---|---|---|
| Salas de aula (nº) | `numero_salas_aula` | ✅ |
| **Sala de recursos multifuncionais (AEE)** | `salas_recursos_multifuncionais` | 🟨 |
| Biblioteca | `possui_biblioteca` | ✅ |
| Lab. ciências / informática | `possui_lab_ciencias` / `possui_lab_informatica` | ✅ |
| Quadra (coberta/descoberta) | `possui_quadra` / `possui_quadra_esportiva` | ✅/🟨 |
| Cozinha / refeitório | `possui_cozinha` / `possui_refeitorio` | ✅ |
| Almoxarifado / despensa | `possui_almoxarifado` | 🟨 |
| Sala diretoria/secretaria/coordenação/professores | `sala_direcao/secretaria/coordenacao/professores` | 🟨 |
| Pátio (coberto × descoberto) | `possui_patio` (1 bool) | 🟨/❌ |
| Parque/brinquedoteca/auditório/horta/estacionamento | `possui_parque/brinquedoteca/auditorio/horta/estacionamento` | 🟨 |
| Sala de leitura / lavanderia / área verde / alojamento | — | ❌ |

## 10. Oferta e gestão (dados administrativos do Censo)
| Requisito | Campo | Status |
|---|---|---|
| Etapas e subníveis ofertados | etapas + `*_1ano..9ano`, `educacao_infantil_*` etc. | ✅ |
| Turnos de funcionamento | `turnos_funcionamento` | 🟨 |
| Dependência/esfera administrativa | `dependencia_administrativa`/`esfera_administrativa` | 🟨 |
| Gestor / secretário escolar | `gestor_principal` / `secretario_escolar` | 🟨 |
| Fornece alimentação escolar | — | ❌ |

## Consolidação
| Situação | Nº aproximado de requisitos |
|---|---|
| ✅ Coberto (modelo + UI) | ~13 |
| 🟨 No modelo, **falta expor na UI** | ~24 |
| ❌ Ausente (falta no modelo) | ~18 |

**Conclusão:** a **maior parcela** dos requisitos MP/FNDE está 🟨 — **o dado já existe no
modelo, faltando apenas expô-lo na interface e em relatórios**. Uma minoria relevante (obras,
conformidade legal, potabilidade, tipificação de esgoto/lixo, metragem) está ❌ e exigiria
evolução pontual do modelo. **Não há hoje relatório/exportação institucional** que consolide
esses dados para resposta rápida a órgãos de controle (ver proposta na `AUDITORIA_CADASTRO_ESCOLAS.md`).

*Última atualização: Jun/2026 — Sprint READ-ONLY. Baseline: Educacenso 2026 + achados MP/TCE.*
