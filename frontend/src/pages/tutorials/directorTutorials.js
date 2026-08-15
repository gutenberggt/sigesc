export const directorTutorials = [
  {
    slug: 'primeiros-passos',
    title: 'Primeiros passos e painel do diretor',
    category: 'Comece aqui',
    estimatedTime: '7 min',
    systemRoute: '/dashboard',
    objective: 'Entender o papel do diretor no SIGESC, reconhecer os principais blocos de gestão e saber como iniciar uma rotina de acompanhamento da escola.',
    intro: 'O diretor usa o SIGESC para combinar visão pedagógica, acompanhamento operacional e responsabilidade documental. A melhor rotina começa pelo panorama geral da unidade e avança para evidências específicas antes de qualquer decisão.',
    before: [
      'Tenha seu usuário e senha do SIGESC.',
      'Confirme que o perfil ativo é Diretor(a).',
      'Verifique se a escola vinculada ao seu acesso é a correta.'
    ],
    steps: [
      { title: 'Entre no SIGESC', text: 'Faça login e confira nome, perfil ativo, escola vinculada e ano letivo antes de abrir qualquer módulo.' },
      { title: 'Leia o panorama da escola', text: 'Use os indicadores de turmas, estudantes, relatórios e avisos para formar uma visão inicial do que exige atenção.' },
      { title: 'Reconheça os blocos do menu', text: 'Localize Gestão Institucional, Gestão Escolar, Gestão Pedagógica, Monitoramento e Análise, Gestão Social e Recursos Humanos.' },
      { title: 'Use a busca do menu', text: 'Procure por termos como “diário”, “frequência”, “plano de ação”, “declarações” ou “RH” quando não encontrar um recurso rapidamente.' },
      { title: 'Priorize acompanhamento antes da ação', text: 'Abra primeiro os painéis de acompanhamento e confirme a evidência. Só depois encaminhe correções, intervenções ou decisões administrativas.' }
    ],
    observe: ['Perfil ativo', 'Escola correta', 'Ano letivo', 'Turmas e estudantes da unidade', 'Itens de menu disponíveis'],
    bestPractices: ['Faça uma leitura geral do painel no início da rotina.', 'Use dados do SIGESC como evidência para orientar a equipe.', 'Evite decisões com base em um único indicador isolado.'],
    attention: ['Alguns recursos podem variar conforme a matriz de permissões definida pela rede.', 'Se um item não estiver visível, não tente acessar por endereço direto como forma de contornar a permissão.'],
    doneWhen: ['Você sabe localizar os principais módulos da direção.', 'Você consegue confirmar o contexto da escola antes de analisar qualquer dado.']
  },
  {
    slug: 'turmas-estudantes',
    title: 'Turmas e estudantes: visão da escola',
    category: 'Comece aqui',
    estimatedTime: '8 min',
    systemRoute: '/admin/classes',
    objective: 'Usar turmas e estudantes como base para qualquer análise pedagógica ou administrativa da unidade.',
    intro: 'Quase toda decisão escolar depende de um recorte correto: escola, turma, etapa, turno, período e estudante. Confirmar esse contexto evita interpretar dados de uma matrícula antiga ou de uma turma diferente.',
    before: ['Confirme escola e ano letivo.', 'Tenha em mente a turma ou estudante que deseja acompanhar.'],
    steps: [
      { title: 'Abra Turmas', text: 'Confira nome da turma, etapa/série, turno, ano letivo e situação.' },
      { title: 'Escolha o recorte correto', text: 'Evite trabalhar apenas pelo nome da turma. Confirme também turno, série e ano.' },
      { title: 'Consulte os estudantes', text: 'Acesse a área de estudantes e use busca e filtros para localizar o estudante no vínculo atual.' },
      { title: 'Relacione o cadastro ao problema', text: 'Antes de investigar frequência, boletim, intervenção ou documento, confirme a turma e o vínculo atual do estudante.' },
      { title: 'Formule a pergunta de gestão', text: 'Defina o que precisa responder: há pendência de diário, risco de infrequência, problema de cobertura curricular ou necessidade de intervenção?' }
    ],
    observe: ['Turma', 'Turno', 'Etapa/série', 'Ano letivo', 'Vínculo atual do estudante'],
    bestPractices: ['Trabalhe sempre no recorte escola → turma → período → estudante.', 'Use o cadastro para contextualizar as evidências de outros módulos.'],
    attention: ['Estudantes transferidos ou remanejados podem possuir histórico em vínculos anteriores; não misture registros de períodos distintos.'],
    doneWhen: ['Você consegue localizar a turma e o estudante corretos.', 'Você sabe qual recorte usar nos módulos seguintes.']
  },
  {
    slug: 'historico-movimentacoes',
    title: 'Histórico e movimentações do estudante',
    category: 'Comece aqui',
    estimatedTime: '8 min',
    systemRoute: '/admin/students',
    objective: 'Interpretar o histórico do estudante sem apagar a sequência de matrículas, transferências, remanejamentos e registros pedagógicos.',
    intro: 'Para a direção, o histórico do estudante ajuda a explicar mudanças de turma, escola e período. Ele deve ser lido como uma linha do tempo, e não como um único cadastro atual.',
    before: ['Localize o estudante correto.', 'Confirme a matrícula atual antes de consultar vínculos anteriores.'],
    steps: [
      { title: 'Localize o estudante', text: 'Use a busca de estudantes e confira nome completo, escola e turma atual.' },
      { title: 'Abra o histórico quando disponível', text: 'Entre no histórico do estudante a partir do cadastro e observe a sequência de vínculos.' },
      { title: 'Leia a linha do tempo', text: 'Identifique datas de matrícula, encerramento, transferência ou remanejamento e a escola/turma correspondente.' },
      { title: 'Relacione períodos e registros', text: 'Ao analisar frequência ou documento, confirme em qual vínculo aquele registro deveria estar associado.' },
      { title: 'Preserve a história escolar', text: 'Em caso de inconsistência, trate a correção como reconstrução auditável. Não apague fatos históricos apenas para “simplificar” o cadastro.' }
    ],
    observe: ['Datas de entrada e saída', 'Escola e turma de cada vínculo', 'Ordem cronológica', 'Registros ligados ao período correto'],
    bestPractices: ['Use datas como referência principal.', 'Diferencie matrícula atual de vínculo histórico.', 'Documente qualquer necessidade de correção antes de alterá-la.'],
    attention: ['Uma transferência pode encerrar um vínculo e iniciar outro no mesmo dia.', 'Histórico escolar exige cuidado porque afeta documentos e continuidade pedagógica.'],
    doneWhen: ['Você consegue explicar a sequência de vínculos do estudante.', 'Você sabe identificar a qual período pertence um registro.']
  },
  {
    slug: 'acompanhamento-diarios',
    title: 'Acompanhamento dos Diários de Classe',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '10 min',
    systemRoute: '/admin/diary-dashboard',
    objective: 'Acompanhar o preenchimento dos diários e localizar turmas ou períodos que precisam de ação da gestão.',
    intro: 'O painel de diários transforma uma cobrança genérica em evidência objetiva. A direção consegue ver onde há pendências e organizar o acompanhamento junto à coordenação e aos professores.',
    before: ['Defina o período a acompanhar.', 'Confirme escola e ano letivo.'],
    steps: [
      { title: 'Abra Acompanhamento de Diários', text: 'Acesse o painel e confirme o recorte da escola e do período.' },
      { title: 'Leia o panorama geral', text: 'Observe primeiro quais turmas apresentam sinais de pendência antes de abrir casos individuais.' },
      { title: 'Identifique a dimensão pendente', text: 'Diferencie falta de frequência, conteúdo, nota ou outra informação do diário.' },
      { title: 'Priorize impacto', text: 'Dê atenção primeiro ao que compromete fechamento, frequência, boletim ou continuidade pedagógica.' },
      { title: 'Encaminhe com evidência', text: 'Ao conversar com coordenação ou professor, informe turma, período e tipo de pendência.' },
      { title: 'Confirme a resolução', text: 'Volte ao painel depois do prazo combinado e verifique se o problema foi resolvido.' }
    ],
    observe: ['Turmas com pendência', 'Período', 'Tipo de registro ausente', 'Recorrência', 'Impacto no fechamento'],
    bestPractices: ['Faça acompanhamento semanal.', 'Use a coordenação pedagógica como parceira na leitura e no retorno aos professores.', 'Registre prazos claros para pendências relevantes.'],
    attention: ['Ausência de lançamento não significa necessariamente ausência de trabalho pedagógico; investigue a causa antes de concluir.'],
    doneWhen: ['Você sabe quais turmas precisam de atenção.', 'Você consegue encaminhar cada pendência com informação objetiva.']
  },
  {
    slug: 'frequencia',
    title: 'Frequência: risco e acompanhamento',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '9 min',
    systemRoute: '/admin/attendance',
    objective: 'Interpretar frequência por turma e estudante e identificar padrões de ausência que exigem resposta da escola.',
    intro: 'A direção deve olhar além do percentual. Sequências de faltas, mudança de padrão e concentração de ausências em determinados estudantes ou períodos podem indicar risco de evasão ou necessidade de contato com a família.',
    before: ['Selecione turma e período corretos.', 'Confirme a matrícula atual do estudante quando a análise for individual.'],
    steps: [
      { title: 'Abra Frequência', text: 'Escolha a escola, turma e período que deseja analisar.' },
      { title: 'Leia a turma antes do estudante', text: 'Observe se o problema está concentrado em poucos estudantes ou distribuído na turma.' },
      { title: 'Procure padrões', text: 'Identifique faltas consecutivas, recorrentes ou aumento recente de ausências.' },
      { title: 'Cruze com justificativas', text: 'Consulte atestados e justificativas antes de tratar toda ausência como abandono ou negligência.' },
      { title: 'Defina o encaminhamento', text: 'Quando houver risco, articule coordenação, secretaria, família e busca ativa conforme o protocolo da rede.' },
      { title: 'Acompanhe a mudança', text: 'Depois do contato ou intervenção, verifique se a frequência voltou ao padrão esperado.' }
    ],
    observe: ['Faltas consecutivas', 'Mudança recente de padrão', 'Justificativas', 'Estudantes com maior risco', 'Retorno após intervenção'],
    bestPractices: ['Intervenha cedo em padrões de ausência.', 'Registre contatos e encaminhamentos nos canais institucionais adequados.', 'Evite interpretar percentual sem contexto.'],
    attention: ['Frequência baixa pode ter causas sociais, de saúde, transporte ou vínculo escolar; o dado não explica sozinho o motivo.'],
    doneWhen: ['Você identificou os casos prioritários.', 'Você definiu quem fará o acompanhamento e quando será revisado.']
  },
  {
    slug: 'atestados-justificativas',
    title: 'Atestados e justificativas de ausência',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '7 min',
    systemRoute: '/admin/attendance',
    objective: 'Diferenciar falta, falta justificada e situação de saúde para interpretar corretamente a frequência e orientar a equipe.',
    intro: 'Uma ausência pode estar registrada corretamente e ainda exigir acompanhamento pedagógico. O diretor precisa separar a situação administrativa da presença do estudante e a necessidade de recuperação de aprendizagem.',
    before: ['Localize estudante e período corretos.', 'Tenha em mente que justificativa não apaga automaticamente a necessidade de acompanhamento pedagógico.'],
    steps: [
      { title: 'Consulte a frequência', text: 'Localize as datas de ausência do estudante.' },
      { title: 'Verifique justificativas', text: 'Confira se existem atestados ou registros institucionais associados ao período.' },
      { title: 'Separe os conceitos', text: 'Diferencie presença, ausência, justificativa administrativa e necessidade de compensação pedagógica.' },
      { title: 'Oriente a continuidade', text: 'Quando necessário, combine com coordenação e professores como o estudante recuperará conteúdos ou atividades.' },
      { title: 'Proteja a informação', text: 'Dados de saúde são sensíveis. Compartilhe somente o necessário para o atendimento escolar.' }
    ],
    observe: ['Datas cobertas', 'Tipo de justificativa', 'Frequência registrada', 'Impacto pedagógico', 'Necessidade de acompanhamento'],
    bestPractices: ['Trate saúde com confidencialidade.', 'Use a justificativa para compreender o contexto, não para rotular o estudante.', 'Planeje continuidade pedagógica quando a ausência for prolongada.'],
    attention: ['Atestado médico não significa presença em sala.', 'Informações clínicas não devem circular em grupos ou canais não autorizados.'],
    doneWhen: ['Você distingue a situação administrativa da pedagógica.', 'Você sabe qual acompanhamento precisa ser feito após a ausência.']
  },
  {
    slug: 'registro-conteudos',
    title: 'Registro de Conteúdos: acompanhar o que foi trabalhado',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '8 min',
    systemRoute: '/admin/learning-objects',
    objective: 'Acompanhar se os conteúdos e objetos de conhecimento estão sendo registrados com regularidade e coerência.',
    intro: 'O registro de conteúdo é uma evidência do percurso pedagógico. Para a direção, ele ajuda a compreender a continuidade do trabalho e a apoiar a coordenação quando há lacunas recorrentes.',
    before: ['Defina turma, componente e período.', 'Tenha em mente o calendário e o planejamento da escola.'],
    steps: [
      { title: 'Abra Registro de Conteúdos', text: 'Selecione turma, componente e período corretos.' },
      { title: 'Observe regularidade', text: 'Verifique se existem registros compatíveis com os dias letivos e a rotina da turma.' },
      { title: 'Procure lacunas', text: 'Identifique períodos extensos sem registro ou descrições excessivamente genéricas.' },
      { title: 'Relacione com cobertura', text: 'Quando houver dúvida sobre o avanço curricular, consulte Cobertura Curricular.' },
      { title: 'Encaminhe à coordenação', text: 'Pendências de natureza pedagógica devem ser analisadas em conjunto com a coordenação e o professor.' }
    ],
    observe: ['Regularidade', 'Coerência com calendário', 'Períodos sem registro', 'Descrição do que foi trabalhado'],
    bestPractices: ['Use o módulo para acompanhar continuidade, não para microgerenciar cada aula.', 'Priorize padrões recorrentes e lacunas que afetem o currículo.'],
    attention: ['Quantidade de registros não mede, sozinha, qualidade da aula.'],
    doneWhen: ['Você identifica se existe continuidade de registros.', 'Você sabe quando acionar a coordenação para análise pedagógica.']
  },
  {
    slug: 'cobertura-curricular',
    title: 'Cobertura Curricular: previsto x realizado',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '9 min',
    systemRoute: '/admin/curriculo/cobertura',
    objective: 'Usar a cobertura curricular para identificar lacunas entre o que foi previsto e o que foi efetivamente registrado.',
    intro: 'A cobertura curricular ajuda a direção a enxergar tendências por turma e componente. Ela não substitui a coordenação pedagógica, mas oferece evidências para priorizar apoio e reorganização.',
    before: ['Confirme ano, escola e turma.', 'Considere o momento do calendário: nem todo conteúdo precisa estar concluído no início do período.'],
    steps: [
      { title: 'Abra Cobertura Curricular', text: 'Selecione o recorte correto de escola, turma e período.' },
      { title: 'Leia o panorama', text: 'Observe componentes ou turmas com cobertura abaixo do esperado para o momento.' },
      { title: 'Compare com o calendário', text: 'Verifique se a diferença é realmente atraso ou apenas sequência planejada ainda em andamento.' },
      { title: 'Volte aos registros', text: 'Consulte conteúdos lançados para entender a origem da lacuna.' },
      { title: 'Defina apoio', text: 'Quando houver atraso real, combine com coordenação e professores um plano de recuperação ou reorganização.' }
    ],
    observe: ['Cobertura por turma/componente', 'Momento do calendário', 'Lacunas recorrentes', 'Evidências no registro de conteúdos'],
    bestPractices: ['Analise tendência e contexto.', 'Use cobertura para orientar apoio pedagógico.', 'Reavalie depois do prazo combinado.'],
    attention: ['Cobertura curricular não é sinônimo de aprendizagem; ela mede execução/registro do percurso previsto.'],
    doneWhen: ['Você sabe onde há possível lacuna curricular.', 'Você definiu como confirmar a causa e acompanhar a resposta.']
  },
  {
    slug: 'calendario-diario',
    title: 'Calendário do Diário: dias letivos e consistência',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '7 min',
    systemRoute: '/admin/diary-calendar',
    objective: 'Entender como o calendário operacional influencia frequência, conteúdo e consistência do Diário de Classe.',
    intro: 'Antes de cobrar um lançamento, confirme se a data pertence ao calendário letivo aplicável. Datas incorretas podem gerar aparentes pendências e distorções de frequência.',
    before: ['Saiba qual período ou data deseja verificar.', 'Confirme o ano letivo.'],
    steps: [
      { title: 'Abra o Calendário do Diário', text: 'Localize o período e observe dias letivos, exceções e marcações disponíveis.' },
      { title: 'Confirme a data questionada', text: 'Verifique se o dia era letivo para aquela turma ou etapa.' },
      { title: 'Relacione com o diário', text: 'Compare a data com frequência e conteúdo antes de apontar uma pendência.' },
      { title: 'Identifique inconsistências', text: 'Se houver divergência real entre calendário e registros, encaminhe para o responsável pela correção.' }
    ],
    observe: ['Dias letivos', 'Exceções', 'Datas sem atividade', 'Coerência com frequência e conteúdo'],
    bestPractices: ['Confirme o calendário antes de cobrar lançamentos por data.', 'Use o mesmo recorte de período nos módulos relacionados.'],
    attention: ['Feriados, paralisações, reposições ou calendários específicos podem alterar a expectativa de registro.'],
    doneWhen: ['Você sabe dizer se uma data exigia registro.', 'Você consegue distinguir ausência de lançamento de um dia não letivo.']
  },
  {
    slug: 'integridade-grade',
    title: 'Integridade da Grade Horária',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '8 min',
    systemRoute: '/admin/grade-integrity',
    objective: 'Identificar inconsistências de grade que podem afetar diário, frequência, conteúdos e carga horária.',
    intro: 'Problemas de grade podem aparecer como erros em vários módulos ao mesmo tempo. A direção deve tratá-los como causa estrutural quando há conflito de horários, componentes ou atribuições.',
    before: ['Confirme turma e período.', 'Tenha em mente qual comportamento estranho motivou a consulta.'],
    steps: [
      { title: 'Abra Integridade da Grade', text: 'Selecione a turma ou recorte que precisa verificar.' },
      { title: 'Observe alertas estruturais', text: 'Procure conflitos, lacunas ou inconsistências apontadas pelo sistema.' },
      { title: 'Relacione com o sintoma', text: 'Pergunte se a inconsistência explica falhas de frequência, conteúdo, professor ou carga horária.' },
      { title: 'Encaminhe a correção na origem', text: 'Evite corrigir apenas o efeito em outro módulo. Ajuste a configuração estrutural com quem possui permissão adequada.' },
      { title: 'Revalide', text: 'Depois da correção, volte ao módulo afetado e confira se o comportamento foi normalizado.' }
    ],
    observe: ['Conflitos', 'Lacunas', 'Componentes', 'Horários', 'Impacto em outros módulos'],
    bestPractices: ['Corrija causa estrutural antes de ajustar registros derivados.', 'Documente inconsistências relevantes e a data da correção.'],
    attention: ['Alterações de grade podem ter efeito em registros futuros e históricos; confirme o alcance antes de mudar configurações.'],
    doneWhen: ['Você identificou se há problema estrutural.', 'Você sabe qual módulo ou responsável deve corrigir a origem.']
  },
  {
    slug: 'diario-aee',
    title: 'Diário AEE: acompanhamento pela direção',
    category: 'Acompanhamento pedagógico',
    estimatedTime: '9 min',
    systemRoute: '/admin/diario-aee',
    objective: 'Acompanhar o Diário AEE sob a perspectiva da gestão, respeitando a especificidade pedagógica e a confidencialidade do atendimento.',
    intro: 'A direção não precisa transformar o Diário AEE em um instrumento burocrático. O objetivo é verificar continuidade, existência de planejamento e registros, e apoiar as condições institucionais do atendimento.',
    before: ['Confirme escola, ano e turma AEE.', 'Lembre que informações do AEE podem conter dados sensíveis.'],
    steps: [
      { title: 'Abra o Diário AEE', text: 'Confirme os filtros de escola, ano e turma antes de interpretar qualquer informação.' },
      { title: 'Observe a organização geral', text: 'Verifique estudantes vinculados, existência de planos e continuidade dos atendimentos.' },
      { title: 'Leia sem extrapolar o papel da direção', text: 'Use o registro para acompanhar oferta e continuidade, não para substituir a análise técnica do professor AEE.' },
      { title: 'Identifique barreiras institucionais', text: 'Procure situações que dependam da gestão: horário, espaço, recursos, articulação com sala comum ou organização da equipe.' },
      { title: 'Proteja a confidencialidade', text: 'Não reproduza informações pessoais ou de saúde fora dos canais institucionais necessários.' }
    ],
    observe: ['Planos existentes', 'Regularidade de atendimento', 'Ausências', 'Barreiras institucionais', 'Necessidade de recursos'],
    bestPractices: ['Converse com professor AEE e coordenação quando houver lacunas.', 'Atue sobre condições institucionais que a direção pode resolver.', 'Mantenha confidencialidade.'],
    attention: ['AEE não deve ser reduzido a diagnóstico clínico.', 'Nem toda condição de saúde implica público-alvo da educação especial.'],
    doneWhen: ['Você consegue verificar continuidade do AEE.', 'Você identificou eventuais ações que dependem da gestão escolar.']
  },
  {
    slug: 'pre-matriculas',
    title: 'Pré-Matrículas: demanda e decisões da escola',
    category: 'Gestão escolar e intervenção',
    estimatedTime: '9 min',
    systemRoute: '/admin/pre-matriculas',
    objective: 'Acompanhar solicitações de pré-matrícula e organizar a resposta da escola com critérios, registro e comunicação claros.',
    intro: 'A pré-matrícula é uma porta de entrada da escola. A direção deve acompanhar demanda, capacidade de atendimento e encaminhamentos sem transformar a etapa em matrícula definitiva antes da confirmação institucional.',
    before: ['Confirme o ano letivo e a escola.', 'Conheça a capacidade e as regras locais de atendimento.'],
    steps: [
      { title: 'Abra Pré-Matrículas', text: 'Observe solicitações pendentes, situação e dados necessários para análise.' },
      { title: 'Priorize pendências', text: 'Identifique solicitações aguardando decisão ou informação complementar.' },
      { title: 'Confirme disponibilidade', text: 'Antes de encaminhar aprovação, confira etapa, turno, turma e capacidade de atendimento.' },
      { title: 'Registre a decisão corretamente', text: 'Use o fluxo do sistema e evite decisões apenas por mensagens informais.' },
      { title: 'Acompanhe a conversão', text: 'Depois da confirmação, verifique se a matrícula efetiva foi concluída pela equipe responsável.' }
    ],
    observe: ['Status da solicitação', 'Etapa/série', 'Turno', 'Disponibilidade', 'Pendências documentais'],
    bestPractices: ['Defina rotina de análise das solicitações.', 'Mantenha critérios transparentes e coerentes.', 'Diferencie pré-matrícula de matrícula concluída.'],
    attention: ['A aprovação de pré-matrícula não deve criar expectativa diferente das regras oficiais da rede.', 'Dados pessoais devem ser tratados apenas por usuários autorizados.'],
    doneWhen: ['Você sabe quais solicitações aguardam decisão.', 'Você consegue acompanhar até a matrícula efetiva ou outro encaminhamento.']
  },
  {
    slug: 'intervencoes',
    title: 'Intervenções Necessárias: priorizar atenção',
    category: 'Gestão escolar e intervenção',
    estimatedTime: '9 min',
    systemRoute: '/admin/intervencoes',
    objective: 'Usar o feed de intervenções para priorizar situações que exigem resposta da escola e distribuir responsabilidades.',
    intro: 'A intervenção útil nasce de uma evidência clara e termina com revisão. O diretor deve garantir que alertas relevantes tenham responsável, prazo e acompanhamento.',
    before: ['Confirme escola e período.', 'Considere quais equipes podem atuar em cada tipo de situação.'],
    steps: [
      { title: 'Abra Intervenções Necessárias', text: 'Leia os itens priorizados pelo sistema e identifique a evidência que originou cada caso.' },
      { title: 'Separe urgência de importância', text: 'Priorize riscos de abandono, pendências de fechamento e situações com impacto imediato.' },
      { title: 'Confirme a causa', text: 'Consulte frequência, diário, cobertura ou cadastro antes de definir a ação.' },
      { title: 'Atribua responsabilidade', text: 'Defina quem conduzirá o próximo passo: direção, coordenação, secretaria, professor ou outra equipe.' },
      { title: 'Defina prazo e retorno', text: 'Uma intervenção sem data de revisão vira apenas uma lista de problemas.' }
    ],
    observe: ['Evidência de origem', 'Prioridade', 'Responsável', 'Prazo', 'Situação após retorno'],
    bestPractices: ['Trabalhe com poucos itens prioritários por vez.', 'Registre decisões e responsáveis.', 'Reavalie a evidência após a ação.'],
    attention: ['Alertas automatizados apoiam a decisão, mas não substituem análise humana e contexto escolar.'],
    doneWhen: ['Cada situação prioritária possui responsável e próximo passo.', 'Você definiu quando o resultado será revisado.']
  },
  {
    slug: 'plano-acao',
    title: 'Plano de Ação: do diagnóstico ao acompanhamento',
    category: 'Gestão escolar e intervenção',
    estimatedTime: '10 min',
    systemRoute: '/admin/plano-acao',
    objective: 'Transformar evidências do SIGESC em ações com responsável, prazo, indicador e revisão.',
    intro: 'O plano de ação é onde a gestão deixa de apenas observar problemas e passa a organizar respostas verificáveis. Ele deve ser simples o suficiente para ser acompanhado e específico o suficiente para ser avaliado.',
    before: ['Tenha uma evidência concreta que justifique a ação.', 'Defina qual resultado precisa mudar.'],
    steps: [
      { title: 'Abra Plano de Ação', text: 'Localize os itens existentes ou inicie a leitura das ações propostas para a escola.' },
      { title: 'Escreva o problema de forma observável', text: 'Prefira “Turma X está com 18% de registros de conteúdo pendentes no período” a “Professores não estão preenchendo”.' },
      { title: 'Defina uma ação executável', text: 'Estabeleça o que será feito, por quem e até quando.' },
      { title: 'Escolha como medir', text: 'Use um indicador que permita verificar se a situação mudou.' },
      { title: 'Acompanhe o prazo', text: 'Revise antes do vencimento quando houver bloqueios.' },
      { title: 'Feche com evidência', text: 'Considere concluída somente quando o dado ou resultado esperado estiver confirmado.' }
    ],
    observe: ['Problema objetivo', 'Responsável', 'Prazo', 'Indicador', 'Evidência de conclusão'],
    bestPractices: ['Evite ações genéricas.', 'Defina poucos compromissos realmente acompanháveis.', 'Use o SIGESC para verificar o resultado depois.'],
    attention: ['Plano de ação não deve ser usado para exposição pessoal ou punição automática de servidores.'],
    doneWhen: ['A ação possui problema, responsável, prazo e indicador.', 'Você sabe qual evidência encerrará o item.']
  },
  {
    slug: 'avisos-calendario',
    title: 'Avisos e calendário: comunicação da rotina escolar',
    category: 'Gestão escolar e intervenção',
    estimatedTime: '7 min',
    systemRoute: '/avisos',
    objective: 'Usar avisos e calendário para reduzir ruído de comunicação e dar previsibilidade à comunidade escolar.',
    intro: 'Boa gestão depende de informação previsível. Avisos e calendário devem registrar o que a comunidade precisa saber, com data, público e ação esperada claramente definidos.',
    before: ['Defina quem precisa receber a informação.', 'Confirme data e objetivo do comunicado.'],
    steps: [
      { title: 'Abra Avisos', text: 'Leia os comunicados existentes antes de publicar informação duplicada.' },
      { title: 'Defina o público', text: 'Especifique se o aviso é para toda a escola, equipe, professores, famílias ou outro grupo.' },
      { title: 'Escreva de forma objetiva', text: 'Informe o que acontecerá, quando, onde e o que a pessoa precisa fazer.' },
      { title: 'Relacione ao calendário', text: 'Quando houver data importante, confira se o calendário institucional está coerente.' },
      { title: 'Evite canais paralelos como fonte oficial', text: 'Mensagens em aplicativos podem complementar, mas a informação institucional deve permanecer registrada no sistema quando aplicável.' }
    ],
    observe: ['Público', 'Data', 'Objetivo', 'Ação esperada', 'Coerência com calendário'],
    bestPractices: ['Use linguagem curta e inequívoca.', 'Evite publicar o mesmo aviso várias vezes.', 'Revise datas antes de enviar.'],
    attention: ['Não publique dados pessoais ou sensíveis em avisos gerais.'],
    doneWhen: ['O comunicado está claro para o público correto.', 'A data e a ação esperada estão inequívocas.']
  },
  {
    slug: 'rh-folha',
    title: 'RH / Folha: visão da direção escolar',
    category: 'Gestão escolar e intervenção',
    estimatedTime: '9 min',
    systemRoute: '/admin/hr',
    objective: 'Acompanhar informações de pessoal disponíveis à direção e identificar situações que exigem correção ou encaminhamento administrativo.',
    intro: 'O módulo de RH reúne informações que podem afetar a organização da escola, como lotações e carga horária. A direção deve usar esses dados como base para conferência e encaminhamento, respeitando as competências da secretaria de educação.',
    before: ['Confirme escola e período/ano.', 'Saiba quais alterações a direção pode realizar e quais dependem da SEMED.'],
    steps: [
      { title: 'Abra RH / Folha', text: 'Confira os servidores vinculados e o contexto da unidade.' },
      { title: 'Revise vínculos relevantes', text: 'Observe lotação, função e demais informações que influenciam a organização escolar.' },
      { title: 'Compare com a realidade da escola', text: 'Identifique divergências entre o sistema e a situação efetiva.' },
      { title: 'Separe correção local de encaminhamento', text: 'Nem todo dado pode ser alterado pela direção. Encaminhe à área competente quando necessário.' },
      { title: 'Confirme depois da correção', text: 'Volte ao módulo para verificar se o ajuste foi refletido corretamente.' }
    ],
    observe: ['Servidor', 'Função', 'Lotação', 'Carga horária quando disponível', 'Divergências'],
    bestPractices: ['Trabalhe com evidência documental.', 'Não altere dados de pessoal sem competência definida.', 'Registre encaminhamentos importantes.'],
    attention: ['Dados funcionais são administrativos e podem ser sensíveis.', 'A direção não deve assumir competências exclusivas do RH/SEMED.'],
    doneWhen: ['Você consegue identificar divergências relevantes.', 'Você sabe quais casos resolve na escola e quais precisa encaminhar.']
  },
  {
    slug: 'boletins',
    title: 'Boletim Online: conferência dos resultados',
    category: 'Documentos e fechamento',
    estimatedTime: '8 min',
    systemRoute: '/admin/bulletins',
    objective: 'Conferir resultados consolidados antes de orientar famílias, professores ou ações de fechamento.',
    intro: 'O boletim é uma visão consolidada do percurso do estudante. Para a direção, ele serve como conferência e comunicação, não como substituto da análise do diário e das situações pedagógicas que produziram o resultado.',
    before: ['Confirme estudante, turma e período.', 'Verifique se o período de lançamento já está em fase de conferência.'],
    steps: [
      { title: 'Abra Boletim Online', text: 'Selecione o estudante ou recorte necessário e confirme período e turma.' },
      { title: 'Leia o conjunto', text: 'Observe componentes, resultados e frequência sem se concentrar apenas em uma nota isolada.' },
      { title: 'Identifique incoerências', text: 'Quando algo parecer incorreto, volte ao diário, frequência ou registro de origem.' },
      { title: 'Evite corrigir pelo documento', text: 'A correção deve acontecer na fonte do dado, não apenas na apresentação do boletim.' },
      { title: 'Use como evidência de conferência', text: 'Depois das correções, gere ou consulte novamente para confirmar o resultado consolidado.' }
    ],
    observe: ['Período', 'Componentes', 'Resultados', 'Frequência', 'Coerência com dados de origem'],
    bestPractices: ['Confira antes de reuniões ou entrega às famílias.', 'Corrija na fonte.', 'Preserve a versão oficial quando houver geração verificável.'],
    attention: ['O boletim mostra resultado consolidado; ele não explica sozinho as causas do desempenho.'],
    doneWhen: ['Você conferiu o resultado no período correto.', 'Você sabe onde investigar qualquer divergência encontrada.']
  },
  {
    slug: 'livro-promocao',
    title: 'Livro de Promoção: acompanhar o fechamento',
    category: 'Documentos e fechamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/promotion',
    objective: 'Acompanhar o fechamento escolar e verificar se resultados finais estão coerentes antes da consolidação institucional.',
    intro: 'O Livro de Promoção concentra resultados finais e exige atenção à integridade dos dados que o alimentam. A direção deve tratá-lo como etapa de conferência formal, não como ponto inicial de correção.',
    before: ['Confirme que notas, frequência e demais registros do período foram revisados.', 'Saiba qual etapa ou turma está sendo fechada.'],
    steps: [
      { title: 'Abra Livro de Promoção', text: 'Selecione a turma e o ano letivo corretos.' },
      { title: 'Revise os resultados', text: 'Observe situações finais e identifique inconsistências aparentes.' },
      { title: 'Volte à origem se necessário', text: 'Problemas devem ser corrigidos no dado de origem antes de nova consolidação.' },
      { title: 'Confirme casos excepcionais', text: 'Situações de dependência, transferência ou outros percursos especiais exigem verificação adicional.' },
      { title: 'Conclua somente com coerência', text: 'Considere a turma pronta quando os resultados fizerem sentido com os registros oficiais.' }
    ],
    observe: ['Turma e ano', 'Situação final', 'Casos excepcionais', 'Coerência com boletim e frequência'],
    bestPractices: ['Faça conferência antes da emissão definitiva.', 'Use checklist por turma.', 'Mantenha evidência das correções realizadas.'],
    attention: ['Fechamento incorreto pode repercutir em histórico e documentos oficiais.'],
    doneWhen: ['Você conferiu a turma completa.', 'Casos excepcionais foram revisados e os dados de origem estão coerentes.']
  },
  {
    slug: 'declaracoes',
    title: 'Declarações Escolares: emissão e responsabilidade',
    category: 'Documentos e fechamento',
    estimatedTime: '8 min',
    systemRoute: '/admin/declaracoes',
    objective: 'Emitir e conferir declarações escolares verificáveis com atenção aos dados que sustentam o documento.',
    intro: 'Uma declaração oficial representa a escola. Antes de emitir, a direção deve ter certeza de que matrícula, frequência ou outra informação declarada está correta no sistema.',
    before: ['Localize o estudante correto.', 'Confirme qual tipo de declaração é necessário.'],
    steps: [
      { title: 'Abra Declarações Escolares', text: 'Escolha o tipo de documento e localize o estudante.' },
      { title: 'Confira os dados de origem', text: 'Revise nome, matrícula, escola, turma e a informação específica que será declarada.' },
      { title: 'Gere o documento', text: 'Use o fluxo oficial do sistema e aguarde a geração completa.' },
      { title: 'Revise o PDF', text: 'Antes de entregar, confira texto, datas, identificação e elementos de verificação.' },
      { title: 'Valide quando necessário', text: 'Use o verificador institucional para confirmar o código ou QR do documento.' }
    ],
    observe: ['Nome e matrícula', 'Escola/turma', 'Data', 'Conteúdo declarado', 'Código/QR de verificação'],
    bestPractices: ['Nunca corrija manualmente um PDF oficial fora do sistema.', 'Revise dados antes de emitir.', 'Use sempre a versão mais recente gerada.'],
    attention: ['Documento oficial com dado incorreto deve ser corrigido na fonte e reemitido.'],
    doneWhen: ['Os dados conferem com o sistema.', 'O documento foi emitido e pode ser validado institucionalmente.']
  },
  {
    slug: 'validar-documentos',
    title: 'Validar documentos escolares',
    category: 'Documentos e fechamento',
    estimatedTime: '6 min',
    systemRoute: '/admin/document-validator',
    objective: 'Confirmar autenticidade e integridade de documentos verificáveis emitidos pelo SIGESC.',
    intro: 'A validação protege escola, estudante e terceiros contra uso de documentos alterados ou inválidos. A direção deve saber distinguir um documento emitido pelo sistema de uma cópia cuja autenticidade não foi confirmada.',
    before: ['Tenha o código, token ou QR do documento.', 'Use o documento completo, sem recortes que ocultem os elementos de verificação.'],
    steps: [
      { title: 'Abra Validar Documentos', text: 'Use a ferramenta interna de validação.' },
      { title: 'Informe o identificador', text: 'Digite ou consulte o código/token conforme apresentado no documento.' },
      { title: 'Compare os dados', text: 'Confirme se estudante, tipo de documento e demais informações retornadas correspondem ao arquivo apresentado.' },
      { title: 'Observe o status', text: 'Considere válido somente quando o sistema reconhecer o documento e os dados coincidirem.' },
      { title: 'Não aceite divergência silenciosamente', text: 'Se o documento não validar, encaminhe para conferência antes de qualquer uso institucional.' }
    ],
    observe: ['Status de validação', 'Identificador', 'Tipo de documento', 'Dados exibidos'],
    bestPractices: ['Valide documentos recebidos quando houver dúvida.', 'Compare conteúdo, não apenas a existência de um QR.'],
    attention: ['Um QR visualmente presente não garante autenticidade; a confirmação precisa ocorrer no verificador.'],
    doneWhen: ['Você confirmou o status no sistema.', 'Os dados do verificador correspondem ao documento apresentado.']
  },
  {
    slug: 'ranking-gestao',
    title: 'Ranking de Gestão: leitura responsável',
    category: 'Monitoramento e decisão',
    estimatedTime: '8 min',
    systemRoute: '/admin/ranking-gestores',
    objective: 'Interpretar indicadores comparativos como ferramenta de gestão e aprendizagem, sem reduzir a escola a uma posição isolada.',
    intro: 'Ranking deve abrir perguntas, não encerrar julgamentos. Para a direção, o valor está em entender quais indicadores puxam o resultado, comparar evolução e transformar diferenças em ações concretas.',
    before: ['Confirme período e unidade analisada.', 'Saiba quais indicadores compõem a leitura.'],
    steps: [
      { title: 'Abra Ranking de Gestão', text: 'Leia primeiro os indicadores que compõem a posição apresentada.' },
      { title: 'Observe tendência', text: 'Compare evolução no tempo quando houver dados disponíveis.' },
      { title: 'Volte às evidências', text: 'Se um indicador chama atenção, consulte diário, frequência, cobertura ou outro módulo de origem.' },
      { title: 'Compare processos', text: 'Procure práticas que expliquem melhora ou dificuldade em vez de comparar apenas pessoas.' },
      { title: 'Defina uma pergunta de gestão', text: 'Transforme o resultado em uma questão verificável e, se necessário, em um plano de ação.' }
    ],
    observe: ['Indicador', 'Período', 'Tendência', 'Evidência de origem', 'Contexto da escola'],
    bestPractices: ['Compare evolução e processos.', 'Use resultados para compartilhar boas práticas.', 'Evite exposição ou constrangimento.'],
    attention: ['Ranking não é diagnóstico completo da qualidade da escola.', 'Contexto precisa ser considerado antes de qualquer conclusão.'],
    doneWhen: ['Você consegue explicar o que o indicador mede.', 'Você definiu uma ação ou pergunta baseada em evidência, não apenas na posição.']
  },
  {
    slug: 'fechamento-gerencial',
    title: 'Checklist gerencial de fechamento da escola',
    category: 'Monitoramento e decisão',
    estimatedTime: '12 min',
    systemRoute: '/dashboard',
    objective: 'Consolidar uma rotina de fechamento que conecte diário, frequência, currículo, documentos, resultados e ações pendentes.',
    intro: 'O fechamento não deveria começar no último dia do período. A direção reduz retrabalho quando acompanha pendências ao longo do tempo e usa um checklist final para confirmar que os principais processos estão coerentes.',
    before: ['Defina o período que será fechado.', 'Tenha acesso aos módulos de acompanhamento da escola.'],
    steps: [
      { title: 'Comece pelos diários', text: 'Confirme se as turmas estão com frequência e registros pedagógicos atualizados.' },
      { title: 'Revise frequência e casos críticos', text: 'Garanta que ausências relevantes, justificativas e encaminhamentos estejam compreendidos.' },
      { title: 'Verifique currículo e intervenções', text: 'Consulte cobertura, pendências e planos de ação que impactem o encerramento.' },
      { title: 'Confira resultados consolidados', text: 'Revise boletins e Livro de Promoção no período correto.' },
      { title: 'Cheque documentos e dados institucionais', text: 'Certifique-se de que declarações e outros documentos serão emitidos a partir de dados coerentes.' },
      { title: 'Revise pendências administrativas', text: 'Observe pré-matrículas, RH ou outros itens da escola que precisem de encaminhamento antes da virada de período.' },
      { title: 'Registre o que fica para acompanhamento', text: 'Nem todo problema termina no fechamento. Deixe responsável, prazo e evidência esperada para o período seguinte.' }
    ],
    observe: ['Diários completos', 'Frequência crítica', 'Cobertura', 'Intervenções', 'Boletins', 'Livro de Promoção', 'Documentos', 'Pendências administrativas'],
    bestPractices: ['Use checklist por período.', 'Distribua responsabilidades antes da data limite.', 'Revise pendências durante o período, não apenas no final.'],
    attention: ['Fechar uma etapa não significa apagar pendências históricas; situações não resolvidas devem permanecer rastreáveis.'],
    doneWhen: ['Os principais módulos foram revisados.', 'Pendências remanescentes possuem responsável, prazo e próximo passo.']
  }
];

export const directorTutorialBySlug = Object.fromEntries(
  directorTutorials.map((tutorial) => [tutorial.slug, tutorial])
);

export const directorTutorialCategories = [
  'Comece aqui',
  'Acompanhamento pedagógico',
  'Gestão escolar e intervenção',
  'Documentos e fechamento',
  'Monitoramento e decisão'
];
