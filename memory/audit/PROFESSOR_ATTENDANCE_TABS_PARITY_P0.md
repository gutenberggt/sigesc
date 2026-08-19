# P0 — Paridade das abas de Frequência do Professor no DVD

Data: 2026-08-19

## Objetivo

Dar ao professor, dentro de **Meus Diários / Diário por Vínculo**, acesso funcional e seguro às abas da página **Controle de Frequência**, preservando escopo de turma, vínculo, tenant e autoria pedagógica.

Não faz parte deste P0:

- AEE;
- liberar configurações globais de frequência para professor;
- migrar/reescrever frequência histórica;
- atribuir `assignment_id` retroativamente;
- expor dados de outros professores/turmas.

## Matriz

| Superfície | Situação anterior | P0 |
|---|---|---|
| Lançamento | DVD-aware, mas `class_daily` podia conflitar entre componentes regulares do mesmo professor | Reutiliza o assignment proprietário já existente quando é do mesmo professor/turma, sem transferir autoria |
| Registros | Datas/resumo apenas dos documentos com `assignment_id`; cutover 18/08 fazia histórico anterior desaparecer | Ponte de leitura class_daily para vínculos 38G-B com origem legada revalidada |
| Informações | Endpoint aceitava `class_id` após mera autenticação; DVD não prendia a aba ao vínculo | Assignment-aware, roster autorizado, escola/turma travadas no vínculo; professor legado também precisa provar alocação |
| Relatórios | DVD-aware, mas via apenas documentos pós-cutover do assignment | Usa a mesma fonte consolidada de histórico class_daily + DVD |
| PDF | DVD-aware, mas via apenas documentos pós-cutover | Usa a mesma fonte consolidada de histórico class_daily + DVD |
| Alertas | Deliberadamente indisponível em DVD | Alertas calculados pelo relatório canônico do próprio assignment; integrador `pdf_only` continua sem alerta acadêmico |
| Configurações | Admin/secretaria | Permanece administrativo |

## Regra histórica

A compatibilidade histórica só é habilitada para vínculo `regular/class_daily/official` cuja proveniência de cutover prove:

- `cutover_provenance.apply_phase == 38G-B`;
- `cutover_provenance.apply_state == ACTIVATED`;
- `source_legacy_assignment_id` presente;
- alocação legada ainda corresponde a professor, turma, componente e ano.

Os documentos legados:

- continuam na coleção `attendance`;
- continuam sem `assignment_id`;
- são marcados apenas na resposta interna como `legacy_history=true` e `read_only=true`;
- nunca são atualizados pela ponte.

Para a chave `class_daily`, se legado e DVD coexistirem na mesma data/período, o documento DVD prevalece apenas na leitura consolidada para impedir dupla contagem.

## Segurança

### Informações dos estudantes

No modo DVD, a lista vem de `build_attendance_roster()` após `resolve_attendance_assignment()`. Somente IDs do roster autorizado podem ter nome, nascimento, mãe e telefone retornados.

No fluxo legado, professor sem `assignment_id` deve provar `teacher_assignments` ativo para a turma/ano. Em turma DVD, o fluxo legado retorna `DVD_ASSIGNMENT_REQUIRED`.

### Alertas

No DVD, `/attendance/alerts?assignment_id=...` reutiliza `_dvd_report`, que já passa pela autorização central. Assim, nenhum relatório consolidado de outra turma/vínculo é usado.

Componente integrador (`attendance_purpose=pdf_only`) retorna zero alertas acadêmicos por contrato.

## Invariantes

1. Nenhuma migração retroativa.
2. Nenhuma escrita no histórico legado.
3. Nenhuma alteração em AEE.
4. Nenhum bypass de `DVD_ASSIGNMENT_REQUIRED`.
5. Professor não recebe permissão para configurações globais.
6. Mesmo professor pode operar `class_daily` por seus componentes regulares sem reatribuir o documento já existente.
7. Registros, Relatórios, PDF e Alertas compartilham a mesma fonte de leitura histórica autorizada.
