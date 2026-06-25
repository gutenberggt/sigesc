# Roteiro de Homologação Operacional — Transferência Institucional (Re-homing)

> Objetivo: comprovar, em cenário real, que **transferência** e **rollback** funcionam corretamente
> ponta a ponta, antes de liberar a funcionalidade aos Super Admins.
> Executor: 1 Super Admin + 1 observador (coordenação/secretaria) registrando evidências.
> Ambiente: homologação/staging com dados completos de UMA escola. **Nunca em produção sem aprovação.**

Referência técnica:
- Endpoints: `/api/admin/school-transfer/dry-run`, `/execute`, `/{protocol}/rollback`,
  `/{protocol}/rollback-eligibility`, `/{protocol}/receipt`
- Telas: Painel `/admin/transferencias` · Wizard `/admin/transferencias/nova`
- Frases obrigatórias:
  - Execução: `CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL`
  - Reversão:  `CONFIRMO A REVERSÃO DA TRANSFERÊNCIA`
- Janela de reversão: **7 dias** OU **1ª emissão de documento oficial** (o que ocorrer primeiro).

---

## 1. Escolha da escola piloto e critérios de seleção

Selecionar UMA escola origem que maximize a cobertura de cenários sem ser a maior da rede.

**Critérios obrigatórios:**
- [ ] Origem e destino na **mesma mantenedora** (regra do motor — destino só lista escolas da mesma mantenedora).
- [ ] Destino com **calendário letivo do ano vigente** configurado (validação `DESTINATION_CALENDAR_OPEN`).
- [ ] Origem com **volume pequeno/médio** (recomendado: 2–5 turmas, 30–120 alunos) — suficiente para evidências, fácil de auditar manualmente.
- [ ] Origem que contenha **diversidade de dados**: pelo menos 1 turma com frequência lançada, notas lançadas, conteúdo (Objetos de Conhecimento), e idealmente ≥1 aluno com **AEE** e ≥1 com **Bolsa Família**.
- [ ] **Nenhuma emissão de documento oficial pendente/planejada** durante a janela de teste (para não fechar a janela de rollback acidentalmente).

**Critérios desejáveis:**
- [ ] Turmas de níveis distintos (ex.: 1 Infantil/Anos Iniciais multi-componente + 1 Anos Finais).
- [ ] Aluno com matrícula ativa e histórico de ano anterior (para validar `school_history[]`).

**Registrar:** nome/ID da escola origem, destino, mantenedora, ano letivo, nº de turmas/alunos esperados.

---

## 2. Checklist pré-transferência (linha de base / baseline)

Antes de qualquer ação, **capturar o estado atual** (prints + planilha) para comparação posterior.

- [ ] **Turmas**: listar turmas da origem (nome, série, turno, `school_id`, `academic_year`).
- [ ] **Alunos**: total de alunos ativos por turma.
- [ ] **Matrículas**: total de matrículas ativas (enrollments).
- [ ] **Frequência**: nº de registros e 1 amostra (1 aluno, 1 data) com valor conhecido.
- [ ] **Notas**: nº de registros e 1 amostra (1 aluno, 1 componente, 1 etapa) com valor conhecido. Anotar se há notas **bloqueadas/migradas** (cadeado).
- [ ] **Conteúdo (Objetos de Conhecimento)**: nº de registros e 1 amostra (turma, data).
- [ ] **AEE**: nº de planos/atendimentos e 1 aluno-amostra.
- [ ] **Bolsa Família**: nº de registros de acompanhamento e 1 aluno-amostra.
- [ ] **Relatórios críticos** (gerar e arquivar PDFs ANTES): Frequência mensal, Rendimento/Boletim, **Histórico Escolar** de 1 aluno. Guardar como "antes".
- [ ] **`school_history[]`** de 1 turma (anotar segmentos atuais: school_id, start_date, end_date).
- [ ] **Status da escola origem** (deve estar `active`).
- [ ] Confirmar operador logado como **super_admin** e que possui a senha em mãos (re-autenticação).
- [ ] Backup/snapshot do banco de homologação (responsabilidade de infra), se disponível.

> Saída desta etapa: **planilha-baseline** com todos os números e amostras + pasta "ANTES" com PDFs.

---

## 3. Execução do Dry Run

Via Wizard (`/admin/transferencias/nova`) — recomendado — ou via API.

- [ ] Etapa 1: selecionar **origem** e **destino**; conferir que o resumo mostra o nº de turmas esperado.
- [ ] Etapa 2: escolher **escola inteira** (recomendado para o piloto) ou turmas específicas.
- [ ] Etapa 3: executar **Dry Run** e validar:
  - [ ] `can_execute = true` (sem bloqueios 🔴).
  - [ ] **Contagens** batem com a baseline (turmas, alunos, matrículas, frequência, notas, conteúdo, AEE, Bolsa Família). **Divergência = PARAR e investigar.**
  - [ ] Avisos 🟡 (se houver) compreendidos e aceitáveis.
  - [ ] Botão "Avançar para confirmação" habilitado.
