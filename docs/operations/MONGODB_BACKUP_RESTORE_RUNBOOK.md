# Runbook — Backup & Restore do MongoDB

**Sistema:** SIGESC  
**Escopo:** banco MongoDB da produção  
**Estado:** operacional/homologado  
**Última homologação técnica:** 2026-08-28  

## 1. Objetivo

Definir o procedimento seguro para verificar, recuperar e testar os backups do MongoDB do SIGESC sem depender de nomes efêmeros de containers, memória de operador ou conversas externas.

Este runbook cobre:

- identificação inequívoca da stack de produção;
- validação do agendamento e da política de retenção;
- verificação de integridade dos arquivos retidos;
- prova de proveniência do backup;
- restore drill isolado;
- critérios para um restore real em situação de incidente.

## 2. Invariantes de segurança

1. **Nunca assumir produção pelo nome do container.** Identificar a stack pelo roteamento público e pelas labels Docker/Compose.
2. O domínio de produção é `sigesc.aprenderdigital.top`; ambientes de homologação devem possuir domínio/router distinto.
3. O script de backup deve selecionar **exatamente um** serviço `mongo` dentro do projeto Compose de produção. Zero ou mais de um resultado deve abortar o backup.
4. Todo arquivo restaurado deve passar por validação GZIP, SHA-256 e metadata antes do `mongorestore`.
5. O campo de proveniência do metadata deve apontar para o MongoDB correspondente à stack de produção validada.
6. Restore drill deve ocorrer em container temporário com `--network none`, sem portas publicadas e com backup montado read-only.
7. Restore real em produção exige autorização humana explícita, janela de manutenção e plano de rollback.
8. Não registrar em Git logs contendo segredos, tokens, strings de conexão, CPF, e-mail ou qualquer dado pessoal operacional.
9. Ambiguidade em roteamento, origem, checksum, metadata ou identidade do banco deve resultar em **aborto fail-closed**.

## 3. Baseline operacional homologado

Na homologação de 2026-08-28 foi confirmado no servidor de produção:

| Controle | Estado esperado |
|---|---|
| Agendamento | diário, 02:15 `America/Belem` |
| Daily | retenção máxima de 14 arquivos |
| Weekly | promoção aos domingos; retenção máxima de 8 |
| Monthly | promoção no dia 01; retenção máxima de 12 |
| Formato | `*.archive.gz` |
| Integridade | `gzip -t` + SHA-256 |
| Proveniência | arquivo `*.metadata.txt` |
| Execução | `systemd` timer/service |
| Política de promoção | hard link quando aplicável, evitando duplicação física desnecessária |

A implementação viva pode evoluir. Antes de qualquer restore, verificar o estado real do servidor; este documento descreve o contrato operacional, não substitui a inspeção do runtime.

## 4. Identificar a stack de produção

### 4.1 Roteamento

Inspecionar os containers frontend candidatos e suas labels Traefik. Deve existir um router cuja regra seja exatamente compatível com:

```text
Host(`sigesc.aprenderdigital.top`)
```

Não considerar `homolog.sigesc.aprenderdigital.top` como produção.

Quando houver mais de uma stack SIGESC ativa no host, executar um probe HTTP com token único e consultar os logs dos frontends candidatos. A produção deve receber os hits correspondentes ao domínio público; stacks de homologação devem registrar zero hits desse probe.

### 4.2 Projeto Compose

Depois de identificar o frontend de produção, obter:

```bash
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' <frontend>
```

Usar esse projeto para localizar o MongoDB:

```bash
docker ps \
  --filter "label=com.docker.compose.project=<PROJECT>" \
  --filter "label=com.docker.compose.service=mongo" \
  --format '{{.ID}}|{{.Names}}|{{.Image}}'
```

**Critério:** deve existir exatamente um resultado.

## 5. Verificar agendamento e serviço

```bash
systemctl show sigesc-mongo-backup.service \
  -p LoadState \
  -p ActiveState \
  -p SubState \
  -p Result \
  -p ExecMainStatus \
  -p InactiveExitTimestamp \
  --no-pager

systemctl show sigesc-mongo-backup.timer \
  -p LoadState \
  -p ActiveState \
  -p SubState \
  -p LastTriggerUSec \
  -p NextElapseUSecRealtime \
  -p TimersCalendar \
  --no-pager
```

Esperado:

- timer `loaded`, `active`, `waiting`;
- calendário diário às 02:15 `America/Belem`;
- serviço com último `Result=success` e `ExecMainStatus=0`.

## 6. Verificar política de retenção

A política homologada é:

```text
daily   = 14
weekly  = 8
monthly = 12
```

A implementação deve promover semanalmente aos domingos e mensalmente no primeiro dia do mês, aplicando poda apenas aos itens acima do limite de cada tier.

A contagem atual pode ser inferior ao limite quando a política ainda não acumulou idade suficiente. **Retenção máxima não significa que o diretório deve sempre conter exatamente 14/8/12 arquivos.**

## 7. Verificar integridade dos arquivos retidos

Para cada `*.archive.gz` de `daily`, `weekly` e `monthly`, validar:

1. arquivo presente;
2. `gzip -t` = PASS;
3. sidecar `*.sha256` presente;
4. SHA-256 calculado igual ao esperado;
5. `*.metadata.txt` presente e não vazio.

Exemplo:

