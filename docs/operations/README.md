# Operações do SIGESC

Esta área reúne runbooks técnicos necessários à operação segura do SIGESC.

## Runbooks

- [Backup & Restore do MongoDB](MONGODB_BACKUP_RESTORE_RUNBOOK.md)

## Princípios

- mudanças destrutivas ou com impacto em produção exigem autorização humana explícita;
- restaurações devem usar postura **fail-closed**;
- nenhum procedimento deve depender de nome efêmero de container sem validação por labels/roteamento;
- segredos, credenciais e dados pessoais não devem ser registrados em documentação ou evidências;
- evidências de homologação devem ser preservadas no `gutenberggt/sigesc-knowledge/05-evidencias`.
