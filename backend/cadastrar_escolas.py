import asyncio
import httpx
import json

# URL da API
API_URL = "https://edumanager-95.preview.emergentagent.com/api"

# Escolas extraídas da imagem
ESCOLAS = [
    {
        "name": "E M E F 22 DE ABRIL",
        "inep_code": "15134628",
        "logradouro": "Vila Piacava",
        "bairro": "Vila Piacava",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F BABAÇU VERDE",
        "inep_code": "15134709",
        "logradouro": "Vila Mendonca",
        "bairro": "Vila Mendonca",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F BOM JESUS",
        "inep_code": "15134814",
        "logradouro": "Vila Bom Jesus",
        "bairro": "Vila Bom Jesus",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F CRISTO REDENTOR",
        "inep_code": "15134962",
        "logradouro": "Vila Bom Jesus II",
        "bairro": "Vila Bom Jesus II",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F JOSE PEREIRA BARBOSA",
        "inep_code": "15552420",
        "logradouro": "Av. Orlando Mendonça",
        "numero": "S/N",
        "bairro": "Centro",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F JOSE PINHEIRO DE SOUSA",
        "inep_code": "15568962",
        "logradouro": "Av Independência",
        "numero": "S/N",
        "bairro": "St. Bananal",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F MONSENHOR AUGUSTO DIAS DE BRITO",
        "inep_code": "15549232",
        "logradouro": "Av. Orlando Mendonça",
        "numero": "S/N",
        "bairro": "Centro",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F MONTEIRO LOBATO",
        "inep_code": "15135322",
        "logradouro": "Povoado São Francisco - PA Juassama",
        "bairro": "Povoado São Francisco",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F PAULETTE CAMILLE MARGARET PLANCHON",
        "inep_code": "15135926",
        "logradouro": "Rua Vereador Solly Valiate",
        "numero": "S/N",
        "bairro": "Vila Nova I",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F PEDRO VOLTARELLI",
        "inep_code": "15134687",
        "logradouro": "Vila Ametista",
        "bairro": "Vila Ametista",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F PROFESSORA VALDIRENE ALVES DOS SANTOS",
        "inep_code": "15559386",
        "logradouro": "Vila Tabuleiro",
        "bairro": "Vila Tabuleiro",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "38543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F SAO BRAS",
        "inep_code": "15135608",
        "logradouro": "Vila São Bras",
        "bairro": "Vila São Bras",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E F SAO VICENTE",
        "inep_code": "15149730",
        "logradouro": "Vila São Vicente - Lote 41",
        "bairro": "Vila São Vicente",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E I E F DR ALMIR JOSE DE OLIVEIRA GABRIEL",
        "inep_code": "15573184",
        "logradouro": "Av. 15 de Novembro",
        "numero": "S/N",
        "bairro": "Centro",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E I E F PAROQUIAL CURUPIRA",
        "inep_code": "15531929",
        "logradouro": "Av Independência",
        "numero": "1497",
        "bairro": "Centro",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68543-000",
        "zona_localizacao": "urbana",
        "situacao_funcionamento": "Em atividade"
    },
    {
        "name": "E M E I F SORRISO DO ARAGUAIA",
        "inep_code": "15135748",
        "logradouro": "Distrito Bela Vista",
        "bairro": "Distrito Bela Vista",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "cep": "68544-100",
        "zona_localizacao": "rural",
        "situacao_funcionamento": "Em atividade"
    }
]

async def login():
    """Fazer login e obter token"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_URL}/auth/login",
            json={"email": "admin@sigesc.com", "password": "password"}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            print(f"Erro no login: {response.status_code} - {response.text}")
            return None

async def criar_escola(token, escola):
    """Criar uma escola"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_URL}/schools",
            json=escola,
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.status_code, response.json() if response.status_code < 400 else response.text

async def main():
    print("=" * 60)
    print("CADASTRO DE ESCOLAS - FLORESTA DO ARAGUAIA")
    print("=" * 60)
    
    # Login
    print("\n🔐 Fazendo login...")
    token = await login()
    if not token:
        print("❌ Falha no login. Abortando.")
        return
    print("✅ Login realizado com sucesso!")
    
    # Cadastrar escolas
    print(f"\n📚 Cadastrando {len(ESCOLAS)} escolas...\n")
    
    sucesso = 0
    erro = 0
    
    for i, escola in enumerate(ESCOLAS, 1):
        status_code, result = await criar_escola(token, escola)
        
        if status_code == 201:
            print(f"✅ [{i}/{len(ESCOLAS)}] {escola['name']} - INEP: {escola['inep_code']}")
            sucesso += 1
        else:
            print(f"❌ [{i}/{len(ESCOLAS)}] {escola['name']} - Erro: {result}")
            erro += 1
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DO CADASTRO")
    print("=" * 60)
    print(f"✅ Sucesso: {sucesso}")
    print(f"❌ Erros: {erro}")
    print(f"📊 Total: {len(ESCOLAS)}")

if __name__ == "__main__":
    asyncio.run(main())
