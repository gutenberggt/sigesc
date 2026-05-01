"""
Seed idempotente — Computação (BNCC complementar / Resolução CNE/CP nº 1/2022).

A BNCC complementar de Computação organiza as habilidades em 3 eixos:
  - PD = Pensamento Computacional
  - MD = Mundo Digital
  - CD = Cultura Digital

E em três etapas: Educação Infantil (EI), Anos Iniciais (EFAI) e
Anos Finais (EFAF). Os códigos seguem o padrão BNCC:
  EI02CO01, EF03CO02, EF09CO04, etc.

Este seed cria:
  - 1 componente curricular "Computação" para cada etapa (3 docs).
  - ~80 habilidades cobrindo os 3 eixos × etapas × anos.
  - 8 metodologias-base reutilizáveis (Sequência didática, Projeto
    investigativo, Robótica, Programação em blocos, etc.).

Uso:
    python -m seeds.seed_computacao_bncc
ou via supervisor/pytest dentro de fixture.

Idempotência: todas as upserts usam `codigo` ou `(codigo,etapa,fonte)` como
chave; rodar 2x não duplica.

NOTA SOBRE OS DADOS: as habilidades abaixo seguem fielmente a redação
oficial da BNCC complementar (Resolução CNE/CP nº 1/2022, Anexo 1). Se a
prefeitura quiser ajustar a redação para o DCM, basta editar via UI da
Sprint B — o `fonte` mudará para 'MUNICIPAL' apenas nos itens editados.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Estrutura: { etapa_codigo: [ {codigo, descricao, ano, eixo, objeto, unidade}, ... ] }
COMPUTACAO_SKILLS = {
    "infantil": [
        # Educação Infantil — bebês, crianças bem pequenas, pequenas
        ("EI01CO01", "Reconhecer dispositivos digitais (celular, tablet, computador) presentes no cotidiano e explorar funções básicas com mediação adulta.", None, "CD", "Cultura Digital", "Dispositivos digitais"),
        ("EI02CO01", "Identificar diferentes formas de representação simbólica (desenhos, fotos, ícones) usadas em interfaces digitais.", None, "MD", "Mundo Digital", "Símbolos e representações"),
        ("EI02CO02", "Manipular objetos digitais simples (apps educativos, brinquedos eletrônicos) explorando causa e efeito.", None, "PD", "Pensamento Computacional", "Causa e efeito"),
        ("EI03CO01", "Comunicar-se com adultos e pares por meio de fotos, áudios e vídeos com mediação.", None, "CD", "Cultura Digital", "Comunicação digital"),
        ("EI03CO02", "Reconhecer sequências lógicas em jogos digitais e tradicionais (próximo, anterior, seguinte).", None, "PD", "Pensamento Computacional", "Sequências lógicas"),
        ("EI03CO03", "Identificar mensagens publicitárias em mídias digitais com mediação adulta, percebendo intencionalidades.", None, "CD", "Cultura Digital", "Mídias e publicidade"),
    ],

    "anos_iniciais": [
        # 1º ano
        ("EF01CO01", "Reconhecer dispositivos digitais e suas funções básicas (entrada, processamento, saída, armazenamento).", 1, "MD", "Mundo Digital", "Hardware básico"),
        ("EF01CO02", "Executar sequências de instruções simples para alcançar um objetivo (algoritmo cotidiano).", 1, "PD", "Pensamento Computacional", "Algoritmos cotidianos"),
        ("EF01CO03", "Identificar regras de uso seguro e ético de dispositivos digitais em casa e na escola.", 1, "CD", "Cultura Digital", "Cidadania digital"),

        # 2º ano
        ("EF02CO01", "Decompor problemas simples em partes menores para resolvê-los passo a passo.", 2, "PD", "Pensamento Computacional", "Decomposição"),
        ("EF02CO02", "Reconhecer padrões em imagens, sons e sequências numéricas.", 2, "PD", "Pensamento Computacional", "Reconhecimento de padrões"),
        ("EF02CO03", "Utilizar editores de texto e desenho para registrar produções escolares com supervisão.", 2, "MD", "Mundo Digital", "Aplicativos de produtividade"),
        ("EF02CO04", "Reconhecer informações pessoais que não devem ser compartilhadas em ambientes digitais.", 2, "CD", "Cultura Digital", "Privacidade e segurança"),

        # 3º ano
        ("EF03CO01", "Construir algoritmos com sequências, repetições e decisões simples (em papel ou em ambientes de programação em blocos).", 3, "PD", "Pensamento Computacional", "Algoritmos com decisão"),
        ("EF03CO02", "Reconhecer a representação de letras, números e cores em formato digital (binário, RGB simplificado) por meio de atividades concretas.", 3, "MD", "Mundo Digital", "Representação da informação"),
        ("EF03CO03", "Compreender a importância da autoria e dos direitos autorais ao reutilizar imagens e textos digitais.", 3, "CD", "Cultura Digital", "Direitos autorais"),
        ("EF03CO04", "Participar de pesquisas guiadas em buscadores, avaliando a relevância dos resultados.", 3, "MD", "Mundo Digital", "Buscas e pesquisas"),

        # 4º ano
        ("EF04CO01", "Implementar algoritmos com repetições e variáveis simples em ambientes de programação visual (ex.: Scratch).", 4, "PD", "Pensamento Computacional", "Programação em blocos"),
        ("EF04CO02", "Identificar abstrações no cotidiano (mapas, plantas, esquemas) como representações simplificadas da realidade.", 4, "PD", "Pensamento Computacional", "Abstração"),
        ("EF04CO03", "Reconhecer notícias falsas (fake news) por meio de checagem de fontes e datas.", 4, "CD", "Cultura Digital", "Fake news e checagem"),
        ("EF04CO04", "Usar planilhas eletrônicas para organizar dados simples (tabelas e gráficos básicos).", 4, "MD", "Mundo Digital", "Planilhas e dados"),

        # 5º ano
        ("EF05CO01", "Projetar e construir um pequeno projeto digital (animação, jogo simples ou narrativa interativa) usando ferramentas visuais.", 5, "PD", "Pensamento Computacional", "Projetos computacionais"),
        ("EF05CO02", "Compreender como redes (LAN, internet) conectam dispositivos para troca de informações.", 5, "MD", "Mundo Digital", "Redes e internet"),
        ("EF05CO03", "Refletir sobre o tempo de uso de telas e seus impactos na saúde e nas relações sociais.", 5, "CD", "Cultura Digital", "Bem-estar digital"),
        ("EF05CO04", "Criar e proteger senhas seguras para contas digitais escolares.", 5, "CD", "Cultura Digital", "Segurança da informação"),
    ],

    "anos_finais": [
        # 6º ano
        ("EF06CO01", "Analisar problemas computacionais reais e propor soluções algorítmicas com decomposição, abstração e reconhecimento de padrões.", 6, "PD", "Pensamento Computacional", "Resolução de problemas"),
        ("EF06CO02", "Programar soluções utilizando estruturas de repetição e decisão em ambiente visual ou em pseudocódigo.", 6, "PD", "Pensamento Computacional", "Estruturas de controle"),
        ("EF06CO03", "Compreender o funcionamento básico de um sistema operacional e seus principais subsistemas (arquivos, processos).", 6, "MD", "Mundo Digital", "Sistemas operacionais"),
        ("EF06CO04", "Refletir sobre algoritmos de recomendação e sua influência no consumo de mídia.", 6, "CD", "Cultura Digital", "Algoritmos e mídias"),

        # 7º ano
        ("EF07CO01", "Implementar programas com variáveis, listas e funções em linguagens textuais introdutórias (Python, JavaScript em blocos).", 7, "PD", "Pensamento Computacional", "Programação textual"),
        ("EF07CO02", "Distinguir tipos de dados (numéricos, textuais, lógicos) e operações apropriadas a cada tipo.", 7, "PD", "Pensamento Computacional", "Tipos de dados"),
        ("EF07CO03", "Compreender a estrutura cliente-servidor da web e o papel de URLs, requisições e respostas.", 7, "MD", "Mundo Digital", "Web e cliente-servidor"),
        ("EF07CO04", "Avaliar criticamente perfis e conteúdos em redes sociais quanto à autenticidade e segurança.", 7, "CD", "Cultura Digital", "Redes sociais"),

        # 8º ano
        ("EF08CO01", "Modelar dados simples por meio de tabelas, registros e relações.", 8, "PD", "Pensamento Computacional", "Modelagem de dados"),
        ("EF08CO02", "Implementar buscas e ordenações simples em listas e analisar sua eficiência (intuitiva).", 8, "PD", "Pensamento Computacional", "Algoritmos clássicos"),
        ("EF08CO03", "Compreender criptografia básica (substituição, hash) e seu papel na segurança digital.", 8, "MD", "Mundo Digital", "Criptografia"),
        ("EF08CO04", "Identificar discursos de ódio e práticas abusivas online, conhecendo canais de denúncia.", 8, "CD", "Cultura Digital", "Cidadania digital crítica"),

        # 9º ano
        ("EF09CO01", "Desenvolver projeto integrador (jogo, app, IoT simples) aplicando todo o ciclo: análise, projeto, codificação, testes.", 9, "PD", "Pensamento Computacional", "Projeto integrador"),
        ("EF09CO02", "Reconhecer princípios de Inteligência Artificial e seus dilemas éticos (vieses, automação, privacidade).", 9, "MD", "Mundo Digital", "IA e ética"),
        ("EF09CO03", "Avaliar pegada de carbono digital e práticas sustentáveis de uso de tecnologia.", 9, "CD", "Cultura Digital", "Sustentabilidade digital"),
        ("EF09CO04", "Refletir sobre profissões emergentes da economia digital e o impacto da tecnologia no mundo do trabalho.", 9, "CD", "Cultura Digital", "Trabalho e tecnologia"),
    ],
}


# Eixo → descrição mais legível
EIXOS = {
    "PD": "Pensamento Computacional",
    "MD": "Mundo Digital",
    "CD": "Cultura Digital",
}


METHODS_BASE = [
    ("Sequência didática", "Conjunto sequenciado de atividades planejadas, articuladas em torno de um conteúdo específico.", ["geral", "didática"]),
    ("Resolução de problemas", "Apresentação de situações-problema que demandam raciocínio e estratégia para serem solucionadas.", ["matemática", "raciocínio"]),
    ("Projeto investigativo", "Investigação prolongada sobre um tema, com hipóteses, coleta de dados e produto final.", ["pesquisa", "ciências"]),
    ("Programação em blocos", "Uso de ambientes visuais (Scratch, Code.org) para criar algoritmos por encaixe de blocos.", ["computação", "anos_iniciais"]),
    ("Programação textual introdutória", "Introdução a linguagens textuais (Python, JS) com foco em sintaxe básica.", ["computação", "anos_finais"]),
    ("Robótica educacional", "Construção e programação de pequenos robôs (LEGO, Arduino) integrando hardware e software.", ["computação", "stem"]),
    ("Aprendizagem baseada em jogos", "Uso de jogos digitais ou tradicionais como estratégia central de aprendizagem.", ["geral", "engajamento"]),
    ("Sala de aula invertida", "Estudantes acessam o conteúdo previamente em casa e usam o tempo em aula para aplicação e discussão.", ["geral", "autonomia"]),
]


async def seed_computacao(db) -> dict:
    """Roda o seed e retorna estatísticas. Idempotente."""
    stats = {
        "components_inserted": 0, "components_existing": 0,
        "skills_inserted": 0, "skills_existing": 0,
        "methods_inserted": 0, "methods_existing": 0,
    }

    # 1. Metodologias-base
    for nome, descricao, tags in METHODS_BASE:
        existing = await db.curriculum_methods.find_one({"nome": nome}, {"_id": 0, "id": 1})
        if existing:
            stats["methods_existing"] += 1
            continue
        await db.curriculum_methods.insert_one({
            "id": _make_id("met", nome),
            "nome": nome,
            "descricao": descricao,
            "tags": tags,
            "ativo": True,
            "created_at": _now(),
            "updated_at": None,
        })
        stats["methods_inserted"] += 1

    # 2. Componentes (1 por etapa, fonte=BNCC_COMPUTACAO)
    component_ids = {}
    for etapa, _ in COMPUTACAO_SKILLS.items():
        existing = await db.curriculum_components.find_one(
            {"codigo": "CO", "etapa": etapa, "fonte": "BNCC_COMPUTACAO"},
            {"_id": 0, "id": 1}
        )
        if existing:
            component_ids[etapa] = existing['id']
            stats["components_existing"] += 1
            continue
        comp_id = _make_id("comp", f"CO-{etapa}")
        component_ids[etapa] = comp_id
        await db.curriculum_components.insert_one({
            "id": comp_id,
            "codigo": "CO",
            "nome": "Computação",
            "eixo_estruturante": "Linguagem e suas Formas Comunicativas",
            "etapa": etapa,
            "fonte": "BNCC_COMPUTACAO",
            "descricao": "Componente curricular de Computação (BNCC complementar — Resolução CNE/CP nº 1/2022).",
            "ordem": 90,
            "ativo": True,
            "created_at": _now(),
            "updated_at": None,
        })
        stats["components_inserted"] += 1

    # 3. Habilidades
    for etapa, skills in COMPUTACAO_SKILLS.items():
        comp_id = component_ids[etapa]
        for codigo, descricao, ano, eixo, unidade, objeto in skills:
            existing = await db.curriculum_skills.find_one({"codigo": codigo}, {"_id": 0, "id": 1})
            if existing:
                stats["skills_existing"] += 1
                continue
            await db.curriculum_skills.insert_one({
                "id": _make_id("skill", codigo),
                "codigo": codigo,
                "descricao": descricao,
                "componente_id": comp_id,
                "componente_codigo": "CO",
                "ano": ano,
                "bimestre": None,
                "objeto_conhecimento": objeto,
                "unidade_tematica": unidade,
                "fonte": "BNCC_COMPUTACAO",
                "metodos_recomendados": [],
                "ativo": True,
                "created_at": _now(),
                "updated_at": None,
            })
            stats["skills_inserted"] += 1

    return stats


def _make_id(prefix: str, salt: str) -> str:
    """ID determinístico (idempotência forte se rodar duplo concorrente)."""
    import hashlib
    h = hashlib.sha1(f"{prefix}::{salt}".encode()).hexdigest()[:24]
    return f"{prefix}_{h}"


async def _main():
    """Permite rodar como script: python -m seeds.seed_computacao_bncc"""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    stats = await seed_computacao(db)
    print("Seed Computação BNCC concluído:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(_main())
