# Guia de Correção do Traefik no Coolify

## Problema Atual

O roteamento da API em produção depende de um arquivo de configuração manual (`/traefik/dynamic/sigesc-backend.yaml`) criado dentro do container do proxy Traefik. Esta solução é frágil porque:

1. Se o Coolify recriar o container do proxy, a configuração é perdida
2. Se o nome do serviço mudar, a API fica inacessível
3. Não é gerenciada automaticamente pelo Coolify

## Causa Raiz

O Traefik do Coolify não detecta automaticamente os containers do backend porque:
- Eles estão em redes diferentes (a rede UUID do projeto vs. a rede `coolify`)
- Os labels Docker não estão sendo aplicados corretamente

## Solução Recomendada

### Opção 1: Configurar o Docker Compose para usar a rede do Coolify

No Coolify, acesse as configurações do serviço Backend e adicione/modifique o `docker-compose.yml`:

```yaml
services:
  backend:
    image: ${IMAGE_NAME}
    networks:
      - default
      - coolify
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.sigesc-backend.rule=Host(`api.sigesc.aprenderdigital.top`)"
      - "traefik.http.routers.sigesc-backend.entrypoints=https"
      - "traefik.http.routers.sigesc-backend.tls=true"
      - "traefik.http.routers.sigesc-backend.tls.certresolver=letsencrypt"
      - "traefik.http.services.sigesc-backend-service.loadbalancer.server.port=8001"
      - "traefik.docker.network=coolify"

networks:
  coolify:
    external: true
```

### Opção 2: Usar Raw Compose Deployment

1. No Coolify, vá em **Applications** → **Backend**
2. Ative o modo **Raw Compose Deployment**
3. Use o seguinte `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - MONGO_URL=${MONGO_URL}
      - DB_NAME=${DB_NAME}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    ports:
      - "8001"
    networks:
      - coolify
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.sigesc-backend.rule=Host(`api.sigesc.aprenderdigital.top`)"
      - "traefik.http.routers.sigesc-backend.entrypoints=https"
      - "traefik.http.routers.sigesc-backend.tls=true"
      - "traefik.http.routers.sigesc-backend.tls.certresolver=letsencrypt"
      - "traefik.http.services.sigesc-backend-service.loadbalancer.server.port=8001"
      - "traefik.docker.network=coolify"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  coolify:
    external: true
```

### Opção 3: Conectar Manualmente à Rede Coolify

Se as opções acima não funcionarem, execute via SSH no servidor:

```bash
# Descobrir o nome do container do backend
docker ps | grep backend

# Conectar o container à rede coolify
docker network connect coolify <nome-do-container-backend>

# Verificar se está conectado
docker inspect <nome-do-container-backend> | grep -A 10 "Networks"

# Reiniciar o Traefik para detectar
docker restart coolify-proxy
```

## Verificação

Após aplicar a correção:

```bash
# Verificar se o Traefik está detectando o serviço
docker exec -it coolify-proxy cat /etc/traefik/traefik.yml

# Verificar os routers ativos
docker exec -it coolify-proxy traefik healthcheck

# Testar a API
curl -I https://api.sigesc.aprenderdigital.top/api/health
```

## Backup da Configuração Manual Atual

Caso precise reverter, a configuração manual atual está em:

```bash
# Dentro do container coolify-proxy
/traefik/dynamic/sigesc-backend.yaml
```

Conteúdo:
```yaml
http:
  routers:
    sigesc-backend:
      rule: "Host(`api.sigesc.aprenderdigital.top`)"
      service: sigesc-backend-service
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
  services:
    sigesc-backend-service:
      loadBalancer:
        servers:
          - url: "http://backend:8001"
```

## Notas Importantes

1. **Rede `coolify`**: É a rede padrão onde o Traefik escuta. Todos os serviços que precisam ser roteados devem estar nessa rede.

2. **Labels Docker**: O Traefik usa labels para descobrir automaticamente os serviços. Os labels mais importantes são:
   - `traefik.enable=true` - Habilita o Traefik para este container
   - `traefik.docker.network=coolify` - Especifica a rede a usar

3. **Após cada deploy**: Se o problema persistir após cada deploy, o docker-compose precisa ser ajustado no Coolify para incluir a rede corretamente.

## Contato para Suporte

Se precisar de ajuda adicional com a configuração do Coolify/Traefik, consulte:
- [Documentação Coolify](https://coolify.io/docs/knowledge-base/proxy/traefik/overview)
- [Documentação Traefik Docker Provider](https://doc.traefik.io/traefik/providers/docker/)
