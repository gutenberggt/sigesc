# ANA-LUCIA-F2.5 — Adjudicação read-only de tenant, chave natural e linhagem

## Objetivo

Resolver, sem qualquer escrita, os três bloqueios remanescentes identificados pela F2.4 antes de desenhar um executor de remapeamento cirúrgico:

1. `attendance` com `mantenedora_id` ausente;
2. `attendance` com chave natural incompleta;
3. linhagem `copied_from_id` dos `learning_objects` candidatos.

A F2.5 **não corrige dados**. Ela apenas classifica se cada caso pode ser determinado de forma inequívoca por evidência estrutural já existente.

## Baseline herdado da F2.4

- `learning_objects` candidatos: 198;
- `attendance` candidatos: 392;
- `attendance` com tenant ausente: 74;
- `attendance` com chave natural incompleta: 4;
- `learning_objects` copiados: 74;
- pais dentro do conjunto candidato: 73;
- pais ausentes: 1.

Qualquer diferença é registrada como drift; não é mascarada nem corrigida.

## Adjudicação do tenant

Para cada `attendance` candidato sem `mantenedora_id`, o tenant esperado só é considerado determinístico quando convergem, sem contradição:

- a turma-alvo;
- a escola da turma;
- o vínculo docente canônico/DVD atual da mesma turma e componente;
- a mantenedora única já provada para as oito turmas.

Se o documento possuir `school_id`, ele também deve coincidir com a escola da turma. Nenhum `mantenedora_id` é escrito nesta fase.

## Adjudicação da chave natural de frequência

A chave auditada permanece:

`class_id + date + period(default=regular) + aula_numero`.

Campos ausentes não são inferidos de `created_at` ou `updated_at`.

Quando o único campo ausente for `aula_numero`, a F2.5 consulta somente os `weekly_slots` estruturais do vínculo DVD atual e os slots já ocupados, na mesma turma/data/período, por documentos de origem e destino. A inferência só é considerada determinística se restar **exatamente um** slot válido e desocupado.

Zero slots, múltiplos slots ou ausência de data permanecem bloqueados para adjudicação humana posterior.

## Adjudicação de `copied_from_id`

A F2.5 constrói apenas a topologia da linhagem, sem ler conteúdo pedagógico.

Ela distingue:

- pai dentro do próprio conjunto candidato: remapear pai e filho juntos preserva a aresta;
- pai fora do conjunto ainda na identidade EJA: o futuro remapeamento criaria uma aresta cross-identity e permanece bloqueado;
- pai já na identidade atual;
- pai em outra identidade;
- pai inexistente antes da operação.

Para pai inexistente, `audit_logs` pode ser consultado exclusivamente com projeção estrutural (`action`, timestamps e papel do ator), sem `old_value`, `new_value` ou `description`, para verificar se há sinal de exclusão histórica.

Também é verificada a existência de ciclos no grafo candidato.

## Boundary

- MongoDB somente leitura;
- nenhum HTTP/login;
- sem `attendance.records`;
- sem estudantes/matrículas;
- sem valores de notas ou estados individuais de frequência;
- sem texto pedagógico;
- sem IDs técnicos brutos em evidência pública; somente fingerprints SHA-256 truncados;
- `audit_logs` sem `old_value`, `new_value` ou `description`;
- nenhuma mutação, backfill, merge, remapeamento, exclusão ou saneamento;
- Transferência Institucional e MT-1 intocados.

## Regra de saída

Mesmo que tenant, chave natural e linhagem fiquem integralmente determinísticos, a F2.5 retorna `write_authorized = false`.

Uma eventual fase de escrita deverá ser separada, fail-closed, presa a SHA exato, com plano de rollback, prova pré/pós-operação e autorização humana explícita antes do merge e antes da execução em produção.
