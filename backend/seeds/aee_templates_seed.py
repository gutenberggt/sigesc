"""
Seed dos Modelos Institucionais de Plano AEE.

Insere 8 modelos validados (um para cada público-alvo da Resolução CNE/CEB nº 04/2009),
alinhados às orientações pedagógicas da SEMED.

Idempotente: só insere modelos que ainda não existem (chave: nome).
Roda no startup do servidor.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _build_template(nome, publico_alvo, descricao, modalidade, carga, local,
                    barreiras, objetivos, recursos, indicadores,
                    orientacoes_sala_comum, adequacoes, criterios_ajuste):
    """Helper para padronizar a estrutura dos modelos."""
    return {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "descricao": descricao,
        "publico_alvo": publico_alvo,
        "modalidade": modalidade,
        "carga_horaria_semanal": carga,
        "local_atendimento": local,
        "barreiras": [
            {"tipo": b[0], "descricao": b[1], "estrategias": b[2] if len(b) > 2 else []}
            for b in barreiras
        ],
        "objetivos": [
            {"prazo": o[0], "descricao": o[1], "status": "nao_iniciado", "indicadores": []}
            for o in objetivos
        ],
        "recursos_acessibilidade": [
            {"tipo": r[0], "descricao": r[1], "disponivel": True} for r in recursos
        ],
        "indicadores_progresso": indicadores,
        "frequencia_revisao": "bimestral",
        "criterios_ajuste": criterios_ajuste,
        "orientacoes_sala_comum": orientacoes_sala_comum,
        "adequacoes_curriculares": adequacoes,
        "ativo": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "system_seed",
    }


# ============================================================
# Definição dos 8 modelos institucionais (SEMED)
# ============================================================

TEMPLATES_INSTITUCIONAIS = [
    # 1. Deficiência Física
    _build_template(
        nome="Modelo Institucional - Deficiência Física",
        publico_alvo="deficiencia_fisica",
        descricao="Plano-base para alunos com limitações motoras (paralisia cerebral, mielomeningocele, amputações, distrofias). Foco em acessibilidade, autonomia e participação plena nas atividades escolares.",
        modalidade="individual",
        carga="2 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("arquitetonica", "Acesso restrito a espaços escolares (rampas, banheiros, mobiliário inadequado)"),
            ("comunicacional", "Dificuldade de manuseio de materiais escolares convencionais"),
            ("atitudinal", "Superproteção familiar/escolar limitando autonomia"),
        ],
        objetivos=[
            ("curto", "Adaptar postura e mobiliário para participação adequada nas aulas"),
            ("medio", "Desenvolver autonomia em atividades de vida diária no ambiente escolar"),
            ("medio", "Utilizar tecnologia assistiva para registro escrito (digital ou alternativo)"),
            ("longo", "Promover participação plena em todas as atividades pedagógicas e sociais"),
        ],
        recursos=[
            ("mobiliario_adaptado", "Cadeira/mesa com altura regulável e apoios laterais"),
            ("software_acessivel", "Teclado adaptado / mouse-pad ergonômico / acionadores"),
            ("outro", "Engrossador de lápis, prancha inclinada para escrita"),
        ],
        indicadores="Aumento gradual da autonomia em atividades de escrita, alimentação e locomoção; participação em ≥80% das atividades coletivas.",
        orientacoes_sala_comum="Posicionar o aluno em local de fácil acesso. Permitir tempo adicional para atividades motoras. Substituir registros escritos extensos por digitais ou orais quando necessário.",
        adequacoes="Reduzir quantidade de exercícios escritos mantendo objetivo conceitual. Avaliação processual valoriza o conteúdo, não a forma do registro.",
        criterios_ajuste="Revisar plano se houver: piora postural, regressão na autonomia, ou avanço significativo que demande novos desafios.",
    ),

    # 2. Deficiência Intelectual
    _build_template(
        nome="Modelo Institucional - Deficiência Intelectual",
        publico_alvo="deficiencia_intelectual",
        descricao="Plano-base para alunos com limitações no funcionamento intelectual e comportamento adaptativo. Foco em desenvolvimento de habilidades cognitivas, sociais e de autonomia.",
        modalidade="individual",
        carga="4 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Dificuldade de compreensão de instruções complexas e abstratas"),
            ("pedagogica", "Defasagem na aquisição de leitura, escrita e raciocínio lógico-matemático"),
            ("atitudinal", "Baixa autoestima e expectativas reduzidas do entorno"),
        ],
        objetivos=[
            ("curto", "Desenvolver atenção e concentração em atividades de 15 a 20 minutos"),
            ("curto", "Reconhecer e nomear letras, números e quantidades até 20"),
            ("medio", "Adquirir leitura e escrita de palavras simples (sílabas canônicas)"),
            ("medio", "Resolver situações-problema do cotidiano com apoio visual"),
            ("longo", "Desenvolver autonomia funcional para atividades escolares e de vida prática"),
        ],
        recursos=[
            ("rotina_visual", "Quadro de rotina com pictogramas (chegada, atividades, lanche, saída)"),
            ("outro", "Material concreto: ábaco, material dourado, alfabeto móvel"),
            ("outro", "Jogos pedagógicos adaptados (memória, dominó, sequência lógica)"),
        ],
        indicadores="Avanços mensuráveis em consciência fonológica, contagem e resolução de problemas simples; aumento do tempo de atenção sustentada.",
        orientacoes_sala_comum="Usar instruções curtas e concretas. Apoiar com recursos visuais. Repetir e parafrasear conteúdos. Valorizar pequenos avanços.",
        adequacoes="Adequar conteúdo ao nível de desenvolvimento do aluno (não somente reduzir quantidade). Avaliação diferenciada com prova adaptada e observação processual.",
        criterios_ajuste="Avaliar bimestralmente. Ajustar metas se houver platô prolongado de 2 bimestres ou avanços inesperadamente rápidos.",
    ),

    # 3. Deficiência Visual
    _build_template(
        nome="Modelo Institucional - Deficiência Visual",
        publico_alvo="deficiencia_visual",
        descricao="Plano-base para alunos cegos ou com baixa visão. Foco em alfabetização Braille (cegueira), uso de recursos ópticos e digitais (baixa visão), orientação e mobilidade.",
        modalidade="individual",
        carga="4 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Inacessibilidade de materiais impressos convencionais"),
            ("pedagogica", "Falta de descrição verbal de imagens e gráficos em sala comum"),
            ("arquitetonica", "Sinalização tátil ausente; obstáculos no fluxo escolar"),
        ],
        objetivos=[
            ("curto", "Desenvolver percepção tátil e auditiva (cegueira) ou treinar funcionalidade visual residual (baixa visão)"),
            ("medio", "Adquirir leitura e escrita em Braille (cegueira) ou ampliar fluência com recursos ópticos (baixa visão)"),
            ("medio", "Desenvolver autonomia em orientação e mobilidade no espaço escolar"),
            ("longo", "Utilizar tecnologia assistiva (DOSVOX/NVDA, lupa eletrônica) para estudos autônomos"),
        ],
        recursos=[
            ("recurso_optico", "Lupa manual, telelupa, óculos especiais (baixa visão)"),
            ("material_ampliado", "Material com fonte ≥18pt, alto contraste e ilustrações simples"),
            ("software_acessivel", "Leitor de tela DOSVOX/NVDA + impressora Braille"),
            ("outro", "Reglete, punção, soroban, livro em Braille"),
        ],
        indicadores="Fluência crescente em Braille (palavras/min) ou em leitura ampliada. Autonomia em deslocamento na escola. Uso funcional de tecnologia assistiva.",
        orientacoes_sala_comum="Descrever oralmente imagens e o que está sendo escrito no quadro. Posicionar o aluno em local com boa luminosidade (baixa visão). Antecipar materiais para transcrição em Braille/ampliação.",
        adequacoes="Provas em Braille ou ampliadas, com tempo adicional. Atividades visuais substituídas por descrição verbal/tátil equivalente.",
        criterios_ajuste="Revisar plano após avaliação oftalmológica anual. Ajustar recursos se houver progressão da perda visual.",
    ),

    # 4. Deficiência Auditiva
    _build_template(
        nome="Modelo Institucional - Deficiência Auditiva / Surdez",
        publico_alvo="deficiencia_auditiva",
        descricao="Plano-base para alunos surdos ou com deficiência auditiva. Foco em Libras como L1, Português escrito como L2, e desenvolvimento da identidade surda.",
        modalidade="individual",
        carga="4 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Ausência de comunicação em Libras no ambiente escolar"),
            ("pedagogica", "Conteúdos pedagógicos sem mediação visual/sinalizada"),
            ("atitudinal", "Pouca convivência com pares surdos / falta de modelo linguístico"),
        ],
        objetivos=[
            ("curto", "Ampliar vocabulário em Libras (sinais cotidianos e escolares)"),
            ("medio", "Desenvolver fluência em Libras como primeira língua"),
            ("medio", "Adquirir leitura e escrita do Português como segunda língua (L2)"),
            ("longo", "Construir identidade bilíngue/bicultural surda"),
        ],
        recursos=[
            ("comunicacao_alternativa", "Material visual em Libras (vídeos, dicionários, glossários)"),
            ("recurso_auditivo", "Aparelhos auditivos / sistema FM (quando indicado)"),
            ("software_acessivel", "VLibras, HandTalk, dicionários digitais Libras-Português"),
        ],
        indicadores="Crescimento do vocabulário sinalizado; produção de textos em Português com estrutura compreensível; participação ativa em diálogos sinalizados.",
        orientacoes_sala_comum="Manter contato visual ao falar. Falar de frente, em ritmo natural. Usar recursos visuais (legendas, esquemas, vídeos legendados). Valorizar a Libras como língua materna.",
        adequacoes="Avaliação em Português L2 (estrutura adaptada). Provas com enunciados claros e visuais. Tradutor/Intérprete de Libras quando disponível.",
        criterios_ajuste="Avaliar bimestralmente progresso em Libras e Português escrito. Ajustar plano se houver mudança no equipamento auditivo ou diagnóstico.",
    ),

    # 5. Surdocegueira
    _build_template(
        nome="Modelo Institucional - Surdocegueira",
        publico_alvo="surdocegueira",
        descricao="Plano-base para alunos com perda concomitante das funções visual e auditiva. Foco em comunicação tátil, mediação contínua e construção de vínculos seguros.",
        modalidade="individual",
        carga="6 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Acesso à informação dependente de mediação contínua"),
            ("atitudinal", "Despreparo da comunidade escolar para interação tátil"),
            ("pedagogica", "Currículo padrão sem adaptação tátil/cinestésica"),
        ],
        objetivos=[
            ("curto", "Estabelecer vínculo seguro com mediador (guia-intérprete)"),
            ("curto", "Desenvolver sistema de comunicação tátil (Libras tátil, Tadoma, alfabeto manual na palma)"),
            ("medio", "Construir rotina previsível com objetos de referência"),
            ("longo", "Adquirir autonomia comunicativa e de mobilidade nos espaços conhecidos"),
        ],
        recursos=[
            ("comunicacao_alternativa", "Calendário de antecipação com objetos de referência"),
            ("comunicacao_alternativa", "Caixa de antecipação / boxes de atividade tátil"),
            ("outro", "Material tátil texturizado para discriminação e categorização"),
        ],
        indicadores="Reconhecimento crescente de objetos de referência; iniciativas comunicativas espontâneas; redução de comportamentos de auto-estimulação por desorientação.",
        orientacoes_sala_comum="Sempre identificar-se ao se aproximar (toque combinado). Respeitar tempo de processamento. Garantir presença constante do guia-intérprete. Antecipar mudanças de rotina.",
        adequacoes="Currículo profundamente individualizado. Avaliação por observação contínua e registros qualitativos.",
        criterios_ajuste="Plano revisto bimestralmente em conjunto com família e equipe multidisciplinar.",
    ),

    # 6. Transtorno do Espectro Autista (TEA)
    _build_template(
        nome="Modelo Institucional - Transtorno do Espectro Autista (TEA)",
        publico_alvo="transtorno_espectro_autista",
        descricao="Plano-base para alunos no espectro autista. Foco em comunicação funcional, regulação sensorial, habilidades sociais e flexibilidade cognitiva.",
        modalidade="individual",
        carga="4 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Dificuldade na comunicação social e uso pragmático da linguagem"),
            ("pedagogica", "Hipersensibilidade sensorial impedindo permanência em sala"),
            ("atitudinal", "Interpretação errônea de comportamentos repetitivos como indisciplina"),
        ],
        objetivos=[
            ("curto", "Aceitar e seguir rotina visual diária (chegada → atividades → saída)"),
            ("curto", "Tolerar ambiente da sala comum por períodos crescentes"),
            ("medio", "Desenvolver comunicação funcional (verbal ou alternativa por PECS)"),
            ("medio", "Iniciar e manter interações sociais simples com pares (turnos, jogos cooperativos)"),
            ("longo", "Generalizar aprendizagens entre AEE e sala comum / casa"),
        ],
        recursos=[
            ("rotina_visual", "Cronograma visual com pictogramas e velcro (PECS)"),
            ("comunicacao_alternativa", "Pranchas PECS / app de comunicação alternativa (CAA)"),
            ("outro", "Caixa sensorial / fones abafadores / brinquedos de regulação"),
        ],
        indicadores="Aumento de iniciativas comunicativas; redução de crises sensoriais; aumento de tempo em atividades dirigidas; trocas sociais com pares.",
        orientacoes_sala_comum="Manter rotina previsível e antecipar mudanças. Usar instruções claras e visuais. Permitir pausas sensoriais. Não punir comportamentos de regulação (stim).",
        adequacoes="Provas com enunciados claros, sem ambiguidade. Permitir respostas alternativas (digitar, apontar, ditar). Tempo adicional sem prejuízo.",
        criterios_ajuste="Reavaliar bimestralmente o nível de apoio. Considerar redução gradual de mediação conforme evolução. Articular com terapias externas (fono, TO, psicologia).",
    ),

    # 7. Altas Habilidades / Superdotação
    _build_template(
        nome="Modelo Institucional - Altas Habilidades / Superdotação",
        publico_alvo="altas_habilidades",
        descricao="Plano-base para alunos com altas habilidades/superdotação. Foco em enriquecimento curricular, aprofundamento e desenvolvimento da criatividade.",
        modalidade="pequeno_grupo",
        carga="3 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("pedagogica", "Currículo regular insuficiente para o ritmo/profundidade de aprendizagem"),
            ("atitudinal", "Estereótipos sobre o aluno superdotado (rotulação, isolamento)"),
            ("pedagogica", "Falta de desafios cognitivos e oportunidades de aprofundamento"),
        ],
        objetivos=[
            ("curto", "Mapear áreas de interesse e talento (Modelo de Renzulli)"),
            ("medio", "Realizar projetos de enriquecimento Tipo I (exposição), II (habilidades) e III (produção autônoma)"),
            ("medio", "Desenvolver pensamento criativo e divergente (resolução de problemas abertos)"),
            ("longo", "Construir produção autoral aplicada a problemas reais da comunidade"),
        ],
        recursos=[
            ("outro", "Material de pesquisa avançado (livros, periódicos, cursos online)"),
            ("software_acessivel", "Plataformas de aprofundamento (Khan Academy, Scratch, simuladores)"),
            ("outro", "Mentoria com especialista da área de interesse (quando viável)"),
        ],
        indicadores="Conclusão de projetos de enriquecimento Tipo III; engajamento em desafios extracurriculares; produção criativa documentada.",
        orientacoes_sala_comum="Oferecer atividades complementares de aprofundamento (não apenas mais exercícios do mesmo). Permitir avanço de etapas em conteúdos dominados. Estimular liderança e tutoria de pares.",
        adequacoes="Compactação curricular: dispensar exercícios de conteúdo já dominado, substituindo por aprofundamento. Avaliação por projetos.",
        criterios_ajuste="Revisar plano bimestralmente. Ajustar áreas de enriquecimento conforme novos interesses surjam. Articular com universidades / olimpíadas científicas.",
    ),

    # 8. Deficiência Múltipla
    _build_template(
        nome="Modelo Institucional - Deficiência Múltipla",
        publico_alvo="deficiencia_multipla",
        descricao="Plano-base para alunos com associação de duas ou mais deficiências. Foco em comunicação funcional, vida diária e participação possível, com forte articulação multidisciplinar.",
        modalidade="individual",
        carga="6 horas",
        local="Sala de Recursos Multifuncionais",
        barreiras=[
            ("comunicacional", "Comunicação restrita ou ausente, exigindo alternativas"),
            ("pedagogica", "Necessidade de currículo profundamente individualizado"),
            ("atitudinal", "Expectativas reduzidas do entorno, limitando oportunidades"),
        ],
        objetivos=[
            ("curto", "Estabelecer rotina previsível com sinais/objetos de referência"),
            ("curto", "Identificar canal preferencial de comunicação (sim/não, escolhas, CAA)"),
            ("medio", "Desenvolver habilidades de vida diária no contexto escolar (alimentação, higiene, locomoção)"),
            ("medio", "Ampliar repertório comunicativo funcional com a família e pares"),
            ("longo", "Promover participação possível em atividades coletivas, segundo seu canal"),
        ],
        recursos=[
            ("comunicacao_alternativa", "Sistema de CAA personalizado (pictogramas, objetos reais, voz sintetizada)"),
            ("mobiliario_adaptado", "Mobiliário e posicionadores adequados ao perfil motor"),
            ("rotina_visual", "Calendário/agenda de antecipação tátil-visual"),
        ],
        indicadores="Sinais de iniciativa comunicativa; engajamento em atividades; conquistas em vida diária registradas qualitativamente.",
        orientacoes_sala_comum="Articular permanentemente com família, AEE, terapeutas (fono, TO, fisio) e equipe gestora. Documentar pequenos avanços. Garantir mediador presente.",
        adequacoes="Currículo profundamente individualizado, focado em habilidades funcionais. Avaliação processual qualitativa.",
        criterios_ajuste="Revisão bimestral em equipe multidisciplinar. Ajustes baseados em mudanças de quadro clínico ou em aquisições da criança.",
    ),
]


async def seed_aee_templates(db) -> int:
    """Insere os modelos institucionais que ainda não existem (idempotente).

    Critério de unicidade: campo `nome`. Não sobrescreve modelos existentes
    (preserva edições feitas por administradores).

    Returns:
        Quantidade de modelos novos inseridos.
    """
    inserted = 0
    for tpl in TEMPLATES_INSTITUCIONAIS:
        existing = await db.planos_aee_templates.find_one(
            {"nome": tpl["nome"]}, {"_id": 0, "id": 1}
        )
        if existing:
            continue
        await db.planos_aee_templates.insert_one(dict(tpl))
        inserted += 1
    if inserted:
        logger.info(f"Seed AEE: {inserted} modelo(s) institucional(is) inserido(s).")
    return inserted
