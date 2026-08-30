# MongoDB Backup Hardening — F0 Architecture & GAP Analysis

Data: 2026-08-30
Issue: #182 — Hardening: backup MongoDB off-host, alertas e RPO/RTO

## 1. Decisão de prioridade

A issue #182 é a próxima prioridade operacional real do SIGESC após o encerramento da P0-F7.9D7.

Motivo: o backup local foi homologado e restaurável, porém a perda total do host/volume ainda pode eliminar simultaneamente banco e cópias locais. Isso é risco de continuidade do serviço e de recuperação de desastre, não apenas conveniência operacional.

Esta F0 é exclusivamente arquitetura, inventário e decomposição segura. Não altera servidor, banco, systemd, Coolify, DNS, storage remoto ou produção.

## 2. Baseline já homologado

O runbook `docs/operations/MONGODB_BACKUP_RESTORE_RUNBOOK.md` registra como baseline:

- backup diário às 02:15 `America/Belem`;
- retenção local máxima 14 daily / 8 weekly / 12 monthly;
- arquivos `*.archive.gz`;
- `gzip -t` + SHA-256;
- sidecar de metadata/proveniência;
- execução por `systemd` service/timer;
- identificação fail-closed da stack de produção;
- restore drill isolado com `--network none`, sem portas publicadas e mount read-only;
- restore real condicionado a autorização humana explícita.

A evidência histórica no repositório `sigesc-knowledge` confirma que a homologação de 2026-08-28 passou com produção não tocada pelo drill.

## 3. GAPs confirmados

### GAP-01 — cópia off-host/off-site inexistente

Estado: bloqueante para resiliência contra perda total do host.

Risco:

- falha catastrófica do servidor, volume ou conta operacional pode remover banco e backups locais ao mesmo tempo;
- restaurabilidade local não equivale a disaster recovery.

Objetivo futuro:

- manter uma cópia criptografada fora do host de produção;
- credencial do produtor com privilégio mínimo;
- integridade verificável;
- recuperação testável sem depender do host original.

### GAP-02 — implementação viva não está versionada

A busca no repositório por `sigesc-mongo-backup` encontra apenas o runbook; o script real e as units `systemd` homologadas não estão sob controle de versão.

Risco:

- reconstrução depende do estado atual do servidor;
- drift entre documentação e runtime pode passar despercebido;
- mudança futura pode degradar o backup sem revisão por PR.

Primeira ação de implementação recomendada: capturar e sanitizar o script/units atuais, comparar com o runbook e somente então versionar uma baseline reproduzível.

Nenhum segredo, path sensível dependente de host ou dado operacional bruto pode ser incluído no Git.

### GAP-03 — ausência de alertas automáticos

Precisam existir dois sinais independentes:

1. falha explícita do `sigesc-mongo-backup.service`;
2. ausência de backup recente / timer inativo, inclusive quando não há falha explícita de service.

A segunda condição é essencial porque um timer desativado pode produzir silêncio em vez de erro.

### GAP-04 — restore drill sem periodicidade institucional

O drill manual provou restaurabilidade em 2026-08-28, mas ainda não há frequência formal nem histórico contínuo de exercícios.

Automação completa do drill não deve ser a primeira mudança. Primeiro devem existir:

- IaC do backup;
- cópia remota estável;
- alertas;
- procedimento remoto de recuperação manual homologado.

### GAP-05 — RPO/RTO não formalizados

O backup diário cria uma janela técnica nominal próxima de 24h, mas isso não é RPO institucional por si só.

RTO também não pode ser inferido do tempo de `mongorestore`; deve incluir detecção, decisão, provisionamento, recuperação, validação, cutover e smoke tests.

## 4. Arquitetura-alvo

Fluxo recomendado:

```text
Mongo produção
    |
    | mongodump --archive --gzip
    v
Backup local homologado
    |
    | validação gzip + sha256 + metadata
    v
Local backup PASS
    |
    | cópia criptografada off-host
    v
Repositório remoto
    |
    | check/inventory/freshness
    v
Remote backup VERIFIED
```

Princípio: o upload remoto nunca transforma um backup local inválido em backup aceito. Somente artefatos locais que passaram por integridade e proveniência podem sair do host.

## 5. Tecnologia off-host — decisão de arquitetura

A F0 não fixa fornecedor. A implementação deve usar uma interface S3-compatible ou equivalente para evitar acoplamento desnecessário.

Candidato técnico preferencial para a primeira prova: `restic` sobre object storage S3-compatible, porque fornece:

- criptografia client-side;
- verificação de integridade;
- snapshots e retenção;
- restore para diretório isolado;
- suporte a backends S3-compatible;
- separação entre o formato local atual e o repositório remoto.

Alternativa aceitável: upload de arquivos já criptografados via `rclone`/cliente S3, desde que haja desenho explícito de criptografia, retenção, verificação e recuperação.

Gate: a escolha final só deve ocorrer após definir o storage remoto disponível, política de credenciais e custo/retention desejados.

## 6. Segurança do repositório remoto

Invariantes obrigatórios:

