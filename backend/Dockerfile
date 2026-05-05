FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements primeiro (melhor cache)
COPY requirements.txt .

# Instala dependências Python (inclui emergentintegrations via index extra do Emergent)
RUN pip install --no-cache-dir \
    --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
    -r requirements.txt

# Copia o código
COPY . .

# Expõe a porta
EXPOSE 8001

# Comando para iniciar
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
