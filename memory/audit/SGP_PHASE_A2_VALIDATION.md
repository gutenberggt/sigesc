# Fase A2 — Fechamento Cadastral: Validação

Data-base: 2026-08-13/14  
Branch: `feat/student-cadastral-close-a2`  
Base: `dbbb687fcc0e8e29b5d5facfe11bf84d7aa3b42f`  
Implementação validada: `b8d7b831b492a75350073b88e159e91a91833052`

## Escopo validado

1. Coleta de `address.geographic_location` com domínio interno `urbana` / `rural`.
2. Coleta de `address.differentiated_location` com distinção explícita entre dado ausente e `nao_se_aplica`.
3. Domínio interno de localização diferenciada: `area_assentamento`, `terra_indigena`, `comunidade_quilombola`, `povos_comunidades_tradicionais` e `nao_se_aplica`.
4. Validação backend nos fluxos de criação e atualização do aluno, sem alterar registros apenas por leitura.
5. Exposição da auditoria administrativa já existente `race-community-audit` na interface de alunos.
6. Revisão demográfica assistida: o operador abre o cadastro individual para corrigir valores; não existe inferência nem migração automática de raça/cor.
7. A tabela/codificação externa do CMDE continua responsabilidade futura do mapper; os códigos internos do SIGESC não são tratados como códigos oficiais do MEC.

## Validação automatizada

Workflow temporário `Validate Student Cadastral A2`, execução `31763422645`:

- aplicação determinística das integrações: **SUCCESS**;
- `git diff --check`: **SUCCESS**;
- compilação Python: **SUCCESS**;
- testes `test_student_location.py` e `test_student_demographics.py`: **SUCCESS**;
- instalação frontend com `yarn install --frozen-lockfile`: **SUCCESS**;
- testes `studentLocation`, `ibgeAddress`, `specialEducation` e `studentHealth`: **SUCCESS**;
- build de produção do frontend: **SUCCESS**;
- remoção do workflow temporário antes do commit final: **SUCCESS**.

## Invariantes

- `None`/não informado permanece distinto de uma declaração expressa.
- Comunidade tradicional não permite inferir raça/cor.
- Nenhum registro demográfico legado é reescrito automaticamente.
- A auditoria continua tenant-aware e somente leitura.
- Nenhum envio ao MEC/SGP/CMDE é habilitado nesta fase.
- Nenhum merge ou deploy é autorizado por este documento.
