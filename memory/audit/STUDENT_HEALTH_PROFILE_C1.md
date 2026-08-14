# Fase C1 — Ficha de Saúde do Estudante

Branch: `feat/student-health-profile`

Escopo: implementar perfil de saúde separado do cadastro genérico do estudante, com acesso restrito, auditoria sem registrar conteúdo clínico, escopo multi-tenant e nenhuma inclusão automática em exports/listagens gerais.

Campos implementados: tipo sanguíneo; alergias; comorbidades; medicação de uso contínuo; necessidade nutricional individualizada; observações de saúde. Campos condicionais usam semântica tri-state (`Sim`, `Não`, `Não informado`).

## Segurança e privacidade

- coleção segregada `student_health_profiles`;
- acesso somente por estudante, sem endpoint de listagem em massa;
- escopo de mantenedora aplicado em leitura e escrita;
- secretário e diretor sujeitos ao vínculo da escola do estudante;
- professor, aluno e demais papéis não autorizados recebem 403;
- diretor possui leitura, sem permissão de escrita;
- leitura e alteração são auditadas;
- valores clínicos não são registrados no log de auditoria; somente metadados e nomes de campos alterados;
- campos de saúde foram adicionados à sanitização defensiva do serviço de auditoria;
- o perfil não integra automaticamente documentos, listagens ou exports genéricos.

## Validação pré-PR

Workflow controlado `Validate Student Health C1` concluído com sucesso em 14/08/2026 (run `31761823662`). Foram aprovados: aplicação determinística das integrações, `git diff --check`, compilação Python, 6 testes backend da ficha de saúde, testes frontend `studentHealth`, `ibgeAddress` e `specialEducation`, e build completo de produção do frontend. O workflow e o patch temporários foram removidos antes do commit final da implementação.

Nenhuma alteração de produção ou envio de dados de saúde ao MEC/CMDE é autorizada por este documento. Qualquer merge em `main` depende dos gates normais do repositório e de aprovação explícita.
