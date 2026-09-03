# F0 — Adendo de Cobertura Documental da Retificação de Matrícula/Turma

> **Status:** adendo normativo da F0  
> **Issue:** #346  
> **PR:** #347  
> **Baseline auditada:** `9954fe5a687a5cf4e661aec11725a7520e23c6f6`  
> **Escopo:** somente auditoria/contrato. Nenhuma mutação funcional, de dados ou produção.

---

## 1. Motivo deste adendo

A Retificação de Matrícula/Turma altera a fonte de verdade acadêmica de um estudante. Qualquer documento oficial já emitido com a turma/série incorreta pode passar a divergir do estado retificado.

A auditoria final da F0 comprovou que o SIGESC possui **múltiplos trilhos de emissão documental**, com níveis diferentes de rastreabilidade. Portanto, a pergunta operacional "já existe documento emitido?" não pode ser respondida consultando uma única coleção.

Mais importante: alguns endpoints de PDF usados atualmente pelo frontend geram o arquivo diretamente e **não persistem registro de emissão**. Consequentemente, o backend não consegue provar a inexistência histórica de cópias já baixadas/impressas.

Este adendo substitui qualquer interpretação anterior de que `verifiable_documents` ou `school_documents_log`, isoladamente, seriam suficientes para o gate documental da retificação.

---

## 2. Inventário comprovado

### 2.1 Declarações escolares verificáveis — cobertura forte

`backend/services/school_docs_service.py` implementa um fluxo verificável para os tipos:

- `matricula`;
- `frequencia`;
- `escolaridade`.

Esse fluxo:

1. resolve estudante/matrícula/escola/turma;
2. cria snapshot imutável;
3. cria/associa `verifiable_document`;
4. grava `school_documents_log` com `student_id`, `school_id`, `class_id`, `enrollment_id`, código, snapshot, emissor e data;
5. gera o PDF.

Há endpoint administrativo de revogação no domínio de documentos escolares verificáveis.

**Classificação para Retificação:** `TRACKED_AND_REVOCABLE`.

### 2.2 Boletim oficial assíncrono/render job — cobertura forte, trilho próprio

O motor `backend/services/bulletin_renderer.py` cria registro em `bulletin_verifications`, incluindo token hash, estudante/ano, job, metadados de emissão e campos `revoked_at`/`revoked_by`.

O endpoint público de verificação em `backend/routers/bulletin_pdf.py` reconhece o estado revogado.

Também existem `document_render_jobs` e `document_files` para o artefato persistido.

**Classificação para Retificação:** `TRACKED_REVOCABLE_DATA_MODEL`.

A F1 não deve assumir que já existe uma API administrativa de revogação equivalente à de `school_documents`; se ela não existir no momento da implementação, deve ser criada em serviço próprio ou o apply deve falhar fechado quando houver boletim oficial rastreado afetado.

### 2.3 Histórico Escolar oficial assíncrono/render job — cobertura forte, trilho próprio

O motor `backend/services/history_renderer.py` persiste `history_verifications`; o endpoint público em `backend/routers/history_pdf.py` consulta esse registro e reconhece `revoked_at`.

Também há render job/arquivo persistido.

**Classificação para Retificação:** `TRACKED_REVOCABLE_DATA_MODEL`.

Assim como no boletim, a F1 deve comprovar o caminho administrativo de revogação antes de automatizar qualquer invalidação.

### 2.4 Certificado de conclusão — verificável, porém com fallback perigoso

O fluxo de certificado em `backend/routers/documents.py` tenta criar snapshot/verifiable document e inserir QR/código.

Entretanto, o código captura exceção na criação do snapshot e continua a emissão do PDF sem QR/verificação.

Logo há dois estados possíveis:

- certificado com snapshot/código verificável: detectável;
- certificado emitido após falha do snapshot: potencialmente não detectável pelo banco documental.

**Classificação para Retificação:** `PARTIALLY_TRACKED`.

A F2/F3 deve eliminar a emissão silenciosa sem trilha para documentos acadêmicos oficiais que dependam da enturmação. Fail-open documental é incompatível com a Retificação.

### 2.5 Ficha Individual manual de Urgências — emissão rastreada, sem revogação comprovada

