# Validação — Fase A do Cadastro Canônico SGP

Data: 2026-08-13  
Branch: `feat/sgp-student-canonical-alignment`

## Escopo validado

A Fase A alinha o cadastro interno do SIGESC para futura interoperabilidade com SGP/CMDE sem habilitar envio real ao MEC.

Foram validados:

- endereço próprio do estudante, com CEP, Município, UF e códigos IBGE pré-preenchidos a partir da Unidade Mantenedora apenas na criação e permanecendo editáveis;
- Nome Social e opção de sexo `prefere_nao_informar`;
- metadados adicionais persistidos na entidade `Enrollment`;
- segundo celular do responsável;
- vínculo de responsável legal principal por estudante, com unicidade e sem substituição silenciosa;
- correção do contrato `GuardianUpdate` para persistir os campos editáveis do formulário;
- contenção de Raça/Cor × Comunidade Tradicional, preservando legado e impedindo nova contaminação semântica;
- auditoria administrativa somente leitura para registros demográficos que exigem revisão.

## Segurança multi-tenant

O endpoint `/students/race-community-audit` usa `apply_tenant_filter({}, current_user, request)`, o helper canônico da plataforma. Assim:

- `super_admin` sem escopo explícito pode operar cross-tenant conforme regra da plataforma;
- `super_admin` com mantenedora ativa respeita esse escopo;
- demais perfis ficam restritos à própria mantenedora;
- usuário não-super_admin sem `mantenedora_id` opera em modo **fail-closed**, sem exposição de dados de outros tenants.

## Compatibilidade e contenção

Nenhum registro legado é migrado ou reinterpretado automaticamente. Em especial, valores como `quilombola`, `cigano`, `ribeirinho` e `extrativista` já existentes em `color_race` continuam legíveis e são sinalizados para revisão; novos cadastros deixam de oferecer esses valores como raça/cor.

Comunidade tradicional não é usada para inferir raça/cor. Qualquer futura migração dependerá de auditoria sobre dados reais e etapa própria de revisão.

## Validações automatizadas executadas

- compilação de sintaxe Python dos arquivos alterados;
- testes de vínculo canônico de responsável principal;
- testes da auditoria de raça/cor × comunidade tradicional;
- testes canônicos de endereço IBGE;
- testes canônicos de Educação Especial já existentes;
- build completo do frontend.

Os codemods e workflows usados exclusivamente para construção/validação da feature foram removidos antes da revisão final do PR.

## Resultado

A Fase A fica tecnicamente preparada para revisão via Pull Request. Esta validação **não autoriza merge, deploy, migração de dados nem envio ao MEC**; essas ações dependem de etapas e aprovações próprias.
