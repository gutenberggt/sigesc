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

O reconhecimento de série/etapa deve reutilizar `utils/serie_canonical.py`, evitando comparações frágeis por texto.

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
- natureza da frequência: `official`;
- notas/conceitos: habilitados conforme regime da etapa.

### `integrator`

- conteúdo: habilitado;
- frequência: habilitada, porém opcional;
- natureza da frequência: `pdf_only`;
- notas/conceitos: desabilitados no vínculo integrador.

### `shared`

- conteúdo: habilitado;
- frequência: habilitada e oficial;
- notas/conceitos: habilitados conforme regime da etapa;
- escopo de estudantes: `all` ou `group` quando a escola dividir a turma por estudantes.

## 5. Regra positiva de frequência

Somente frequência explicitamente classificada como:

```text
attendance_purpose = official
```

pode produzir efeitos acadêmicos ou estatísticos.

`pdf_only`:

- pode ficar em branco;
- não gera pendência;
- não gera falta;
- não soma presença;
- não entra no numerador nem no denominador do percentual;
- não alimenta Busca Ativa;
- não alimenta Bolsa Família;
- não interfere em aprovação/reprovação;
- não entra em boletim, histórico, ficha individual, declaração de frequência ou indicadores oficiais;
- aparece somente no contexto documental/PDF do respectivo diário docente.

Registros legados ainda sem `attendance_purpose` não são reclassificados nesta fase. A compatibilidade será tratada explicitamente na fase de integração/migração.

## 6. Navegação e páginas existentes

Não serão criadas páginas paralelas para frequência, notas ou conteúdo.

`Meus Diários` será uma camada organizadora. Os acessos tradicionais continuam válidos.

Os fluxos existentes deverão, nas fases posteriores, receber contexto de `assignment_id`:

- `Attendance.js`;
- `Grades.js`;
- fluxo canônico de conteúdo/objetos de conhecimento.

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

Para componente integrador, qualquer frequência exibida no PDF deve ser identificada como **acompanhamento pedagógico/documental sem efeito na frequência escolar oficial**.

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
- série vazia/não reconhecida impede classificação automática.

Esse guardrail evita migração parcial silenciosa. Caso surja necessidade real de turma multisseriada atravessando a fronteira de escopo, deverá existir decisão específica antes da implementação.

## 12. Invariantes oficiais

1. O DVD v1.0 aplica-se apenas ao escopo educacional aprovado neste documento.
2. AEE permanece fora sem autorização explícita para alterar seu domínio.
3. Modalidade avaliativa é independente do vínculo docente.
4. Todo novo registro integrado ao DVD deverá conhecer seu `assignment_id`.
5. Professor comum só consulta/modifica seus próprios vínculos.
6. PDF docente é filtrado por `assignment_id`.
7. Somente `official` produz efeitos acadêmicos/estatísticos.
8. `pdf_only` é opcional e exclusivamente documental.
9. Ausência de registro de frequência não equivale a falta.
10. Migração preserva o histórico e nunca atribui autoria ambígua por suposição.
11. `created_by`/`updated_by` não substituem a autoria pedagógica.
12. A Fase 0 não altera comportamento de produção.

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