`backend/routers/manual_ficha_individual.py` declara que sua única escrita é `manual_document_issuances` e efetivamente grava uma emissão por PDF gerado.

A auditoria não encontrou mecanismo de revogação/supersessão dessa trilha.

**Classificação para Retificação:** `TRACKED_NOT_REVOCABLE_YET`.

Na V1, uma emissão manual afetada deve bloquear o apply até existir política explícita de supersessão/revogação ou decisão administrativa específica registrada no protocolo.

### 2.6 Boletim síncrono legado — lacuna operacional ativa

`GET /api/documents/boletim/{student_id}` em `backend/routers/documents.py`:

- lê banco vivo;
- monta o PDF;
- retorna `StreamingResponse`;
- não grava `bulletin_verifications`, `school_documents_log` ou outro registro de emissão nesse caminho.

A auditoria confirmou que `frontend/src/services/api.js` ainda usa diretamente esse endpoint em `getBoletim()`.

Portanto, não se trata de código morto.

**Classificação para Retificação:** `UNTRACKED_ACTIVE_PATH`.

### 2.7 Ficha Individual síncrona legado — lacuna operacional ativa

`GET /api/documents/ficha-individual/{student_id}` em `backend/routers/documents.py`:

- lê matrícula/notas/frequência atuais;
- gera a Ficha Individual;
- em caso de remanejamento pode mesclar ficha destino + fichas de origem;
- retorna o PDF diretamente;
- não registra emissão persistente nesse caminho.

`frontend/src/services/api.js` ainda usa esse endpoint em `getFichaIndividual()`.

**Classificação para Retificação:** `UNTRACKED_ACTIVE_PATH`.

O mesmo cuidado se aplica à Ficha Individual de Dependência enquanto não houver trilha de emissão comprovada.

### 2.8 Declarações síncronas legado — lacuna operacional ativa

`backend/routers/documents.py` mantém rotas diretas para, entre outras:

- Declaração de Matrícula;
- Declaração de Frequência;
- Declaração de Transferência.

Essas rotas geram `StreamingResponse` diretamente. A auditoria do frontend confirmou que a URL antiga de Declaração de Matrícula ainda é exposta em `frontend/src/services/api.js`.

A existência paralela de `school_docs_service.py` não torna automaticamente as rotas antigas rastreáveis.

**Classificação para Retificação:** `UNTRACKED_ACTIVE_OR_REACHABLE_PATH`.

### 2.9 Diário Escolar publicado — snapshot imutável

`diary_snapshots` representa documento institucional congelado. O contrato do snapshot determina que payload e hash publicados nunca são recalculados a partir do banco vivo.

Uma retificação que retire o estudante de frequências já incorporadas a snapshot publicado não pode alterar o snapshot antigo.

**Classificação para Retificação:** `IMMUTABLE_VERSIONED_DOCUMENT`.

Deve existir supersessão/revogação/reemissão, nunca rewrite.

### 2.10 Livro de Promoção — identidade persistida, emissão não comprovável

`promotion_books` persiste a identidade/número do livro por turma/ano. O endpoint de PDF síncrono reconstrói o Livro de Promoção a partir do banco e devolve bytes.

A mera existência de `promotion_books` comprova que um número foi atribuído, mas **não comprova que determinado PDF foi efetivamente baixado, impresso ou assinado**.

**Classificação para Retificação:** `PARTIAL_AUDIT_ONLY`.

O dry-run deve verificar se a turma possui Livro de Promoção numerado e elevar o risco documental, mas não deve confundir `book_number` com prova de emissão.

---

## 3. Conclusão de cobertura

### DOC-01 — Não existe prova global de ausência de emissão

Enquanto caminhos `UNTRACKED_ACTIVE_PATH` permanecerem acessíveis, o SIGESC **não pode afirmar**:

> "Nenhum documento oficial referente a este estudante foi emitido."

O máximo tecnicamente defensável é:

> "Nenhuma emissão foi encontrada nos trilhos documentais persistidos que o SIGESC consegue consultar; existem caminhos históricos/ativos de emissão sem ledger, portanto cópias previamente geradas podem não ser detectáveis."

