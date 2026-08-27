# Baseline Estratégico do SIGESC — 2026-08-27

**Natureza:** fotografia de continuidade do projeto  
**Data de referência:** 2026-08-27  
**Objetivo:** preservar o estado estratégico mínimo necessário para retomar o projeto sem depender de conversas históricas.

> Este documento não substitui código, testes, contratos, ADRs, dossiês ou dados operacionais. Ele funciona como mapa de estado e aponta os invariantes que devem sobreviver à limpeza de conversas.

## 1. Identidade e produção

- Sistema: **SIGESC — Sistema Integrado de Gestão Escolar**.
- Repositório principal: `gutenberggt/sigesc`.
- Produção: `https://sigesc.aprenderdigital.top/`.
- Stack principal: FastAPI + React + MongoDB + Docker + PWA.
- Modelo: plataforma educacional SaaS multi-tenant.
- Deploy de produção: fluxo containerizado via Coolify.

## 2. Invariantes arquiteturais

- isolamento lógico por tenant/mantenedora;
- autorização por papel e escopo;
- consultas e escritas sensíveis devem respeitar tenant scope;
- postura fail-closed diante de ambiguidades de autorização, tenant ou mapeamento externo;
- regras de negócio com fonte única não devem ser duplicadas em routers/clients;
- mudanças de contrato ou comportamento precisam de teste e documentação compatíveis.

## 3. Núcleo funcional existente

O sistema possui, entre outros, os seguintes domínios funcionais:

- escolas e mantenedoras;
- turmas e séries;
- estudantes e matrículas;
- professores/staff e alocações;
- currículo e componentes;
- frequência e diário de classe;
- notas, avaliações e boletins;
- documentos escolares oficiais;
- transferência institucional;
- AEE/Diário AEE;
- Busca Ativa/Bolsa Família;
- painéis e relatórios;
- PWA/offline;
- capacidades de RH/Folha em evolução.

A enumeração acima é orientativa. O código e os contratos vigentes são a fonte definitiva de implementação.

## 4. Governança de desenvolvimento

Fluxo desejado para mudanças:

1. compreender arquitetura e impacto antes de alterar código;
2. trabalhar em branch dedicada;
3. manter escopo incremental e compatível;
4. adicionar/atualizar testes e documentação;
5. abrir PR;
6. executar CI/gates relevantes;
7. revisar;
8. obter autorização humana explícita antes de integrar em `main`;
9. realizar deploy controlado e validar produção quando aplicável.

## 5. AEE

O AEE é considerado **módulo protegido** no processo de desenvolvimento.

Regra de governança: não realizar alteração funcional no AEE sem autorização explícita do responsável pelo projeto.

O repositório já possui implementação e documentação/auditorias próprias do AEE. Conversas antigas de troubleshooting do módulo não precisam ser preservadas quando o estado relevante estiver representado em código, testes, PRs e documentação.

## 6. Diário por Vínculo — DVD

O SIGESC possui infraestrutura específica de cutover, auditoria, proveniência legada e guards de regressão do Diário por Vínculo.

Estado de continuidade a preservar:

- tratar DVD como migração/cutover controlado, não como simples troca de tela;
- preservar compatibilidade necessária com conteúdo/histórico legado;
- manter guards e auditorias de cutover no CI;
- evitar remoção de bridges ou fallback de legado sem evidência de que não são mais necessários;
- a bridge de histórico de conteúdo legado foi validada em produção em 19/08/2026, conforme registro operacional do projeto.

O detalhe técnico deve ser obtido dos artefatos `memory/audit/DVD_*`, serviços/scripts de cutover e workflows correspondentes no próprio repositório.

## 7. MIG / MEC / CMDE

A integração MEC/CMDE possui material arquitetural, simuladores, validadores e documentação de sprint no repositório.

### Arquitetura-alvo consolidada

