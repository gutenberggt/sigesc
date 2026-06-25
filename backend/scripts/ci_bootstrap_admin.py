#!/usr/bin/env python3
"""
Bootstrap de super_admin para o GATE de regressão em CI.

Idempotente. Cria/atualiza UM usuário super_admin a partir de variáveis de ambiente,
para que o `cycle` (smoke test de regressão) consiga autenticar num MongoDB efêmero de CI.

⚠️ USO EXCLUSIVO DE CI (banco efêmero). Não rode contra banco real:
o usuário é marcado com `ci_bootstrap: true`. Recusa-se a rodar se o banco já tiver
usuários reais e a env CI != 'true' (proteção contra uso acidental em produção).

Env:
  CI_ADMIN_EMAIL     (default: ci-admin@sigesc.local)
  CI_ADMIN_PASSWORD  (obrigatória)
  DB_NAME, MONGO_URL (do .env)
  CI                 (deve ser 'true')
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auth_utils import hash_password  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

email = os.environ.get("CI_ADMIN_EMAIL", "ci-admin@sigesc.local")
password = os.environ.get("CI_ADMIN_PASSWORD")
if not password:
    print("ERRO: CI_ADMIN_PASSWORD não definida."); sys.exit(2)

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# Proteção: só roda em CI OU em banco vazio de usuários.
if os.environ.get("CI") != "true" and db.users.count_documents({}) > 0:
    print("RECUSADO: banco com usuários e CI!='true'. Bootstrap é exclusivo de CI."); sys.exit(3)

now = datetime.now(timezone.utc).isoformat()
db.users.update_one(
    {"email": email},
    {"$set": {
        "email": email, "full_name": "CI Regression Admin", "role": "super_admin",
        "status": "active", "password_hash": hash_password(password),
        "ci_bootstrap": True, "updated_at": now,
    }, "$setOnInsert": {"id": f"ci-admin-{int(datetime.now().timestamp())}", "created_at": now}},
    upsert=True,
)
print(f"OK: super_admin de CI garantido ({email}).")