- [ ] Registrar print da tela de Dry Run (contagens + validações).

> Critério de passagem: contagens do Dry Run == baseline e `can_execute=true`.

---

## 4. Execução da transferência real

- [ ] Etapa 4 (Confirmação forte): conferir o **resumo** (X turmas / Y alunos / Z matrículas, origem → destino).
- [ ] Preencher **justificativa** (≥10 caracteres, texto operacional real), **senha** e a **frase exata** `CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL`.
- [ ] Confirmar que o botão só habilita com os 3 campos corretos.
- [ ] **Executar.**
- [ ] Etapa 5 (Resultado): anotar **protocolo** (`TRANSF-AAAA-NNNNNN`), data/hora, nº de turmas/alunos movidos, e se a **escola origem foi encerrada** (esperado: Sim, no modo escola inteira).
- [ ] Registrar horário exato (`executed_at`) — referência para a janela de 7 dias.

---

## 5. Validação pós-transferência

Comparar contra a baseline. Para cada item: **conferir que os dados foram para o destino e que NADA foi perdido.**

- [ ] **Turmas**: `school_id` == destino; `school_history[]` da turma agora tem **novo segmento aberto** apontando ao destino (start_date ≈ data da transferência, end_date = null) e o segmento da origem **fechado** (end_date preenchido). Sem sobreposição/lacuna.
- [ ] **Alunos**: todos os alunos das turmas agora com `school_id` == destino; total idêntico à baseline.
- [ ] **Matrículas**: total idêntico; `school_id` == destino.
- [ ] **Frequência**: total idêntico; amostra conhecida preservada (mesmo valor).
- [ ] **Notas**: total idêntico; amostra preservada; notas bloqueadas/migradas continuam intactas.
- [ ] **Conteúdo**: total idêntico; amostra preservada.
- [ ] **AEE**: planos/atendimentos preservados; aluno-amostra vinculado ao destino.
- [ ] **Bolsa Família**: registros preservados; aluno-amostra vinculado ao destino.
- [ ] **Relatórios críticos** (gerar DEPOIS e comparar com a pasta "ANTES"):
  - [ ] **Frequência mensal**: períodos passados ainda atribuídos corretamente (resolução temporal via `school_history[]`); período atual no destino.
  - [ ] **Rendimento/Boletim**: valores idênticos aos de "antes".
  - [ ] **Histórico Escolar (PDF)**: períodos anteriores mostram a **escola correta da época** (origem), não a atual — comprova que o relatório usa `resolve_school_at()` e não vaza a escola atual.
- [ ] **Acesso da escola origem**: aparece como **encerrada** (não recebe novos lançamentos).

> Critério de passagem: 100% dos itens conferem; relatórios pós == pré (exceto o vínculo institucional atual, que deve refletir o destino).

---

## 6. Geração e validação do recibo PDF com QR Code

- [ ] No Painel, linha da transferência → **Gerar recibo**. PDF abre.
- [ ] Conferir campos: protocolo, status (Executada), origem, destino, turmas, alunos afetados, matrículas, operador, justificativa, data/hora.
- [ ] **Escanear o QR Code** → deve abrir a página pública de verificação `/v/{token}` e confirmar o documento como **válido/autêntico**.
- [ ] Conferir o **código de verificação** humano impresso no rodapé.
- [ ] Confirmar que **gerar o recibo NÃO fechou a janela de rollback** (o recibo não é documento de aluno; a transferência deve continuar reversível — ver etapa 7).
- [ ] Arquivar o PDF do recibo como evidência.

---

## 7. Teste completo de rollback pela interface

> Executar **dentro da janela de 7 dias** e **sem ter emitido documento oficial de aluno** após a transferência.

- [ ] (Opcional) Conferir elegibilidade: a linha do painel mostra **"Reversível (N dias)"**.
- [ ] No Painel, linha da transferência → **Reverter**.
- [ ] No modal: justificativa (≥10), senha, e frase exata `CONFIRMO A REVERSÃO DA TRANSFERÊNCIA`.
- [ ] Confirmar reversão. Anotar **protocolo de rollback** (`ROLLBACK-AAAA-NNNNNN`) e `origin_reopened`.
- [ ] **Teste de idempotência**: tentar reverter o MESMO protocolo novamente → deve retornar "já revertida" com o **mesmo** protocolo de rollback, **sem efeito colateral**.
- [ ] **Teste de bloqueio (opcional, controlado)**: em uma 2ª transferência de teste, emitir um documento oficial de aluno e então tentar reverter → deve **bloquear** com motivo `OFFICIAL_DOCUMENT_EMITTED`. (Apenas se houver tempo; não obrigatório no piloto principal.)

