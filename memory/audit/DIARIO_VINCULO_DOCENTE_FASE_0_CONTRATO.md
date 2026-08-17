# Diário por Vínculo Docente v1.0 — Fase 0 — Contrato Técnico

**Status:** especificação/guardrails, sem integração com produção  
**Branch:** `agent/diario-vinculo-fase0`  
**Base:** `main` em `f78b531b97669eb2ef1da4c70e69029f7b13059f`

## 1. Objetivo

Estabelecer, antes de qualquer alteração funcional, o contrato do **Diário por Vínculo Docente (DVD)** para turmas em que mais de um professor atua na mesma turma — especialmente escola de tempo integral e turmas compartilhadas — preservando turma, matrícula, histórico, regime avaliativo e navegação atual.

A unidade de autoria/isolamento deixa de ser apenas a turma e passa a ser o **vínculo docente temporal** já representado por `teacher_class_assignments`.

## 2. Escopo educacional aprovado

Entram no DVD v1.0:

- toda a **Educação Infantil**;
- **1º ao 5º Ano** do Ensino Fundamental — Anos Iniciais;
- **1ª e 2ª Etapa da EJA**.

Ficam fora:

- 6º ao 9º Ano;
- 3ª e 4ª Etapa da EJA;
- Ensino Médio e outras modalidades não aprovadas;
- **AEE**, explicitamente, mesmo quando a escola/turma estiver em contexto integral.

O reconhecimento de série/etapa deve reutilizar `utils/serie_canonical.py`, evitando comparações frágeis por texto. Na **Educação Infantil**, `education_level=educacao_infantil` é a autoridade de enquadramento do segmento; o rótulo local da turma não precisa existir na tabela canônica.

## 3. Princípio de não interferência avaliativa

O DVD define **propriedade, escopo de acesso e proveniência do registro**. Ele não define a modalidade de avaliação.

Consequentemente:

- Educação Infantil preserva seus conceitos e regras atuais;
- 1º e 2º Ano preservam `C / ED / ND` e suas regras atuais;
- 3º ao 5º Ano preservam o modelo avaliativo atual;
- EJA 1ª/2ª preserva o modelo atualmente aplicado pelo SIGESC.

Nenhum `assignment_id` pode converter conceito em nota, nota em conceito, alterar médias, promoção, situação ou apresentação documental.

## 4. Perfis de diário

### `regular`

- conteúdo: habilitado;
- frequência: habilitada e obrigatória conforme regras atuais;
- modo da frequência: `class_daily`;
- natureza da frequência: `official`;
- notas/conceitos: habilitados conforme regime da etapa.

### `integral_content`

- conteúdo: habilitado;
- frequência: desabilitada;
- modo da frequência: `none`;
- natureza da frequência: não aplicável;
- notas/conceitos: desabilitados.

Esse perfil representa componentes da **Educação Integral** cuja responsabilidade no DVD é registrar conteúdo pedagógico próprio, sem criar uma segunda frequência da turma e sem lançar notas/conceitos.

### `shared`

- conteúdo: habilitado;
- frequência: habilitada e oficial;
- modo da frequência: `assignment_session`;
- natureza da frequência: `official`;
- notas/conceitos: habilitados conforme regime da etapa;
- escopo de estudantes: `all` ou `group` quando a escola dividir a turma por estudantes.

## 5. Modos e natureza da frequência

O contrato diferencia **como** a frequência é armazenada/isolada de **qual efeito** ela pode produzir.

### `class_daily`

Preserva a frequência canônica atual da turma/data. É o modo do perfil `regular` e deverá ser mantido sem multiplicar registros por professor.

### `assignment_session`

Reserva, para as fases funcionais posteriores, uma frequência oficial isolada por vínculo/sessão docente. É o modo do perfil `shared` e impede que dois professores compartilhem ou sobrescrevam indevidamente o mesmo registro de frequência.

### `none`

Não existe lançamento de frequência para o vínculo. É o modo do perfil `integral_content`.

Somente frequência explicitamente classificada como:

```text
attendance_purpose = official
```

pode produzir efeitos acadêmicos ou estatísticos.

Valores ausentes, desconhecidos ou futuros não podem ser promovidos implicitamente a `official`. Registros legados ainda sem `attendance_purpose` não são reclassificados nesta fase; a compatibilidade será tratada explicitamente na fase de integração/migração.

## 6. Navegação e páginas existentes

Não serão criadas páginas paralelas para frequência, notas ou conteúdo.

`Meus Diários` será uma camada organizadora. Os acessos tradicionais continuam válidos.

Os fluxos existentes deverão, nas fases posteriores, receber contexto de `assignment_id` conforme a capacidade do vínculo:

