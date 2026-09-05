# R1.0B.2 — Bridge Relacional por Topologia Histórica — Luiz Gomes

Data: 2026-09-05  
Tracking: `sigesc#435` → `#418` → `#357`

## Estado de entrada

A R1.0B.2 parte de duas rotas já esgotadas no dump BSON ad hoc de 18/08/2026:

1. **R1.0B / #422 — schema/value bridge**: terminou `HISTORICAL_SCHEMA_BRIDGE_INCONCLUSIVE`, motivo `CLASS_LABEL_VALUE_OR_COMPOSITE_NOT_RESOLVED`. O schema histórico não permitiu resolver 6º A, 6º B, 7º A, 7º B, 8º A e 9º A por rótulo completo ou composição série+seção.
2. **R1.0B.1 / #425 — temporal identity bridge**: terminou `COMPLETED / TEMPORAL_IDENTITY_NOT_PRESERVED`, com **0/6** identidades atuais preservadas no dump. `math_rows=None` e `payload_rows=None`; **None não significa zero**.

O baseline acadêmico continua o da R1.0A: `RECOVERABLE_EXACT=0`. R1.1 permanece bloqueada.

## Pergunta forense da R1.0B.2

A fase testa se a **Topologia Histórica** do próprio dump consegue recuperar identidade sem depender de nomes das chaves, rótulos de turma ou IDs atuais.

O dump é modelado como grafo de incidência entre os documentos preservados de:

- `users` / `staff`;
- `teacher_assignments` / `teacher_class_assignments`;
- `classes`;
- `courses`;
- `learning_objects`;
- `content_entries`, quando disponível.

A busca usa valores escalares somente como arestas internas. Valores técnicos usados para formar arestas não são externalizados.

## Duas provas separadas

### 1. Vizinhança Luiz + Matemática

O probe procura, dinamicamente:

- o componente relacional histórico do professor Luiz Gomes dos Santos;
- o componente relacional dos documentos de curso Matemática;
- assignments incidentes simultaneamente nos dois componentes;
- classes alcançadas de maneira única por esses assignments.

A primeira condição estrutural é existir exatamente uma vizinhança de **seis nós de classe distintos**.

### 2. Identidade semântica dos seis papéis

**Seis nós não são seis papéis.**

Mesmo que o grafo encontre seis classes candidatas, elas não podem ser nomeadas automaticamente como 6º A, 6º B, 7º A, 7º B, 8º A e 9º A. Para isso seria necessária uma bijeção semântica única sustentada por evidência independente.

O probe calcula assinaturas locais sanitizadas por nó, incluindo apenas contagens estruturais:

- grau de assignments;
- grau de componentes;
- grau de `learning_objects`;
- grau de Matemática;
- linhas/datas no período, ainda anônimas;
- presença de payload como contagem/booleano;
- grau de `content_entries`, quando disponível.

Se dois ou mais nós têm a mesma assinatura estrutural, há **simetria** e o resultado deve ser `HISTORICAL_TOPOLOGY_BRIDGE_SYMMETRIC`.

Mesmo se as seis assinaturas forem diferentes, diferença estrutural não autoriza atribuir nomes de turma. Sem âncora semântica independente, o resultado permanece `HISTORICAL_TOPOLOGY_BRIDGE_INCONCLUSIVE`, motivo `SIX_NODE_NEIGHBORHOOD_RESOLVED_ROLE_MAPPING_UNANCHORED`.

Não é permitido ordenar nós por ID, contagem, data, fingerprint ou posição para batizá-los.

## O que a fase deliberadamente não usa

- IDs atuais das seis turmas;
- rótulos de turma como chave de mapeamento;
- frequência atual ou as contagens 33/34 como identidade;
- `attendance` ou `attendance.records`;
- alunos, matrículas ou notas;
- ordenação lexical/numérica de IDs;
- inferência de autoria do payload.

O nome do professor e o nome do componente Matemática servem somente para localizar seus nós históricos de partida; a identidade das turmas é investigada pelas relações resultantes.

## Boundary operacional

A execução futura, se autorizada, reutiliza o runner forense já revisado `luiz_gomes_f6_3d_1_bson_dump_runner.sh`:

- seleção do dump ad hoc de 18/08/2026;
- restore em Mongo temporário com `--network none`;
- nenhuma porta publicada;
- fonte BSON read-only;
- somente coleções bounded da trilha forense;
- nenhuma escrita no Mongo de produção;
- nenhum deploy;
- nenhum ID técnico bruto em Actions/issues/artifacts;
- nenhum plaintext pedagógico emitido;
- cleanup obrigatório dos temporários.

## Taxonomia

- `HISTORICAL_TOPOLOGY_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT`
- `HISTORICAL_TOPOLOGY_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD`
- `HISTORICAL_TOPOLOGY_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS`
- `HISTORICAL_TOPOLOGY_BRIDGE_SYMMETRIC`
- `HISTORICAL_TOPOLOGY_BRIDGE_INCONCLUSIVE`
- `HISTORICAL_TOPOLOGY_RUNTIME_OR_BOUNDARY_ERROR`

A implementação inicial é deliberadamente fail-closed: não produz uma classificação `RESOLVED` sem uma futura evidência semântica independente capaz de nomear unicamente todos os seis nós. Isso impede transformar assimetria do grafo em identidade acadêmica inventada.

## Gates

- **R1.0C** permanece fechada enquanto os seis papéis não forem identificados unicamente e não houver ao menos uma linha histórica de Matemática atribuível ao 8º A ou 9º A.
- **R1.1** permanece bloqueada enquanto `RECOVERABLE_EXACT=0`.
- A PR desta fase pode ser preparada e revisada, mas merge e execução read-only exigem autorização humana explícita separada.
