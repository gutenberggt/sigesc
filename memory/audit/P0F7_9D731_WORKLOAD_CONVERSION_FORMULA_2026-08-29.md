# P0-F7.9D7.3.1 — Fórmula canônica de conversão de carga horária

Data: 2026-08-29

## Decisão institucional

Foram definidos os símbolos e a fórmula canônica de conversão de carga horária curricular:

- `ha` = horas anuais;
- `hm` = horas mensais;
- `hs` = horas semanais;
- `ha / 8 = hm`;
- `hm / 5 = hs`;
- equivalência algébrica: `ha / 40 = hs`.

## Equivalências canônicas

| ha | hm = ha/8 | hs = hm/5 |
|---:|---:|---:|
| 40h | 5h | 1h |
| 80h | 10h | 2h |
| 120h | 15h | 3h |

## Aplicação curricular

A fórmula converte a carga anual já resolvida pela política curricular. A regra de aplicabilidade continua sendo:

1. componente curricular;
2. nível de ensino;
3. série/ano ou etapa;
4. em turma multissérie, prevalece a maior carga anual entre as séries/etapas representadas (`MAX_ANNUAL_WORKLOAD`);
5. somente depois é feita a conversão `ha -> hm -> hs`.

A matriz institucional atualmente coberta por `backend/utils/curricular_workload_policy.py` permanece a de Geografia, História e Ciências. A inclusão de `40h -> 1h semanal` amplia a conversão canônica, mas não cria por si só uma nova regra curricular de 40h para esses três componentes.

## Caso D7.3.1 em análise

Para `MULTI 3º E 4º ETAPA`, EJA Anos Finais, Geografia:

- carga anual resolvida: 80h;
- `80 / 8 = 10h mensais`;
- `10 / 5 = 2h semanais`;
- portanto o valor semanal canônico permanece 2h.

## Segurança e escopo

Esta alteração é de política pura/offline e apresentação da estação de adjudicação.

- `PRODUCTION_ACCESS=NO`
- `DATABASE_MUTATION=NO`
- `PRODUCTION_WRITES=NO`
- `EXECUTOR_AUTHORIZED=NO`

Nenhuma autorização anterior de escrita em produção é reutilizada ou ampliada por esta decisão.