Essa distinção deve aparecer no dry-run e na confirmação administrativa.

### DOC-02 — Cobertura documental é um vetor, não um booleano

O dry-run futuro deverá retornar algo equivalente a:

```json
{
  "document_impact": {
    "coverage": "partial",
    "tracked": {
      "school_documents": [],
      "bulletins": [],
      "histories": [],
      "certificates": [],
      "manual_ficha_issuances": [],
      "diary_snapshots": [],
      "promotion_books": []
    },
    "untracked_paths_present": [
      "documents.boletim.sync",
      "documents.ficha_individual.sync",
      "documents.declaracoes.sync"
    ],
    "can_prove_no_prior_issuance": false,
    "warnings": []
  }
}
```

A F1 pode alterar o shape, mas não a semântica.

---

## 4. Política normativa de documentos para a Retificação

### DOC-03 — Documento persistido afetado nunca é apagado

Nenhum registro documental deve ser deletado para "limpar" a turma errada.

Regra:

- preservar o artefato/registro original;
- marcar inválido/revogado/superseded quando o subsistema suportar;
- registrar protocolo da Retificação;
- gerar nova emissão a partir do estado retificado quando solicitado.

### DOC-04 — Revogação deve ser feita pelo domínio documental

A saga da Retificação não deve escrever `revoked_at` diretamente em coleções documentais espalhadas.

A F1/F2 deverá chamar serviços canônicos de revogação/supersessão. Se um tipo de documento não possuir esse serviço, a operação falha fechado ou fica pendente de etapa administrativa explícita.

### DOC-05 — Ficha manual sem revogação comprovada bloqueia automação total

Se `manual_document_issuances` indicar Ficha Individual manual incompatível com a retificação, a V1 não deverá ocultar o fato nem simplesmente continuar.

Estado recomendado do dry-run:

`BLOCKED_DOCUMENT_REVIEW_REQUIRED`.

### DOC-06 — Snapshot de Diário publicado permanece imutável

A retificação nunca altera `diary_snapshots.payload`, hash ou PDF publicado. Deve haver nova versão/supersessão se a instituição decidir republicar o período.

### DOC-07 — Boletim/Histórico verificáveis precisam de invalidação coordenada

Se um Boletim ou Histórico rastreado contiver a turma/série incorreta, o apply somente poderá concluir como `COMPLETED` depois de:

1. registrar o documento afetado no snapshot da retificação;
2. invalidá-lo/supersedê-lo pelo serviço documental correspondente;
3. registrar `rectification_protocol` ou referência equivalente na auditoria;
4. deixar explícita a necessidade de nova emissão.

Se a revogação falhar, a saga não pode declarar sucesso integral.

### DOC-08 — Cópias não rastreadas exigem reconhecimento administrativo

Devido aos endpoints síncronos ativos sem ledger, a execução deverá registrar declaração explícita do operador, em linguagem equivalente a:

> "Estou ciente de que podem existir PDFs anteriormente baixados ou impressos por caminhos sem registro de emissão. A retificação corrige a fonte de verdade do SIGESC e documentos anteriores incompatíveis devem ser desconsiderados e substituídos por nova emissão oficial."

Essa declaração não substitui a migração arquitetural dos documentos; ela apenas torna a limitação explícita durante a transição.

---

## 5. Gate obrigatório antes de habilitar Retificação em produção

### DOC-GATE-01 — Instrumentação dos caminhos usados pela UI

A Retificação não deve chegar à F3 produtiva sem que os caminhos de emissão usados pela interface sejam tratados por uma das estratégias abaixo:

**Estratégia preferencial:**

- migrar a UI para os fluxos verificáveis/render jobs canônicos;
- descontinuar o uso operacional das rotas síncronas antigas para documentos oficiais sensíveis à enturmação.

**Estratégia transitória aceitável:**

- manter a rota síncrona, mas fazê-la registrar uma emissão imutável/auditável no mesmo domínio documental canônico antes de devolver o PDF.

Não é aceitável manter indefinidamente uma rota oficial que possa gerar PDF sem qualquer prova de emissão.

### DOC-GATE-02 — Certificado não pode mais ser fail-open