---

## 8. Validação pós-rollback

Comparar novamente contra a **baseline** (estado original). Tudo deve ter **voltado à origem**.

- [ ] **Turmas**: `school_id` == origem; `school_history[]` **idêntico ao baseline** (segmento do destino removido; sem sobreposição/lacuna).
- [ ] **Alunos / Matrículas**: de volta à origem; totais idênticos ao baseline.
- [ ] **Frequência / Notas / Conteúdo**: amostras preservadas e vinculadas à origem.
- [ ] **AEE / Bolsa Família**: preservados e vinculados à origem.
- [ ] **Escola origem reaberta**: status `active` (se foi encerrada pela transferência).
- [ ] **Relatórios críticos** (gerar de novo): devem ficar **iguais à pasta "ANTES"** (Frequência, Rendimento, Histórico Escolar).
- [ ] **Auditoria**: confirmar registro imutável da reversão (quem, quando, justificativa, IP, protocolo original e de reversão) e que o **evento original foi preservado** + evento de reversão adicionado (append-only).
- [ ] **Recibo pós-rollback**: gerar recibo novamente → deve refletir status **Revertida** com dados da reversão.

> Critério de passagem: estado pós-rollback == baseline em 100% dos itens.

---

## 9. Critérios objetivos de aprovação (liberação aos Super Admins)

Liberar **somente se TODOS** forem verdadeiros:

1. [ ] Dry Run com contagens == baseline e `can_execute=true`.
2. [ ] Transferência executada com protocolo gerado e escola origem encerrada (modo escola inteira).
3. [ ] Pós-transferência: **0 perdas** de dados em todos os domínios (turmas, alunos, matrículas, frequência, notas, conteúdo, AEE, Bolsa Família).
4. [ ] Relatórios críticos pós == pré; Histórico Escolar respeita a escola temporal (`school_history[]`).
5. [ ] Recibo PDF gerado, campos corretos e **QR verificável como autêntico**.
6. [ ] Rollback executado pela UI com sucesso; **idempotência** comprovada.
7. [ ] Pós-rollback: estado **idêntico ao baseline** em 100% dos itens; escola origem reaberta.
8. [ ] Auditoria imutável presente e correta (transferência + reversão).
9. [ ] Nenhum erro 500/exception relevante nos logs do backend durante todo o fluxo.
10. [ ] Aprovação **formal por escrito** do responsável (você).

> Qualquer item reprovado = **não liberar**. Tratar como bloqueio.

---

## 10. Plano de contingência (se a homologação falhar)

**Princípio:** a transferência é projetada para ser reversível e idempotente; a primeira ação diante de qualquer anomalia é **reverter**.

- **Falha durante o Dry Run** (contagens divergentes / bloqueio inesperado):
  - Não executar. Registrar evidências, abrir investigação. Não há mutação — risco zero.
- **Falha/anomalia após a execução** (dados divergentes, relatório errado):
  - **Executar rollback imediatamente** pela UI (dentro da janela).
  - Validar pós-rollback (etapa 8). Se voltar ao baseline → incidente contido.
- **Rollback falha parcialmente** (erro no meio):
  - Por design, o estado **não** é marcado como revertido e o lock é liberado → **reexecutar o rollback** (é idempotente). 
  - Se persistir após 2 tentativas: **não liberar**; acionar o time de desenvolvimento com o protocolo, logs e horário; restaurar via **backup/snapshot** do banco de homologação.
- **Janela expirada ou documento oficial já emitido** (rollback bloqueado):
  - Não forçar. Avaliar correção manual assistida pelo time de dev (fora do escopo do piloto) ou restaurar via backup.
- **Comunicação:** manter a escola origem/destino cientes de que é um **teste de homologação**; não usar dados para decisões oficiais até a aprovação.
- **Registro de incidente:** protocolo, etapa da falha, evidências (prints/PDFs/logs), ação tomada, resultado.

---

### Anexos a arquivar como evidência
- Planilha-baseline (números e amostras).
- Pastas "ANTES" / "DEPOIS-TRANSFERÊNCIA" / "DEPOIS-ROLLBACK" com PDFs dos relatórios.
- Prints: Dry Run, Resultado da execução, Recibo + verificação QR, Modal/resultado do rollback.
- Protocolos: transferência (`TRANSF-...`) e rollback (`ROLLBACK-...`).
- Aprovação formal final.