1. dumps nunca podem ser enviados em claro para storage remoto;
2. segredo/chave de criptografia nunca entra no Git;
3. credencial de upload deve ter privilégio mínimo e ser exclusiva para backup;
4. processo normal de backup não deve possuir privilégio administrativo amplo sobre o storage;
5. restore exige credencial separada ou elevação operacional controlada quando viável;
6. logs não devem conter conteúdo de documentos Mongo, URI, token ou segredo;
7. falha no off-host não apaga o backup local válido;
8. falha local invalida o ciclo inteiro e impede upload daquele artefato;
9. exclusão/retention remota deve ser controlada e auditável;
10. recuperação remota deve funcionar em host limpo, sem depender do volume de produção perdido.

## 7. Estratégia de alertas

### 7.1 Falha do serviço

Adicionar um mecanismo fail-visible ligado ao `systemd`, preferencialmente desacoplado do script principal.

Sinal mínimo:

- unit falhou;
- timestamp;
- exit status;
- host lógico/ambiente;
- sem segredo e sem conteúdo de dump.

### 7.2 Watchdog de freshness

Um checker separado deve validar periodicamente:

- timer loaded/active/waiting;
- último backup local dentro do limite;
- integridade dos sidecars essenciais;
- último snapshot/cópia remota dentro do limite;
- última verificação remota bem-sucedida.

Falhar se o backup ficar silenciosamente velho, mesmo com service sem falha recente.

## 8. RPO/RTO — proposta inicial para decisão institucional

Como baseline de engenharia, não como SLA contratual:

- **RPO alvo inicial: <= 24h** enquanto houver um backup local diário;
- objetivo evolutivo: avaliar **RPO <= 12h** apenas se custo/carga do `mongodump` e criticidade justificarem;
- **RTO alvo inicial de exercício: <= 4h** para recuperação completa em infraestrutura disponível.

Esses valores devem permanecer classificados como `PROPOSED` até decisão institucional e medição prática.

## 9. Decomposição em fases

### F1 — IaC baseline do backup local

Objetivo: tornar reproduzível o mecanismo já homologado antes de mudá-lo.

Entregáveis:

- script de backup sanitizado e parametrizado;
- `sigesc-mongo-backup.service` versionado;
- `sigesc-mongo-backup.timer` versionado;
- arquivo de exemplo de configuração sem segredos;
- guard/lint estático para impedir credenciais e writers inesperados;
- documentação de instalação/update/rollback.

Produção: nenhuma mudança durante o PR. Aplicação posterior somente com autorização operacional específica.

### F2 — observabilidade e stale-backup watchdog

Entregáveis:

- checker read-only de saúde/freshness;
- unit/timer de watchdog;
- mecanismo de notificação configurável;
- testes de cenários: timer parado, service failed, arquivo ausente, SHA ausente/inválido, backup velho.

### F3 — off-host encrypted copy

Entregáveis:

- adapter/configuração de storage remoto;
- criptografia client-side;
- upload somente após local PASS;
- retenção remota definida;
- inventory/check remoto;
- nenhuma credencial no repositório.

### F4 — remote recovery drill

Objetivo: provar recuperação partindo da cópia externa.

Procedimento:

1. baixar/restaurar snapshot remoto em diretório isolado;
2. validar cadeia criptográfica/integridade;
3. validar GZIP + SHA + metadata do artefato recuperado;
4. subir Mongo temporário `--network none`;
5. executar `mongorestore --stopOnError`;
6. validar apenas estatísticas estruturais, sem imprimir documentos;
7. destruir ambiente temporário;
8. registrar tempos e evidências sanitizadas.

### F5 — RPO/RTO formal + DR runbook

Entregáveis:

- decisão institucional de RPO/RTO;
- exercício cronometrado ponta a ponta;
- runbook de disaster recovery;
- critérios de declaração de incidente, aprovação de ponto de recuperação e cutover.

### F6 — periodic drill automation

Somente depois de F1–F5 homologadas.

Automação deve permanecer isolada e nunca possuir caminho automático para restore/cutover em produção.

## 10. Ordem obrigatória

```text
F0 arquitetura/GAP
 -> F1 versionar baseline local
 -> F2 alertas/watchdog
 -> F3 off-host criptografado
 -> F4 recuperação remota real em ambiente isolado
 -> F5 RPO/RTO + DR runbook
 -> F6 automação periódica do drill
```

Não iniciar F3 capturando automaticamente o conteúdo atual do host antes de F1, porque isso perpetuaria implementação não versionada e dificultaria auditoria de drift.

## 11. Critérios para fechar a issue #182

Todos devem estar satisfeitos:

- [ ] script e units locais versionados/reproduzíveis;
- [ ] backup local continua homologado após IaC;
- [ ] alerta de falha de service testado;
- [ ] watchdog de stale backup testado;
- [ ] cópia off-host criptografada ativa;
- [ ] integridade remota verificável;
- [ ] recuperação a partir do remoto homologada em ambiente isolado;
- [ ] periodicidade de drill definida;
- [ ] RPO institucional definido;
- [ ] RTO institucional definido e medido;
- [ ] runbook atualizado;
- [ ] evidência sanitizada persistida;
- [ ] zero segredo/dump/dado pessoal versionado.

## 12. Veredito F0

`READY_FOR_F1_BASELINE_CAPTURE`

A próxima mudança deve ser deliberadamente pequena: **versionar a implementação local homologada antes de introduzir storage remoto ou novos efeitos operacionais**.
