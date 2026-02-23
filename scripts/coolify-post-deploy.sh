#!/bin/bash
# Script de pós-deploy para Coolify
# Este script garante que os containers estejam conectados à rede coolify
# e configura o Traefik corretamente.
#
# IMPORTANTE: Com o novo docker-compose.coolify.yml, este script NÃO deve ser mais necessário.
# Os containers agora têm nomes fixos (sigesc-backend e sigesc-frontend) e se conectam
# automaticamente à rede coolify.
#
# Execute apenas se houver problemas de conectividade após o deploy.

set -e

echo "=== SIGESC Post-Deploy Script ==="
echo ""

# Nomes fixos dos containers (definidos no docker-compose.coolify.yml)
BACKEND_CONTAINER="sigesc-backend"
FRONTEND_CONTAINER="sigesc-frontend"
NETWORK="coolify"

# Função para verificar se container existe
container_exists() {
    docker ps -a --format '{{.Names}}' | grep -q "^$1$"
}

# Função para verificar se container está na rede
container_in_network() {
    docker inspect "$1" --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}' 2>/dev/null | grep -q "$2"
}

echo "1. Verificando containers..."

if container_exists "$BACKEND_CONTAINER"; then
    echo "   ✓ Backend container encontrado: $BACKEND_CONTAINER"
else
    echo "   ✗ Backend container NÃO encontrado!"
    echo "   Procurando containers com 'backend' no nome..."
    docker ps --format "{{.Names}}" | grep -i backend || echo "   Nenhum container backend encontrado"
fi

if container_exists "$FRONTEND_CONTAINER"; then
    echo "   ✓ Frontend container encontrado: $FRONTEND_CONTAINER"
else
    echo "   ✗ Frontend container NÃO encontrado!"
    echo "   Procurando containers com 'frontend' no nome..."
    docker ps --format "{{.Names}}" | grep -i frontend || echo "   Nenhum container frontend encontrado"
fi

echo ""
echo "2. Verificando conexão com rede $NETWORK..."

if container_in_network "$BACKEND_CONTAINER" "$NETWORK"; then
    echo "   ✓ Backend já está na rede $NETWORK"
else
    echo "   → Conectando backend à rede $NETWORK..."
    docker network connect "$NETWORK" "$BACKEND_CONTAINER" 2>/dev/null || echo "   (já conectado ou erro)"
fi

if container_in_network "$FRONTEND_CONTAINER" "$NETWORK"; then
    echo "   ✓ Frontend já está na rede $NETWORK"
else
    echo "   → Conectando frontend à rede $NETWORK..."
    docker network connect "$NETWORK" "$FRONTEND_CONTAINER" 2>/dev/null || echo "   (já conectado ou erro)"
fi

echo ""
echo "3. Configurando Traefik..."

# Configuração do Traefik com nomes fixos
docker exec coolify-proxy sh -c "cat > /traefik/dynamic/sigesc.yaml << 'EOF'
http:
  routers:
    sigesc-backend:
      rule: \"Host(\`api.sigesc.aprenderdigital.top\`)\"
      service: sigesc-backend-service
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
    sigesc-frontend:
      rule: \"Host(\`sigesc.aprenderdigital.top\`)\"
      service: sigesc-frontend-service
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
  services:
    sigesc-backend-service:
      loadBalancer:
        servers:
          - url: \"http://sigesc-backend:8001\"
    sigesc-frontend-service:
      loadBalancer:
        servers:
          - url: \"http://sigesc-frontend:80\"
EOF" && echo "   ✓ Traefik configurado com sucesso" || echo "   ✗ Erro ao configurar Traefik"

echo ""
echo "4. Verificação final..."
echo ""
echo "   Backend: http://sigesc-backend:8001"
echo "   Frontend: http://sigesc-frontend:80"
echo ""
echo "   URLs públicas:"
echo "   - https://api.sigesc.aprenderdigital.top"
echo "   - https://sigesc.aprenderdigital.top"
echo ""
echo "=== Deploy finalizado ==="