- `Attendance.js`;
- `Grades.js`;
- fluxo canônico de conteúdo/objetos de conhecimento.

No perfil `integral_content`, o acesso operacional do vínculo deve direcionar apenas ao fluxo de conteúdo; frequência e notas/conceitos não são capacidades desse perfil.

## 7. Propriedade e autorização

Para professor comum:

- leitura e escrita devem ser limitadas a vínculos ativos que lhe pertencem;
- `teacher_id` enviado pelo frontend não é prova suficiente de autorização;
- a validação efetiva será feita no backend por vínculo, turma, componente, data e vigência.

Usuários de gestão poderão manter visão consolidada conforme suas permissões, com auditoria.

## 8. PDF por vínculo docente

A unidade documental será `assignment_id`, não apenas `class_id` nem apenas `teacher_id`.

Cada PDF deve conter exclusivamente os registros pertencentes ao vínculo docente selecionado.

Os geradores atuais serão preservados visualmente sempre que possível; a mudança principal será a fonte/filtro de dados.

No perfil `integral_content`, o PDF do vínculo contém seus registros pedagógicos de conteúdo; não há frequência nem notas/conceitos próprias do vínculo.

## 9. Migração dos dados existentes

A migração será aditiva e registro a registro.

Prioridade de atribuição pedagógica:

1. `teacher_id` explícito no registro;
2. professor + componente explícitos e compatíveis;
3. vínculo docente único e vigente na data;
4. trilha de auditoria que determine inequivocamente o vínculo;
5. `created_by` apenas quando for professor e houver vínculo compatível;
6. caso contrário: `needs_review`.

`created_by`/`updated_by` representam autoria operacional e, isoladamente, não redefinem a propriedade pedagógica.

Nenhum registro ambíguo será atribuído por suposição.

## 10. Notas/conceitos e granularidade histórica

O documento de nota atual pode reunir vários bimestres. Em turma compartilhada, professores diferentes podem ter sido responsáveis por bimestres diferentes.

Por isso, a migração futura deverá preservar autoria em granularidade suficiente para não atribuir todo o documento ao último professor que o alterou. A estratégia final será definida na fase de notas após auditoria de schema e histórico.

## 11. Multisseriadas

Guardrail conservador da Fase 0:

- uma multisseriada só é considerada elegível **em bloco** se todas as séries/etapas informadas estiverem no escopo;
- combinação `1º + 3º + 5º` é elegível;
- `5º + 6º` é bloqueada para migração automática;
- `EJA 1ª + 2ª` é elegível;
- `EJA 2ª + 3ª` é bloqueada;
- no Fundamental e na EJA, série vazia ou não reconhecida impede classificação automática;
- na Educação Infantil, `education_level=educacao_infantil` define o enquadramento e os rótulos locais não precisam ser canônicos, mas valores vazios continuam bloqueando a classificação em bloco.

Esse guardrail evita migração parcial silenciosa. Caso surja necessidade real de turma multisseriada atravessando a fronteira de escopo, deverá existir decisão específica antes da implementação.

## 12. Invariantes oficiais

1. O DVD v1.0 aplica-se apenas ao escopo educacional aprovado neste documento.
2. AEE permanece fora sem autorização explícita para alterar seu domínio.
3. Modalidade avaliativa é independente do vínculo docente.
4. Todo novo registro integrado ao DVD deverá conhecer seu `assignment_id` quando a granularidade por vínculo se aplicar.
5. Professor comum só consulta/modifica seus próprios vínculos.
6. PDF docente é filtrado por `assignment_id`.
7. Frequência `regular` preserva o modo canônico `class_daily`.
8. Frequência `shared` usa o modo `assignment_session` e permanece `official`.
9. `integral_content` não possui frequência nem notas/conceitos; registra conteúdo.
10. Somente `attendance_purpose=official` produz efeitos acadêmicos/estatísticos.
11. Ausência de registro de frequência não equivale a falta.
12. Migração preserva o histórico e nunca atribui autoria ambígua por suposição.
13. `created_by`/`updated_by` não substituem a autoria pedagógica.
14. A Fase 0 não altera comportamento de produção.

## 13. Limites desta fase

A Fase 0 **não**:

- altera `teacher_class_assignments` persistidos;
- adiciona `assignment_id` a conteúdo, frequência ou notas;
- altera routers;
- altera telas;
- altera PDFs;
- executa migração;
- altera cálculos de frequência;
- altera AEE.

O arquivo `backend/services/diary_assignment_contract.py` é deliberadamente puro/inativo e existe apenas para materializar as invariantes em testes antes da Fase 1.
