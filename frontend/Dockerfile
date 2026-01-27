# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Cache buster - mude este valor para forçar rebuild
ARG CACHEBUST=20260127_2100
RUN echo "Cache bust: $CACHEBUST"

# Copia arquivos de dependências primeiro (melhor cache)
COPY package.json yarn.lock* ./

# Instala dependências usando yarn (mais estável que npm)
RUN yarn install --frozen-lockfile --network-timeout 600000

# Copia o restante do código
COPY . .

# Define variáveis de ambiente para o build
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Build da aplicação
RUN yarn build

# Production stage
FROM nginx:alpine

# Copia o build para o nginx
COPY --from=build /app/build /usr/share/nginx/html

# Copia configuração customizada do nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expõe a porta 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