```bash
gzip -t "$BACKUP"

EXPECTED="$(awk 'NR==1 {print tolower($1)}' "${BACKUP}.sha256")"
ACTUAL="$(sha256sum "$BACKUP" | awk '{print tolower($1)}')"
test "$EXPECTED" = "$ACTUAL"
test -s "${BACKUP}.metadata.txt"
```

Qualquer falha impede restore.

## 8. Provar proveniência

O metadata deve permitir verificar pelo menos:

- container Mongo de origem;
- imagem Mongo usada na origem;
- timestamp do backup;
- tamanho/checksum quando presentes.

Antes de restaurar, comparar `mongo_container` do metadata com o Mongo obtido a partir do projeto Compose de produção identificado por roteamento.

Divergência = **abortar**.

## 9. Restore drill isolado

### 9.1 Finalidade

Provar periodicamente que um backup íntegro é também restaurável, sem tocar na produção.

### 9.2 Restrições obrigatórias

O container de drill deve:

- usar a mesma família/imagem Mongo da produção;
- usar `--network none`;
- não publicar portas;
- montar o diretório de backups como read-only;
- ser temporário;
- ser removido ao final, inclusive em caso de falha.

Exemplo de criação:

```bash
docker run \
  -d \
  --name "$DRILL" \
  --network none \
  --mount "type=bind,src=$DAILY,dst=/backup,readonly" \
  "$MONGO_IMAGE" \
  --bind_ip 127.0.0.1
```

### 9.3 Restore

Somente após GZIP, SHA e proveniência passarem:

```bash
docker exec "$DRILL" \
  mongorestore \
  --gzip \
  --archive="/backup/$BASE" \
  --stopOnError
```

### 9.4 Validação mínima

Validar o banco restaurado sem imprimir documentos:

```javascript
const d = db.getSiblingDB("sigesc");
const s = d.stats();
print("COLLECTIONS=" + s.collections);
print("OBJECTS=" + s.objects);
print("DATA_SIZE=" + s.dataSize);
```

Critérios mínimos:

- `collections > 0`;
- `objects > 0`;
- `mongorestore` exit code 0;
- network mode `none`;
- nenhuma porta publicada;
- container temporário removido ao final.

## 10. Restore real em incidente

Restore real é uma operação destrutiva de alta criticidade e **não deve reutilizar automaticamente o procedimento do drill contra o Mongo existente**.

Fluxo obrigatório:

1. declarar incidente e interromper novas escritas quando necessário;
2. identificar e registrar a stack de produção pelo procedimento deste runbook;
3. selecionar o ponto de recuperação aprovado;
4. validar GZIP, SHA-256 e metadata;
5. preservar, quando tecnicamente possível e seguro, snapshot/backup forense do estado incidente;
6. restaurar primeiro em banco/volume de substituição ou ambiente isolado;
7. executar smoke tests de estrutura e funcionalidades críticas;
8. planejar o cutover para o banco restaurado;
9. obter autorização humana explícita para a mudança de produção;
10. executar cutover;
11. validar aplicação, autenticação, leituras críticas e escrita controlada;
12. registrar evidências, horário, backup usado, resultado e rollback disponível.

Nunca executar `mongorestore` diretamente no banco de produção em uso sem um plano específico de incidente aprovado.

## 11. RPO e RTO

Não há, neste runbook, declaração de SLA contratual de RPO/RTO.

O agendamento diário às 02:15 implica uma **janela técnica nominal de até aproximadamente 24 horas entre pontos diários**, mas isso não deve ser apresentado como RPO formal sem decisão institucional específica.

RTO deve ser medido em exercícios de recuperação completos; o restore drill comprova restaurabilidade, mas não mede sozinho o tempo total para retorno do serviço.

## 12. Evidências

A homologação deve registrar apenas dados sanitizados, como:

- data/hora;
- resultado de timer/service;
- contagens por tier;
- PASS/FAIL de GZIP/SHA/metadata;
- prova de roteamento produção x homologação;
- prova de proveniência;
- resultado do restore drill;
- isolamento de rede;
- remoção do container temporário.

Logs brutos permanecem em armazenamento operacional protegido quando necessários e não devem ser versionados se contiverem dados sensíveis.

## 13. Critério de homologação

Backup & Restore é considerado homologado somente quando todos forem verdadeiros:

```text
TIMER=PASS
SERVICE=PASS
RETENTION_POLICY=PASS
RETENTION_INVENTORY=PASS
GZIP=PASS
SHA256=PASS
METADATA=PASS
PRODUCTION_ROUTE_IDENTIFICATION=PASS
BACKUP_PROVENANCE=PASS
RESTORE_DRILL=PASS
NETWORK_ISOLATION=PASS
NO_PUBLISHED_PORTS=PASS
PRODUCTION_DATABASE_TOUCHED=NO
CLEANUP=PASS
```

## 14. Riscos residuais e melhorias

A homologação de restaurabilidade não elimina riscos arquiteturais adicionais. Devem ser tratados como backlog separado, quando aplicável:

- cópia off-host/off-site para proteção contra perda total do servidor ou volume;
- alertas automáticos para falha do serviço/timer e ausência de backup recente;
- restore drills periódicos automatizados ou semiautomatizados;
- versionamento do script e das units `systemd` como infraestrutura operacional reproduzível;
- medição e definição institucional de RPO/RTO.

Esses itens são hardening adicional e não invalidam a prova de que o mecanismo atualmente homologado produz backups íntegros e restauráveis.
