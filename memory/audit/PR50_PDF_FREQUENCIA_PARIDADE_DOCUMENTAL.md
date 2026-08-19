# PR #50 — Paridade documental do PDF de Frequência DVD

## Objetivo

Fazer o PDF de frequência emitido pelo professor via Diário por Vínculo usar as mesmas fontes documentais do PDF administrativo, sem ampliar permissões e sem alterar registros de frequência.

## Paridade

- Série/Ano: documento canônico da turma em `classes`, preservando configuração multisseriada.
- Professores: `services.class_teachers.get_multi_teacher_names_for_pdf`, mesma regra já usada no PDF administrativo.
- Assinaturas: mesmo `generate_relatorio_frequencia_bimestre_pdf`; quando há múltiplos professores, o renderer gera as assinaturas adicionais já existentes.
- Frequência: continua vindo da ponte DVD/histórica já validada.

## Invariantes

1. Nenhuma escrita, migração ou reatribuição no MongoDB.
2. O `assignment_id` continua obrigatório para professor DVD e define autorização/escopo.
3. A turma canônica é usada apenas depois da resolução segura do vínculo.
4. Nenhum professor recebe acesso a turma, escola ou mantenedora fora do vínculo.
5. O PDF administrativo não é alterado.
6. O renderer e a regra institucional de múltiplos professores são reutilizados, não duplicados.

## Caso de aceitação

E M E I E F Cristo Redentor — turma `1º AO 5º ANO` — 1º bimestre/2026.

Esperado no PDF emitido por Ivanete Silva Santos:

- `SÉRIE/ANO: 1º, 2º, 3º, 4º e 5º Ano`;
- `PROFESSORES(AS): Ivanete Silva Santos, Rayane de Sousa Gomes de Carvalho` (ordem definida pelo helper canônico);
- duas assinaturas de professor(a) + uma de coordenador(a);
- 41 dias previstos e 40 registrados;
- P/F/J e totais preservados pelo PR #49.
