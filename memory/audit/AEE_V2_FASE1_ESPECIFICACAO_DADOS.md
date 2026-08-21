# AEE v2 — Fase 1: Especificação Canônica de Dados

Data: 21/08/2026  
Status: implementação em branch, sem migração de produção

## 1. Objetivo

Estabelecer o contrato canônico do Dossiê AEE v2 do SIGESC para organizar, de forma aditiva e não destrutiva:

1. Estudo de Caso;
2. Plano de Atendimento Educacional Especializado — PAEE;
3. Plano Educacional Individualizado — PEI;
4. cronograma de atendimento;
5. ciclo de vida/versionamento;
6. proveniência do documento legado.

Esta fase **não substitui**, **não apaga** e **não regrava** os documentos existentes em `planos_aee`.

## 2. Base normativa verificada

### Decreto nº 12.686/2025, com redação do Decreto nº 12.773/2025

Fonte oficial:  
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12686.htm  
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12773.htm

Pontos usados no desenho:

- o Estudo de Caso é etapa inicial necessária para a identificação do estudante público da educação especial;
- contempla demandas individuais e barreiras, análise do contexto escolar, potencialidades, demandas de apoio e definição de estratégias/recursos de acessibilidade;
- seu resultado fundamenta PAEE e PEI;
- estudante e familiares devem participar ao longo do Estudo de Caso;
- pode haver diálogo com a rede de proteção social quando necessário;
- avaliação biopsicossocial pode subsidiar o processo;
- a oferta do AEE não pode ser condicionada a diagnóstico, laudo, relatório ou outro documento de profissional de saúde.

### Portaria MEC nº 421/2026, vigente

Fonte oficial MEC Normas:  
https://mecnormas.mec.gov.br/pesquisa/detalhar/11240

Pontos usados no desenho:

- PAEE e PEI são documentos pedagógicos individualizados, de atualização contínua, derivados do Estudo de Caso;
- a rede pode adotar documento único, desde que mantenha os critérios mínimos de PAEE e PEI;
- revisão anual deve ser compatibilizada com a avaliação contínua do estudante;
- PAEE deve contemplar materiais/recursos, avaliação de tecnologia assistiva e CAA, avaliação de apoios humanos, demandas de formação e eventual acionamento da rede de proteção;
- PEI deve contemplar atividades do AEE e articulação escolar, acessibilidade curricular/didático-pedagógica/avaliativa, acompanhamento/monitoramento e devolutivas às famílias.

### Portaria MEC nº 550/2026

Fonte oficial MEC Normas:  
https://mecnormas.mec.gov.br/pesquisa/detalhar/12723

A alteração atingiu o art. 29 da Portaria nº 421/2026. Não alterou os arts. 7, 10 e 11 utilizados nesta especificação.

## 3. Regra de preservação

A evolução do Diário AEE é:

- incremental;
- aditiva;
- versionada;
- auditável;
- reversível por camada;
- sem recriação de IDs históricos;
- sem hard migration nesta fase.

A projeção v2 é gerada em memória a partir do Plano legado. O documento original não é modificado.

## 4. Estrutura canônica

```text
AEEDossierV2
├── identificação / contexto escolar
├── study_case
│   ├── fundamentação pedagógica da identificação
│   ├── demanda/contexto inicial
│   ├── barreiras
│   ├── potencialidades
│   ├── demandas de apoio
│   ├── comunicação/participação
│   ├── estratégias e recursos de acessibilidade
│   ├── participação/contribuições do estudante
│   ├── contribuições da família
│   └── articulação com rede de proteção, quando necessária
├── paee
│   ├── barreiras prioritárias
│   ├── objetivos
│   ├── materiais e recursos
│   ├── tecnologia assistiva
│   ├── comunicação aumentativa e alternativa
│   ├── profissional de apoio escolar
│   ├── tradutor/intérprete de Libras
│   ├── guia-intérprete
│   ├── demandas de formação
│   ├── acionamentos da rede de proteção
│   └── monitoramento/revisão
├── pei
│   ├── atividades AEE
│   ├── articulação com sala comum
│   ├── combinados com professor regente
│   ├── acessibilidade curricular
│   ├── acessibilidade didático-pedagógica
│   ├── acessibilidade avaliativa
│   ├── adaptações por componente
│   ├── acompanhamento/monitoramento
│   └── devolutivas à família
├── schedule
├── lifecycle
└── provenance
```