Antes da F3, falha ao criar snapshot/verificação de Certificado deve impedir a emissão ou encaminhar explicitamente para modo de contingência auditado.

### DOC-GATE-03 — Inventário documental unificado

Deverá existir um serviço read-only único, por estudante/ano, capaz de agregar ao menos:

- `school_documents_log` + `verifiable_documents`;
- `bulletin_verifications`;
- `history_verifications`;
- `manual_document_issuances`;
- snapshots/document render jobs relevantes;
- `diary_snapshots` afetados;
- `promotion_books` da turma/ano;
- alertas de cobertura incompleta.

A Retificação deve consumir esse serviço; não duplicar queries documentais dentro do router.

---

## 6. Impacto no rollback da Retificação

O rollback não pode usar apenas a regra hoje existente em outros fluxos que consulta `school_documents_log` após uma operação.

### DOC-RB-01

O rollback deve ser bloqueado quando, após a Retificação, houver nova emissão rastreada baseada no estado retificado e a reversão faria esse documento ficar incorreto.

### DOC-RB-02

O gate de rollback deve consultar o inventário documental unificado, não uma coleção isolada.

### DOC-RB-03

Caminhos históricos sem ledger impedem prova absoluta de ausência de cópias, mas não devem tornar todo rollback impossível. A limitação deve ser registrada no protocolo e a decisão deve permanecer fail-closed nos documentos efetivamente rastreados.

---

## 7. Cenários adicionais de teste para F1/F2

Adicionar à matriz principal:

1. retificação sem nenhum documento rastreado → dry-run `coverage=partial`, nunca `can_prove_no_prior_issuance=true` enquanto houver rota ativa sem ledger;
2. declaração verificável de matrícula emitida → listar código/snapshot e plano de revogação;
3. boletim renderizado/verificável emitido → listar `bulletin_verifications`;
4. histórico verificável emitido → listar `history_verifications`;
5. Ficha Manual de Urgências emitida → bloquear para revisão documental;
6. snapshot de Diário publicado contendo o estudante → preservar snapshot e exigir supersessão/revisão;
7. Livro de Promoção numerado → warning de alto impacto, sem afirmar que o PDF foi emitido;
8. certificado rastreado → listar e invalidar pelo domínio verificável;
9. certificado emitido em cenário simulado de falha do snapshot → teste deve demonstrar que a F2/F3 elimina o fail-open;
10. emissão documental nova entre dry-run e apply → detectar drift e bloquear/reexecutar dry-run;
11. revogação documental falha durante saga → estado `FAILED_COMPENSATION_REQUIRED`/equivalente, nunca `COMPLETED`;
12. documento novo emitido após retificação → rollback bloqueado por dependência posterior;
13. UI de Boletim migrada para fluxo rastreável → teste garante que nenhuma emissão oficial ocorre sem ledger;
14. UI de Ficha Individual migrada/instrumentada → mesma garantia;
15. declaração síncrona antiga instrumentada ou removida do fluxo operacional → mesma garantia.

---

## 8. Decisão arquitetural resultante

### DEC-DOC-F0

A Retificação de Matrícula/Turma somente é segura como capacidade institucional quando **estado acadêmico e estado documental forem tratados como uma única saga**, embora cada documento preserve sua própria imutabilidade.

Assim:

- a F1 pode implementar o domínio/dry-run sem mutar documentos;
- a F2 deve fornecer inventário documental unificado e capacidades de invalidação/supersessão necessárias;
- a F3 produtiva fica condicionada à instrumentação/migração dos caminhos oficiais ativos que hoje emitem PDF sem ledger.

Essa exigência não amplia a Retificação para uma reescrita geral do módulo de documentos; ela fecha especificamente a impossibilidade de garantir consistência institucional após uma correção retroativa de enturmação.

---

## 9. Segurança deste adendo

- nenhuma coleção alterada;
- nenhum endpoint alterado;
- nenhuma emissão documental alterada;
- nenhum schema/índice alterado;
- nenhum AEE alterado;
- nenhum merge em `main`;
- nenhum deploy.

Este arquivo é exclusivamente contrato/auditoria da F0.
