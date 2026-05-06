"""Pacote `startup` — extração de blocos do `server.py` para reduzir tamanho do
entrypoint sem alterar comportamento.

Cada submódulo expõe uma única função `async def run(db, ...)` que é chamada
em ordem pelo lifespan de startup.
"""
