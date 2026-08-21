# AEE V2 — Fase 4: Adequação Pedagógica e Guia de Conformidade

Data: 2026-08-21

## Objetivo

Completar a adequação pedagógica do Dossiê Individual AEE V2 a partir da homologação real em produção, sem migração destrutiva e sem invalidar snapshots já existentes.

## Evidência de homologação

O primeiro Dossiê V2 homologado apresentou `v1.r1 · Em trabalho`, fonte efetiva ainda no Plano AEE legado e bloqueadores de vigência expostos como códigos técnicos. A mecânica de bootstrap, leitura e versionamento funcionou, mas a orientação ao usuário precisava ser convertida em linguagem pedagógica e alguns requisitos de completude precisavam ser endurecidos.

## Invariantes

- nenhum write em `planos_aee`, `atendimentos_aee`, `articulacoes_aee` ou `evolucoes_aee`;
- nenhuma migração em massa;
- nenhuma recriação de IDs históricos;
- snapshots anteriores permanecem verificáveis pelo mesmo SHA-256;
- não serão adicionados campos default ao `AEEDossierV2` nesta fase;
- o `v1.r1` já criado em homologação deve permanecer legível e íntegro;
- toda edição continua criando snapshot imutável e usando optimistic locking.

## Adequações

1. Pendências em linguagem humana, com seção e ação `Corrigir →`.
2. Participação do estudante e da família passam a ser verificadas separadamente no Estudo de Caso.
3. Tecnologia Assistiva e CAA passam a expor a capacidade de disponibilização já existente no contrato.
4. Demandas de formação e acionamento da rede de proteção passam a exigir avaliação explícita independente, inclusive quando a conclusão for ausência de demanda/acionamento.
5. PEI passa a exigir separadamente atividades do AEE e articulação com professor regente/equipe escolar.
6. A data de revisão anual passa a ser requisito de vigência.
7. Nova aba `Vigência e Revisão`, persistida em snapshots via endpoint sidecar próprio, sem permitir alteração direta de `status` ou `version`.

## Critério de aceite

A primeira versão V2 somente poderá tornar-se Vigente quando Estudo de Caso, PAEE e PEI estiverem concluídos e todos os requisitos obrigatórios tiverem sido preenchidos/avaliados. O usuário deve receber orientação legível e acionável em vez de códigos internos.