- pacote modular `backend/mig/`;
- infraestrutura reutilizável em `mig/core/`;
- contrato de providers em `mig/providers/`;
- implementação CMDE isolada em `mig/cmde/`;
- router MEC fino, sem regra de negócio e sem HTTP direto;
- saída externa centralizada em cliente CMDE;
- auditoria e correlation IDs;
- retry/backoff controlado;
- configuração e dashboard técnico separados.

### Postura operacional

- scheduler de frequência permanece OFF por padrão em produção;
- ativação deve ocorrer apenas mediante flag/tenant/janela operacional e mecanismos de lock aplicáveis;
- enquanto contrato oficial, credenciais e homologação não forem suficientes, preservar simulador/dry-run e bloquear envio real;
- mapeamentos SIGESC -> CMDE são fail-closed: não adivinhar códigos, estados ou identidade;
- preview administrativo deve permanecer tenant-scoped e estritamente sem efeitos colaterais quando definido como dry-run;
- a fonte de verdade de frequência continua sendo o domínio de attendance do SIGESC.

### Pendências estratégicas

Antes de promover integração oficial para produção, confirmar formalmente:

- contrato oficial completo de payloads e rotas;
- ciclo de vida/autorização do token;
- separação de homologação e produção;
- provider oficial;
- credenciais válidas e gestão segura dos secrets;
- critérios de readiness e promoção;
- evidências de homologação.

## 8. Documentação e conhecimento

- SIGESC Knowledge Framework: `gutenberggt/sigesc-knowledge`.
- Publicação documental: `https://docs.sigesc.aprenderdigital.top/`.
- O SKF preserva fontes, dossiês, conhecimento consolidado, rastreabilidade e evidências.
- O SIGESC Docs é camada de publicação, não substituto do SKF nem do código.
- Em 2026-08-27, o repositório GitHub principal do SIGESC Docs não apareceu entre os repositórios acessíveis auditados; `sigesc-cursos-docs` pertence a outro projeto.

## 9. Backup operacional conhecido

Baseline operacional informado para MongoDB:

- backup local diário por volta de **02:15**;
- geração/verificação de checksum **SHA-256**;
- retenção planejada/operacional de **14 diários, 8 semanais e 12 mensais**.

### Lacuna de governança identificada em 2026-08-27

A busca no repositório principal não localizou documentação evidente contendo conjuntamente essa política de backup e retenção. Portanto:

- este baseline preserva a informação para evitar perda durante a limpeza das conversas;
- a configuração efetiva do servidor deve continuar sendo a autoridade operacional;
- deve ser criado ou validado um runbook versionado de backup/restore, sem credenciais, tokens, chaves ou dados pessoais, em etapa própria.

## 10. Segredos e dados pessoais

Nunca promover para GitHub:

- senhas;
- tokens;
- API keys reais;
- chaves privadas;
- `.env` de produção;
- dumps de banco contendo dados pessoais;
- arquivos de estudantes/professores não anonimizados;
- credenciais SSH.

Logs e evidências persistidos devem ser sanitizados.

## 11. O que pode desaparecer junto com as conversas

Após consolidação, são dispensáveis:

- saídas completas de PowerShell/bash;
- IDs de container;
- sequências de tentativas de troubleshooting;
- erros já resolvidos;
- screenshots intermediários;
- comandos usados uma única vez;
- UUIDs de entidades usados somente para diagnosticar casos;
- contagens momentâneas;
- PRs já encerrados como informação memorizada — o próprio GitHub preserva o histórico.

## 12. Critério de atualização deste baseline

Criar novo baseline ou atualizar documento equivalente quando houver mudança material em pelo menos um dos itens:

- arquitetura principal;
- plataforma de deploy;
- estratégia multi-tenant;
- fonte canônica de um domínio crítico;
- estado do MIG/CMDE;
- estratégia DVD/cutover;
- proteção do AEE;
- política de backup/restore;
- organização dos repositórios.

Não atualizar o baseline para cada bug ou PR rotineiro. Esses eventos pertencem ao histórico normal do GitHub.