## 5. Mapeamento inicial do legado

| Legado | Destino v2 |
|---|---|
| `criterio_elegibilidade` | `study_case.fundamentacao_pedagogica_identificacao` |
| `linha_base_situacao_atual` | `study_case.demanda_inicial_contexto` |
| `linha_base_potencialidades` | `study_case.potencialidades` |
| `linha_base_dificuldades` | `study_case.demandas_apoio` |
| `linha_base_comunicacao` | `study_case.comunicacao_participacao` |
| `barreiras` | `study_case.barreiras_contexto` + `paee.barreiras_prioritarias` |
| `objetivos` | `paee.objetivos` |
| `recursos_acessibilidade` | `study_case.estrategias_recursos_acessibilidade` + `paee.materiais_recursos` |
| `orientacoes_sala_comum` | `pei.articulacao_sala_comum` |
| `combinados_professor_regente` | `pei.combinados_professor_regente` |
| `adequacoes_curriculares` | `pei.acessibilidade_curricular` |
| `adaptacoes_por_componente` | `pei.adaptacoes_por_componente` |
| `indicadores_progresso` | `paee.indicadores_progresso` + apoio inicial ao monitoramento do PEI |
| dias/horários/local/modalidade | `schedule.sessions[]` |
| `status` | `lifecycle.status` |
| IDs/autoria/template/datas | `provenance` + `lifecycle` |

O mapeamento não afirma que um campo legado satisfaz integralmente uma exigência nova. Ele apenas reaproveita conteúdo semanticamente relacionado e sinaliza o que ainda precisa ser complementado.

## 6. Semântica crítica: `not_assessed`

Para tecnologia assistiva, CAA e apoios humanos, ausência de informação legada resulta em:

```text
not_assessed
```

Nunca em:

```text
not_needed
```

Isso impede transformar silêncio histórico em conclusão pedagógica.

## 7. Relatório de lacunas

Cada projeção retorna:

- campos legados consumidos;
- campos não vazios ainda não mapeados;
- lacunas por seção;
- severidade da lacuna.

O relatório é instrumento de adequação progressiva. **Não é certificação automática de conformidade normativa.**

## 8. Campos propositalmente não obrigatórios

O contrato canônico não exige:

- diagnóstico clínico;
- CID;
- laudo médico;
- relatório de profissional de saúde.

Documentos externos poderão subsidiar o processo em fluxos próprios, mas não constituem pré-condição de criação do Estudo de Caso, PAEE ou PEI.

## 9. Estados das seções

Cada seção admite:

- `legacy_projected` — conteúdo projetado do documento existente;
- `in_progress` — em elaboração;
- `complete` — seção declarada concluída no fluxo futuro;
- `not_applicable` — somente quando houver decisão pedagógica explícita e justificável.

## 10. Critérios de aceite da Fase 1

- [ ] contrato canônico compila em Python 3.11;
- [ ] projeção não modifica o dict/documento legado;
- [ ] IDs e status legados permanecem rastreáveis;
- [ ] ausência de apoio não é convertida em `not_needed`;
- [ ] campos desconhecidos não vazios aparecem no relatório de auditoria;
- [ ] teste impede tornar diagnóstico/laudo/CID obrigatórios;
- [ ] listas mutáveis não são compartilhadas entre documentos;
- [ ] gate CI específico do AEE v2 aprovado.

## 11. Próxima subfase após o gate

Criar uma leitura canônica sem escrita:

```text
GET /api/aee/planos/{plano_id}/dossie-v2
```

O endpoint deverá:

1. respeitar as permissões atuais do AEE;
2. carregar o Plano legado sem modificá-lo;
3. projetar o Dossiê v2 em memória;
4. retornar `dossier` + `report`;
5. não gravar nada no MongoDB;
6. permitir auditoria real dos Planos existentes antes de qualquer persistência v2.
