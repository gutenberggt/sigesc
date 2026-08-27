# Governança de Conhecimento e Conversas do SIGESC

**Status:** proposta para adoção
**Data:** 2026-08-27
**Escopo:** repositório `gutenberggt/sigesc` e ecossistema documental do SIGESC

## 1. Objetivo

Evitar que decisões técnicas, regras de negócio, histórico arquitetural e conhecimento institucional dependam de conversas de ChatGPT, sessões de terminal, mensagens instantâneas ou outros registros transitórios.

O conhecimento necessário para reconstruir, operar, auditar e evoluir o SIGESC deve existir em fontes persistentes, versionadas e adequadas ao seu tipo.

## 2. Regra fundamental

> Conversas são espaço de trabalho; repositórios e documentação são fontes persistentes de verdade.

Uma conversa pode ser apagada quando tudo que nela possuir valor durável tiver sido consolidado no local apropriado.

## 3. Distribuição canônica do conhecimento

| Tipo de informação | Destino canônico |
|---|---|
| Código-fonte, testes, migrations, CI/CD, contratos técnicos e documentação próxima do código | `gutenberggt/sigesc` |
| Fontes MEC/FNDE/legislação, dossiês, conhecimento consolidado, rastreabilidade e evidências | `gutenberggt/sigesc-knowledge` |
| Documentação pública/institucional, manuais e material de publicação | SIGESC Docs (`https://docs.sigesc.aprenderdigital.top/`) |
| Backlog, bugs ainda abertos, dívida técnica e trabalho futuro | GitHub Issues/Projects do repositório correspondente |
| Releases e mudanças implementadas | Git history, PRs, changelog/release notes e documentação pertinente |
| Dados operacionais de alunos, escolas, professores, matrículas, frequência e demais registros transacionais | Banco de dados/serviços do SIGESC, não documentação estática |
| Segredos, tokens, chaves, senhas e credenciais de produção | mecanismo seguro de secrets/env; nunca versionar |

## 4. O que deve ser preservado

Devem ser registrados de forma persistente quando relevantes:

- decisões arquiteturais e ADRs;
- regras de negócio e invariantes;
- contratos de API e esquemas relevantes;
- políticas de multi-tenancy, RBAC, segurança e auditoria;
- decisões de integração externa, inclusive MIG/MEC/CMDE;
- critérios de rollout, cutover, rollback e homologação;
- decisões de fonte única de verdade (SSoT);
- procedimentos operacionais que sejam recorrentes;
- incidentes cuja causa e correção gerem aprendizado reutilizável;
- riscos conhecidos e dívida técnica ainda existente;
- restrições explícitas de módulos protegidos;
- critérios de Definition of Done e gates de CI relevantes.

## 5. O que não deve ser preservado como memória permanente

Por padrão, são transitórios e podem ser descartados após a consolidação do resultado:

- logs de terminal;
- IDs de containers e processos;
- hashes usados apenas durante troubleshooting;
- comandos pontuais de diagnóstico;
- screenshots de erros já resolvidos;
- tentativas fracassadas sem valor arquitetural;
- hipóteses descartadas;
- nomes/UUIDs de alunos, professores, turmas ou escolas usados apenas em investigação;
- contagens temporárias;
- saídas de testes isolados;
- conversas do tipo `erro -> investigação -> correção -> PR -> deploy -> validado`, desde que o resultado esteja registrado no GitHub/documentação.

## 6. Ciclo de vida de uma conversa técnica

1. **Exploração:** diagnóstico, comandos, hipóteses, consultas e discussão.
2. **Decisão:** identifica-se o que possui valor durável.
3. **Implementação:** código e testes entram em branch/PR.
4. **Consolidação:** decisão, contrato, runbook, changelog, issue ou conhecimento normativo é registrado no repositório adequado.
5. **Validação:** CI, revisão e homologação confirmam o resultado.
6. **Descarte:** a conversa deixa de ser necessária como fonte de verdade.

## 7. Governança GitHub

Para mudanças no SIGESC:

- desenvolvimento preferencialmente em branch dedicada;
- PR por etapa coerente;
- CI obrigatório conforme o escopo;
- revisão antes da integração;
- nenhuma integração em `main` sem autorização humana explícita do responsável pelo projeto;
- documentação deve acompanhar mudanças que alterem arquitetura, comportamento, contrato ou operação.

## 8. Regras específicas já consolidadas

### Multi-tenancy

O SIGESC é uma plataforma SaaS educacional multi-tenant. Toda leitura e escrita de dados deve respeitar o escopo de tenant/mantenedora e as políticas de autorização correspondentes. A postura padrão para ambiguidades de escopo é fail-closed.

### AEE

O módulo AEE é protegido e não deve sofrer alteração funcional sem autorização explícita do responsável pelo projeto.

### MIG/MEC/CMDE

Integrações oficiais devem permanecer separadas entre configuração, serviço, provider e cliente HTTP. Não promover comunicação real com o MEC sem contrato oficial suficiente, credenciais, homologação e autorização. Mapeamentos SIGESC -> CMDE não podem adivinhar códigos ou estados; diante de ambiguidade, falhar de forma fechada e auditável.

### Diário por Vínculo (DVD)

Alterações relacionadas ao DVD devem preservar guards e testes de regressão associados ao cutover e à compatibilidade com histórico legado.

## 9. Relação com o SIGESC Knowledge Framework

O `sigesc-knowledge` é o repositório canônico para conhecimento externo e institucional estruturado: fontes oficiais, dossiês, consolidação, rastreabilidade, evidências e decisões de governança do conhecimento.

O repositório `sigesc` não deve duplicar grandes dossiês normativos. Deve manter apenas o que é necessário para compreender e operar o software e apontar para o SKF quando a fundamentação estiver nele.

## 10. SIGESC Docs

O endereço público `https://docs.sigesc.aprenderdigital.top/` permanece a camada de publicação. Em 2026-08-27, o repositório GitHub principal correspondente ao SIGESC Docs não estava disponível entre os repositórios acessíveis da conta, portanto não deve ser confundido com `sigesc-cursos-docs`.

Quando o SIGESC Docs principal for versionado no GitHub, sua função deverá permanecer separada:

- SKF = fonte canônica de conhecimento estruturado;
- SIGESC = fonte canônica do software;
- SIGESC Docs = camada de publicação e consumo documental.

## 11. Critério para apagar conversas antigas

Uma conversa pode ser removida quando a resposta para as perguntas abaixo for **sim**:

1. Todo código relevante está versionado?
2. Toda decisão durável está documentada?
3. Todo backlog ainda válido virou Issue/Project ou documento de roadmap?
4. Todo conhecimento normativo relevante está no SKF?
5. Todo arquivo necessário existe fora da conversa?
6. Nenhum segredo depende da conversa como local de armazenamento?

Se todas as respostas forem positivas, a conversa é material transitório e sua exclusão não deve comprometer a continuidade do projeto.
