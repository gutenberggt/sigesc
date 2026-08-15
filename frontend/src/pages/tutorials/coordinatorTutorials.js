export const coordinatorTutorials = [
  {
    slug: 'primeiros-passos',
    title: 'Primeiros passos e painel do coordenador',
    category: 'Comece aqui',
    estimatedTime: '6 min',
    systemRoute: '/dashboard',
    objective: 'Entender o papel do coordenador no SIGESC, localizar as áreas pedagógicas e saber por onde começar a rotina de acompanhamento.',
    intro: 'O coordenador usa o SIGESC principalmente para acompanhar, comparar, identificar pendências e orientar intervenções. Algumas ações podem ser somente de leitura, conforme as permissões definidas pela rede.',
    before: [
      'Tenha seu usuário e senha do SIGESC.',
      'Confirme que seu perfil ativo é Coordenador(a) ou Apoio Pedagógico.',
      'Saiba qual escola deve aparecer vinculada ao seu acesso.'
    ],
    steps: [
      { title: 'Entre no SIGESC', text: 'Faça login e acesse o Dashboard. Antes de abrir qualquer módulo, confira seu nome, perfil ativo e escola vinculada.' },
      { title: 'Reconheça as áreas do menu', text: 'Procure especialmente Gestão Pedagógica, Monitoramento e Análise e os itens de currículo/intervenção. Esses blocos concentram a rotina da coordenação.' },
      { title: 'Use a busca do menu', text: 'Quando não localizar um recurso, digite parte do nome, como “frequência”, “diário”, “cobertura” ou “intervenções”.' },
      { title: 'Comece pelo acompanhamento, não pela edição', text: 'Abra primeiro Acompanhamento de Diários, Frequência e Notas para entender o cenário antes de orientar qualquer correção.' },
      { title: 'Respeite a permissão exibida', text: 'Se um botão de edição não aparecer, trate o módulo como consulta. O SIGESC pode aplicar permissões específicas por rede e por perfil.' }
    ],
    observe: ['Perfil ativo correto', 'Escola correta', 'Ano letivo correto', 'Menus pedagógicos disponíveis'],
    bestPractices: ['Faça uma leitura geral do painel antes de cobrar lançamentos.', 'Use os dados do sistema como evidência para conversas pedagógicas.', 'Evite compartilhar credenciais ou usar o perfil de outro servidor.'],
    attention: ['O coordenador é predominantemente um perfil de acompanhamento; nem todo recurso visível permite edição.', 'A matriz de permissões da rede pode alterar a visibilidade de alguns itens.'],
    doneWhen: ['Você consegue localizar Frequência, Notas, Registro de Conteúdos e Acompanhamento de Diários.', 'Você sabe confirmar escola, ano letivo e perfil antes de analisar dados.']
  },
  {
    slug: 'turmas-estudantes',
    title: 'Turmas e estudantes: visão pedagógica',
    category: 'Comece aqui',
    estimatedTime: '7 min',
    systemRoute: '/admin/classes',
    objective: 'Localizar turmas e estudantes e usar essas informações como ponto de partida para o acompanhamento pedagógico.',
    intro: 'Antes de analisar notas ou frequência, confirme qual turma, série e estudante você está acompanhando. Uma análise correta começa pelo recorte correto.',
    before: ['Confirme escola e ano letivo.', 'Tenha em mente a turma ou o estudante que deseja acompanhar.'],
    steps: [
      { title: 'Abra Turmas', text: 'Acesse a área de turmas e identifique nome, etapa/série, turno e ano letivo.' },
      { title: 'Escolha uma turma', text: 'Confirme se é a turma esperada antes de prosseguir para outros módulos. Turmas com nomes parecidos podem pertencer a turnos ou anos diferentes.' },
      { title: 'Consulte os estudantes', text: 'Use a área de estudantes para localizar um estudante e conferir sua turma atual. Prefira a busca por nome e os filtros da escola.' },
      { title: 'Relacione o estudante à análise', text: 'Ao investigar nota, falta ou intervenção, volte a confirmar turma e vínculo do estudante para evitar conclusões sobre uma matrícula antiga.' },
      { title: 'Registre a pergunta pedagógica', text: 'Antes de abrir outro módulo, formule o que deseja responder: “A turma está com frequência baixa?”, “Há notas pendentes?”, “O conteúdo previsto foi registrado?”.' }
    ],
    observe: ['Turma correta', 'Turno', 'Série/etapa', 'Ano letivo', 'Vínculo atual do estudante'],
    bestPractices: ['Sempre trabalhe com um recorte claro: escola → turma → período → estudante, quando necessário.', 'Use o cadastro para contextualizar, não para substituir a leitura do diário.'],
    attention: ['Histórico escolar e movimentações podem ter permissões diferentes do acesso à lista de estudantes.'],
    doneWhen: ['Você consegue localizar a turma e os estudantes corretos.', 'Você consegue definir o recorte da análise antes de abrir frequência, notas ou conteúdo.']
  },
  {
    slug: 'acompanhamento-diarios',
    title: 'Acompanhamento dos Diários de Classe',
    category: 'Rotina pedagógica',
    estimatedTime: '10 min',
    systemRoute: '/admin/diary-dashboard',
    objective: 'Acompanhar o preenchimento dos diários e localizar rapidamente turmas, períodos ou professores que precisam de atenção.',
    intro: 'Este deve ser um dos painéis mais frequentes na rotina da coordenação. Ele ajuda a trocar a pergunta “quem ainda não lançou?” por uma leitura objetiva das pendências.',
    before: ['Defina o período que deseja acompanhar.', 'Tenha claro se a análise é geral ou de uma turma específica.'],
    steps: [
      { title: 'Abra Acompanhamento de Diários', text: 'No Dashboard, acesse o painel de acompanhamento e confirme escola e período.' },
      { title: 'Leia os indicadores gerais', text: 'Observe primeiro o panorama: turmas acompanhadas, registros existentes e sinais de pendência. Não comece pelo caso individual.' },
      { title: 'Desça para o detalhe', text: 'Filtre ou localize a turma que merece atenção e identifique qual dimensão está incompleta: frequência, conteúdo, notas ou outro registro do diário.' },
      { title: 'Separe atraso de problema pedagógico', text: 'Um lançamento ausente é diferente de um dado preocupante já lançado. Registre qual dos dois casos você encontrou.' },
      { title: 'Converse com evidência', text: 'Ao orientar o professor, informe turma, período e tipo de pendência. Evite cobranças genéricas.' },
      { title: 'Volte para conferir', text: 'Depois da orientação, consulte novamente o painel para verificar se a pendência foi resolvida.' }
    ],
    observe: ['Período analisado', 'Turmas com pendências', 'Dimensão pendente', 'Recorrência do problema'],
    bestPractices: ['Crie uma rotina semanal de acompanhamento.', 'Priorize pendências que afetam fechamento, frequência e comunicação com famílias.', 'Use o painel para orientar e depois verificar o retorno.'],
    attention: ['O painel mostra evidências do sistema; a causa da pendência ainda precisa ser compreendida com o professor quando necessário.'],
    doneWhen: ['Você identifica quais turmas exigem atenção e por qual motivo.', 'Você consegue transformar a pendência em uma orientação específica.']
  },
  {
    slug: 'frequencia',
    title: 'Frequência: análise por turma e estudante',
    category: 'Rotina pedagógica',
    estimatedTime: '9 min',
    systemRoute: '/admin/attendance',
    objective: 'Interpretar a frequência da turma e localizar estudantes com padrão de ausência que exige acompanhamento.',
    intro: 'A frequência não deve ser lida apenas como um percentual. Para a coordenação, o mais importante é identificar padrões, mudanças e situações que exigem contato ou intervenção.',
    before: ['Selecione escola, turma e período corretos.', 'Se estiver investigando um estudante, confirme a matrícula atual.'],
    steps: [
      { title: 'Abra Frequência', text: 'Acesse o módulo de frequência e escolha o recorte correto de escola, turma e período.' },
      { title: 'Leia a turma primeiro', text: 'Observe o padrão geral antes de analisar um estudante. Isso ajuda a distinguir um problema individual de uma ocorrência da turma ou do calendário.' },
      { title: 'Localize ausências recorrentes', text: 'Procure estudantes com faltas repetidas, sequência de ausências ou queda recente de presença.' },
      { title: 'Considere justificativas', text: 'Quando houver atestado ou justificativa visível, leia o registro antes de interpretar a ausência como falta de acompanhamento familiar.' },
      { title: 'Cruze com outras evidências', text: 'Compare frequência com notas, participação e intervenções. Uma queda simultânea em vários indicadores merece prioridade.' },
      { title: 'Defina a ação pedagógica', text: 'Registre o que precisa acontecer: conversar com professor, acionar família, encaminhar busca ativa conforme protocolo da rede ou acompanhar por novo período.' }
    ],
    observe: ['Percentual de frequência', 'Sequência de faltas', 'Mudança recente', 'Justificativas/atestados', 'Relação com desempenho'],
    bestPractices: ['Analise tendência, não apenas um número isolado.', 'Priorize mudanças abruptas e faltas sequenciais.', 'Documente a ação tomada e volte a acompanhar.'],
    attention: ['A existência de justificativa não elimina a necessidade de acompanhar a aprendizagem perdida.', 'Não altere presença para “corrigir” um indicador; qualquer ajuste deve refletir a realidade e seguir o fluxo autorizado.'],
    doneWhen: ['Você consegue apontar quais estudantes exigem acompanhamento e por quê.', 'Você definiu uma próxima ação baseada em evidências.']
  },
  {
    slug: 'notas',
    title: 'Notas: lançamentos, pendências e sinais de aprendizagem',
    category: 'Rotina pedagógica',
    estimatedTime: '9 min',
    systemRoute: '/admin/grades',
    objective: 'Acompanhar se as notas foram lançadas e interpretar resultados que indiquem necessidade de apoio pedagógico.',
    intro: 'O coordenador precisa distinguir duas situações: nota ainda não lançada e nota lançada que revela dificuldade de aprendizagem. Cada uma exige uma ação diferente.',
    before: ['Confirme turma, componente e bimestre/período.', 'Evite comparar turmas sem considerar etapa e contexto.'],
    steps: [
      { title: 'Abra Notas', text: 'Selecione o recorte de turma, componente curricular e período.' },
      { title: 'Procure lacunas de lançamento', text: 'Identifique campos sem nota ou situações em que o registro ainda não foi concluído.' },
      { title: 'Leia a distribuição dos resultados', text: 'Observe se a dificuldade está concentrada em poucos estudantes ou aparece em grande parte da turma.' },
      { title: 'Cruze com frequência e conteúdo', text: 'Antes de concluir que há dificuldade de aprendizagem, verifique frequência e o que foi registrado como conteúdo trabalhado.' },
      { title: 'Transforme o dado em pergunta pedagógica', text: 'Exemplo: “Por que grande parte da turma teve dificuldade neste objetivo?” é mais útil do que apenas “as notas estão baixas”.' },
      { title: 'Acompanhe a resposta', text: 'Após a orientação ou intervenção, observe os registros seguintes para verificar se houve mudança.' }
    ],
    observe: ['Notas ausentes', 'Concentração de resultados baixos', 'Diferenças entre componentes', 'Relação com frequência', 'Evolução entre períodos'],
    bestPractices: ['Use notas como evidência de aprendizagem, não como fim em si mesmas.', 'Converse com o professor sobre objetivos e evidências da avaliação.', 'Compare o estudante com sua própria evolução antes de fazer comparações simplistas.'],
    attention: ['Campos vazios podem significar pendência de lançamento, não nota zero.', 'Evite interpretar resultado sem considerar o período e o componente corretos.'],
    doneWhen: ['Você distingue pendência de lançamento de dificuldade de aprendizagem.', 'Você consegue indicar uma pergunta pedagógica objetiva para orientar o acompanhamento.']
  },
  {
    slug: 'registro-conteudos',
    title: 'Registro de Conteúdos: o que foi trabalhado',
    category: 'Rotina pedagógica',
    estimatedTime: '8 min',
    systemRoute: '/admin/learning-objects',
    objective: 'Acompanhar os registros de conteúdos/objetos de conhecimento e verificar a continuidade do trabalho pedagógico.',
    intro: 'O registro de conteúdo ajuda a coordenação a compreender o percurso real da turma. Ele não deve ser analisado isoladamente: serve para relacionar planejamento, aula realizada e aprendizagem observada.',
    before: ['Escolha escola, turma, componente e período.', 'Tenha uma pergunta clara sobre continuidade ou cobertura.'],
    steps: [
      { title: 'Abra Registro de Conteúdos', text: 'Selecione a turma e o componente curricular que deseja acompanhar.' },
      { title: 'Observe a sequência', text: 'Verifique se os registros mostram continuidade ao longo dos dias letivos ou se existem períodos extensos sem informação.' },
      { title: 'Leia a descrição pedagógica', text: 'Avalie se o registro permite compreender o que foi efetivamente trabalhado, e não apenas um título genérico.' },
      { title: 'Relacione ao calendário', text: 'Considere dias letivos, eventos e interrupções antes de concluir que há falha de registro.' },
      { title: 'Use a Cobertura Curricular quando necessário', text: 'Se a pergunta for “quanto do currículo previsto já foi trabalhado?”, avance para o tutorial de Cobertura Curricular.' }
    ],
    observe: ['Regularidade dos registros', 'Clareza das descrições', 'Sequência pedagógica', 'Períodos sem registro', 'Relação com o calendário'],
    bestPractices: ['Avalie qualidade e continuidade, não apenas quantidade de registros.', 'Use exemplos específicos ao orientar melhoria de registro.'],
    attention: ['Um registro curto não é necessariamente ruim; o critério é se ele documenta adequadamente o trabalho realizado.'],
    doneWhen: ['Você consegue reconstruir a sequência do trabalho pedagógico da turma.', 'Você sabe quando usar Cobertura Curricular para uma análise mais ampla.']
  },
  {
    slug: 'adaptacoes-curriculares',
    title: 'Adaptações Curriculares: planejar apoios pedagógicos',
    category: 'Currículo e intervenção',
    estimatedTime: '11 min',
    systemRoute: '/admin/curriculo/adaptacoes',
    objective: 'Entender como registrar e acompanhar adaptações curriculares sem descaracterizar os objetivos de aprendizagem.',
    intro: 'Adaptação curricular é uma decisão pedagógica intencional. O foco deve ser remover barreiras, tornar o currículo acessível e explicitar como o estudante participará e demonstrará aprendizagem.',
    before: ['Tenha evidências das barreiras observadas.', 'Conheça o objetivo de aprendizagem que precisa ser acessado.', 'Evite começar pela deficiência ou pelo diagnóstico; comece pela necessidade pedagógica.'],
    steps: [
      { title: 'Abra Adaptações Curriculares', text: 'Acesse o módulo e selecione o contexto disponível: etapa, componente, turma ou estudante, conforme a configuração apresentada.' },
      { title: 'Defina a barreira', text: 'Descreva o que impede ou dificulta a participação/aprendizagem de forma observável.' },
      { title: 'Preserve o objetivo', text: 'Antes de adaptar, identifique qual aprendizagem é essencial. A adaptação muda o caminho, recurso, tempo ou forma de resposta quando necessário — não deve reduzir automaticamente a expectativa.' },
      { title: 'Escolha a estratégia', text: 'Registre recurso, apoio, organização, mediação ou forma alternativa de acesso que será usada.' },
      { title: 'Defina como observar o resultado', text: 'Indique que evidência mostrará se a adaptação funcionou e quando será revista.' },
      { title: 'Articule com o professor', text: 'A adaptação precisa chegar à prática da sala comum; use o registro como base para alinhamento, não como documento isolado.' }
    ],
    observe: ['Barreira descrita', 'Objetivo preservado', 'Estratégia concreta', 'Evidência esperada', 'Data/critério de revisão'],
    bestPractices: ['Escreva adaptações executáveis por quem está em sala.', 'Prefira recursos e estratégias vinculados a uma barreira específica.', 'Revise quando a resposta do estudante mudar.'],
    attention: ['Diagnóstico clínico não substitui avaliação pedagógica.', 'Adaptação não significa simplificar tudo nem criar um currículo paralelo por padrão.'],
    doneWhen: ['A adaptação explica barreira, objetivo, estratégia e evidência.', 'O professor consegue entender o que fazer na prática.']
  },
  {
    slug: 'cobertura-curricular',
    title: 'Cobertura Curricular: previsto x realizado',
    category: 'Currículo e intervenção',
    estimatedTime: '9 min',
    systemRoute: '/admin/curriculo/cobertura',
    objective: 'Acompanhar a cobertura do currículo e identificar componentes, turmas ou períodos que precisam de atenção.',
    intro: 'Cobertura curricular responde a uma pergunta diferente de “há conteúdo lançado?”. Ela ajuda a verificar quanto do percurso previsto está sendo alcançado e onde existem lacunas.',
    before: ['Confirme etapa, turma, componente e período.', 'Considere o calendário letivo e o ritmo esperado para o período.'],
    steps: [
      { title: 'Abra Cobertura Curricular', text: 'Selecione o recorte que deseja analisar e observe o panorama antes do detalhe.' },
      { title: 'Identifique lacunas', text: 'Procure habilidades/objetos ainda não cobertos ou cobertura muito inferior ao esperado para o momento do ano.' },
      { title: 'Evite conclusão automática', text: 'Cobertura baixa pode vir de atraso de registro, reorganização do calendário, necessidade de retomada ou dificuldade real de execução.' },
      { title: 'Cruze com Registro de Conteúdos', text: 'Confira se os registros diários sustentam o indicador de cobertura.' },
      { title: 'Defina prioridade', text: 'Priorize lacunas essenciais, turmas em risco e situações recorrentes.' },
      { title: 'Acompanhe após a orientação', text: 'Volte ao painel depois do prazo combinado para verificar evolução.' }
    ],
    observe: ['Percentual/nível de cobertura', 'Habilidades ainda não trabalhadas', 'Diferenças entre turmas', 'Coerência com registros diários'],
    bestPractices: ['Use a cobertura para planejar apoio, não para criar corrida de conteúdos.', 'Discuta profundidade e aprendizagem, além da quantidade coberta.'],
    attention: ['Cobrir mais rápido não significa ensinar melhor.', 'A ausência de registro pode afetar a leitura do indicador.'],
    doneWhen: ['Você identifica as lacunas prioritárias.', 'Você consegue explicar se a situação parece ser registro, calendário ou execução pedagógica.']
  },
  {
    slug: 'calendario-diario',
    title: 'Calendário do Diário: dias letivos e consistência',
    category: 'Rotina pedagógica',
    estimatedTime: '7 min',
    systemRoute: '/admin/diary-calendar',
    objective: 'Usar o calendário operacional do diário para compreender dias letivos, períodos e possíveis lacunas de registro.',
    intro: 'Antes de tratar uma data sem lançamento como pendência, confirme se aquele dia realmente deveria ter aula para a turma. O calendário evita cobranças baseadas em datas incorretas.',
    before: ['Confirme ano letivo e escola.', 'Tenha em mente a turma ou período que deseja verificar.'],
    steps: [
      { title: 'Abra Calendário do Diário', text: 'Acesse o calendário operacional e navegue até o período desejado.' },
      { title: 'Identifique dias letivos', text: 'Observe dias previstos para atividade escolar e possíveis exceções do calendário.' },
      { title: 'Compare com o diário', text: 'Ao encontrar uma lacuna em frequência ou conteúdo, verifique se a data deveria mesmo ter registro.' },
      { title: 'Observe padrões', text: 'Várias lacunas em dias letivos consecutivos merecem investigação; uma data isolada pode ter justificativa no calendário.' },
      { title: 'Use a data correta na orientação', text: 'Ao conversar com o professor, cite exatamente o período ou as datas que precisam ser conferidas.' }
    ],
    observe: ['Dias letivos', 'Exceções', 'Períodos sem registro', 'Coerência entre calendário e diário'],
    bestPractices: ['Confira o calendário antes de apontar pendência por data.', 'Use datas concretas nas orientações.'],
    attention: ['Calendário escolar geral e calendário operacional do diário cumprem funções diferentes.'],
    doneWhen: ['Você sabe se a data analisada exigia registro.', 'Você consegue relacionar a lacuna do diário ao calendário.']
  },
  {
    slug: 'integridade-grade',
    title: 'Integridade da Grade Horária',
    category: 'Rotina pedagógica',
    estimatedTime: '8 min',
    systemRoute: '/admin/grade-integrity',
    objective: 'Identificar inconsistências de grade que podem afetar diário, frequência, conteúdo e acompanhamento pedagógico.',
    intro: 'Algumas “pendências do professor” podem ter origem na configuração da grade. Antes de insistir em uma correção de lançamento, verifique se a estrutura que sustenta o diário está consistente.',
    before: ['Tenha a turma e o período do problema.', 'Anote o sintoma observado: aula ausente, componente inesperado, conflito de horário ou outro.'],
    steps: [
      { title: 'Abra Integridade da Grade', text: 'Selecione o contexto da escola/turma que apresenta inconsistência.' },
      { title: 'Leia os alertas', text: 'Observe conflitos, lacunas ou configurações que o painel indicar.' },
      { title: 'Relacione ao sintoma', text: 'Pergunte se a inconsistência encontrada explica o problema visto no diário ou na frequência.' },
      { title: 'Não corrija fora da sua competência', text: 'Se a solução exigir alteração administrativa de turma, vínculo ou grade, encaminhe para o perfil responsável.' },
      { title: 'Confirme depois da correção', text: 'Após o ajuste pela equipe autorizada, retorne ao diário e verifique se o comportamento esperado foi restabelecido.' }
    ],
    observe: ['Conflitos', 'Lacunas', 'Componente/turma afetado', 'Relação com o diário'],
    bestPractices: ['Diagnostique a estrutura antes de atribuir o problema ao usuário.', 'Encaminhe com evidência: turma, componente, data e alerta encontrado.'],
    attention: ['O coordenador pode visualizar o problema sem necessariamente ter permissão para alterar a grade.'],
    doneWhen: ['Você consegue explicar se o problema é pedagógico ou estrutural.', 'Você sabe para quem encaminhar uma correção administrativa.']
  },
  {
    slug: 'intervencoes',
    title: 'Intervenções Necessárias: priorizar quem precisa de atenção',
    category: 'Currículo e intervenção',
    estimatedTime: '10 min',
    systemRoute: '/admin/intervencoes',
    objective: 'Usar o feed de intervenções para priorizar situações pedagógicas e transformar alertas em ações acompanháveis.',
    intro: 'O feed de intervenções ajuda a coordenação a organizar prioridade. O alerta é o início da análise, não a conclusão: ele precisa ser contextualizado com frequência, notas, conteúdo e histórico recente.',
    before: ['Defina o período de acompanhamento.', 'Esteja preparado para cruzar informações de outros módulos.'],
    steps: [
      { title: 'Abra Intervenções Necessárias', text: 'Observe primeiro quais situações aparecem como prioritárias.' },
      { title: 'Leia o motivo do alerta', text: 'Identifique qual indicador ou combinação de sinais levou o caso a aparecer.' },
      { title: 'Confirme em outras fontes', text: 'Abra frequência, notas e/ou registros de conteúdo para verificar se a evidência é coerente.' },
      { title: 'Classifique a urgência', text: 'Dê prioridade a situações com múltiplos sinais, piora recente ou impacto direto na permanência e aprendizagem.' },
      { title: 'Defina ação e responsável', text: 'Transforme o alerta em uma ação concreta com responsável e momento de revisão.' },
      { title: 'Reavalie', text: 'A intervenção só termina quando você verifica se houve resposta e decide manter, ajustar ou encerrar a ação.' }
    ],
    observe: ['Motivo do alerta', 'Quantidade de sinais', 'Recência', 'Evidências confirmatórias', 'Resposta após intervenção'],
    bestPractices: ['Use o alerta para priorizar, não para rotular.', 'Documente o que será feito e quando será revisto.', 'Converse com o professor antes de concluir causas pedagógicas.'],
    attention: ['Um alerta automatizado não substitui análise profissional.', 'Evite expor informações sensíveis em comunicações desnecessárias.'],
    doneWhen: ['Cada caso prioritário tem uma ação concreta.', 'Você sabe quando voltará a verificar o resultado.']
  },
  {
    slug: 'plano-acao',
    title: 'Plano de Ação: transformar diagnóstico em acompanhamento',
    category: 'Currículo e intervenção',
    estimatedTime: '11 min',
    systemRoute: '/admin/plano-acao',
    objective: 'Converter problemas identificados em ações com foco, responsáveis, evidências e revisão.',
    intro: 'Um bom plano de ação não é uma lista de intenções. Ele deve dizer o que será feito, por quem, para resolver qual evidência e como a coordenação saberá se houve avanço.',
    before: ['Tenha um diagnóstico sustentado por dados.', 'Evite criar plano para problema ainda não compreendido.'],
    steps: [
      { title: 'Defina o problema', text: 'Escreva o problema de forma observável. Ex.: “3 turmas estão com cobertura de leitura abaixo do esperado no período”, e não “melhorar português”.' },
      { title: 'Escolha uma prioridade', text: 'Evite planos enormes. Comece pelo que tem maior impacto e pode ser acompanhado.' },
      { title: 'Defina a ação', text: 'Descreva o que realmente será feito: reunião de planejamento, sequência de retomada, acompanhamento de registros, intervenção com grupo de estudantes etc.' },
      { title: 'Defina responsável e prazo', text: 'Toda ação precisa de alguém responsável e de um momento para revisão.' },
      { title: 'Escolha a evidência', text: 'Defina qual dado mostrará avanço: frequência, cobertura, resultados de avaliação, conclusão de registros ou outra evidência pertinente.' },
      { title: 'Revise o plano', text: 'No prazo combinado, compare a evidência inicial com a nova situação e ajuste a estratégia quando necessário.' }
    ],
    observe: ['Problema específico', 'Ação executável', 'Responsável', 'Prazo', 'Evidência de sucesso'],
    bestPractices: ['Use poucos indicadores realmente ligados ao problema.', 'Prefira ciclos curtos de revisão.', 'Registre decisões para manter continuidade entre reuniões.'],
    attention: ['Plano sem responsável ou sem evidência de sucesso tende a virar apenas registro burocrático.'],
    doneWhen: ['É possível responder o que será feito, por quem, até quando e como será avaliado.', 'A próxima revisão já está definida.']
  },
  {
    slug: 'atestados-justificativas',
    title: 'Atestados e justificativas de ausência',
    category: 'Rotina pedagógica',
    estimatedTime: '7 min',
    systemRoute: '/admin/students',
    objective: 'Consultar justificativas/atestados disponíveis e interpretar corretamente sua relação com frequência e aprendizagem.',
    intro: 'O atestado explica uma ausência, mas não repõe automaticamente a aprendizagem perdida. Para a coordenação, ele serve para contextualizar a frequência e planejar apoio quando necessário.',
    before: ['Localize o estudante correto.', 'Confirme o período da ausência.'],
    steps: [
      { title: 'Localize o estudante', text: 'Use a busca de estudantes e confirme nome, turma e matrícula atual.' },
      { title: 'Consulte os registros disponíveis', text: 'Quando o perfil e a tela disponibilizarem atestados/justificativas, confira período e informações do registro.' },
      { title: 'Compare com a frequência', text: 'Abra o módulo de frequência e verifique se as datas analisadas correspondem ao período justificado.' },
      { title: 'Separe justificativa de aprendizagem', text: 'Mesmo com ausência justificada, avalie se o estudante precisa recuperar atividades, orientações ou objetivos trabalhados.' },
      { title: 'Preserve a privacidade', text: 'Use somente as informações necessárias para a decisão pedagógica. Não reproduza dados de saúde em mensagens ou relatórios sem necessidade.' }
    ],
    observe: ['Período do registro', 'Correspondência com as faltas', 'Necessidade de recuperação pedagógica'],
    bestPractices: ['Use o mínimo necessário de informação de saúde.', 'Planeje continuidade da aprendizagem após ausências prolongadas.'],
    attention: ['A disponibilidade de detalhes de atestado depende das permissões do perfil e da rede.', 'Justificar ausência não significa alterar registros de presença sem respaldo no fluxo do sistema.'],
    doneWhen: ['Você contextualizou as ausências sem expor dados desnecessários.', 'Você avaliou se há necessidade de apoio pedagógico.']
  },
  {
    slug: 'boletins',
    title: 'Boletim Online: conferência pedagógica dos resultados',
    category: 'Fechamento e evidências',
    estimatedTime: '8 min',
    systemRoute: '/admin/bulletins',
    objective: 'Conferir como notas e resultados aparecem no boletim antes de reuniões, fechamento ou comunicação com famílias.',
    intro: 'O boletim é uma visão consolidada. Se algo parece errado nele, a coordenação deve rastrear a origem no lançamento de notas, frequência, matrícula ou configuração correspondente — e não “corrigir o boletim” diretamente.',
    before: ['Confirme estudante, turma e período.', 'Tenha os lançamentos de origem disponíveis para comparação quando necessário.'],
    steps: [
      { title: 'Abra Boletim Online', text: 'Localize o estudante ou a turma e selecione o período correspondente.' },
      { title: 'Confira os componentes', text: 'Observe se os componentes e resultados exibidos correspondem ao contexto da turma.' },
      { title: 'Compare com Notas', text: 'Quando houver divergência aparente, confira o módulo de Notas para localizar a origem.' },
      { title: 'Observe a leitura pedagógica', text: 'Identifique componentes com maior dificuldade, evolução entre períodos e possíveis combinações com baixa frequência.' },
      { title: 'Prepare a conversa', text: 'Use o boletim como síntese para reunião com professor, estudante ou família, sempre contextualizando o resultado.' }
    ],
    observe: ['Componentes', 'Resultados por período', 'Evolução', 'Coerência com lançamentos'],
    bestPractices: ['Verifique a origem do dado antes de solicitar correção.', 'Apresente evolução e próximos passos, não apenas médias.'],
    attention: ['O boletim é consequência dos registros de origem.', 'Evite interpretar resultado final sem considerar frequência, avaliações e intervenções.'],
    doneWhen: ['Você consegue explicar de onde vem o resultado exibido.', 'Você identificou os pontos que merecem acompanhamento pedagógico.']
  },
  {
    slug: 'livro-promocao',
    title: 'Livro de Promoção: acompanhar o fechamento',
    category: 'Fechamento e evidências',
    estimatedTime: '9 min',
    systemRoute: '/admin/promotion',
    objective: 'Acompanhar o fechamento de resultados e identificar pendências antes da consolidação final.',
    intro: 'O Livro de Promoção é uma etapa de fechamento. A coordenação deve chegar a ele depois de acompanhar notas, frequência e pendências do diário — não como primeira fonte de correção.',
    before: ['Confirme que o período de fechamento está correto.', 'Revise previamente pendências de notas e frequência.'],
    steps: [
      { title: 'Abra Livro de Promoção', text: 'Selecione escola, turma e período/ano conforme os filtros disponíveis.' },
      { title: 'Confira a completude', text: 'Procure estudantes ou componentes com informação ausente ou situação que impeça o fechamento.' },
      { title: 'Rastreie a origem', text: 'Se houver pendência, volte ao módulo correspondente — Notas, Frequência ou Diário — para entender o que falta.' },
      { title: 'Verifique casos excepcionais', text: 'Situações de movimentação, dependência ou outros casos específicos devem ser conferidos com a equipe responsável antes da consolidação.' },
      { title: 'Use como checklist de fechamento', text: 'Acompanhe até que as pendências pedagógicas estejam resolvidas ou devidamente encaminhadas.' }
    ],
    observe: ['Dados ausentes', 'Situações não concluídas', 'Coerência com notas/frequência', 'Casos excepcionais'],
    bestPractices: ['Faça pré-conferência antes do prazo final.', 'Registre responsáveis por cada pendência de fechamento.'],
    attention: ['A permissão para gerar ou alterar documentos finais pode variar por perfil.', 'Não force fechamento quando a origem do dado ainda está inconsistente.'],
    doneWhen: ['As pendências estão resolvidas ou encaminhadas com responsável.', 'Os resultados consolidados são coerentes com os registros de origem.']
  },
  {
    slug: 'diario-aee',
    title: 'Diário AEE: acompanhamento pela coordenação',
    category: 'Currículo e intervenção',
    estimatedTime: '8 min',
    systemRoute: '/admin/diario-aee',
    objective: 'Acompanhar planos e atendimentos do AEE respeitando o caráter pedagógico, a privacidade e as permissões do perfil.',
    intro: 'Para a coordenação, o Diário AEE deve apoiar a articulação entre atendimento especializado e sala comum. O foco é verificar continuidade, objetivos, registros de atendimento e coerência pedagógica.',
    before: ['Confirme escola/polo AEE e ano letivo.', 'Tenha claro qual estudante ou turma AEE deseja acompanhar.'],
    steps: [
      { title: 'Abra Diário AEE', text: 'Selecione escola/polo, ano letivo e turma AEE quando o filtro estiver disponível.' },
      { title: 'Comece pelos Estudantes e Planos', text: 'Verifique se o estudante possui plano e se os objetivos/estratégias estão descritos de forma pedagógica.' },
      { title: 'Leia os Atendimentos', text: 'Observe regularidade, objetivo trabalhado, atividade/estratégia e resposta do estudante.' },
      { title: 'Consulte o Diário Consolidado', text: 'Use o consolidado para perceber frequência de atendimento, carga horária e continuidade.' },
      { title: 'Promova articulação', text: 'Quando necessário, alinhe com professor AEE e professor regente como os apoios dialogam com a sala comum.' }
    ],
    observe: ['Plano existente', 'Objetivos claros', 'Regularidade dos atendimentos', 'Evidências de progresso', 'Articulação com sala comum'],
    bestPractices: ['Foque em barreiras, apoios e aprendizagem.', 'Preserve informações sensíveis.', 'Use o plano como instrumento vivo de acompanhamento.'],
    attention: ['O nível de edição no Diário AEE depende da permissão do perfil.', 'Não reduza a análise pedagógica ao diagnóstico clínico.'],
    doneWhen: ['Você consegue explicar os objetivos atuais do AEE e como estão sendo acompanhados.', 'Você identificou se há necessidade de alinhamento com a sala comum.']
  },
  {
    slug: 'avisos-calendario',
    title: 'Avisos e calendário: comunicação da rotina pedagógica',
    category: 'Fechamento e evidências',
    estimatedTime: '6 min',
    systemRoute: '/avisos',
    objective: 'Usar avisos e calendário para acompanhar prazos, reuniões e eventos que impactam a rotina pedagógica.',
    intro: 'A coordenação trabalha com prazos: fechamento, conselho, avaliações, reuniões e intervenções. Avisos e calendário ajudam a colocar os dados pedagógicos dentro do tempo real da escola.',
    before: ['Confirme a escola e o período atual.', 'Saiba quais prazos pedagógicos estão próximos.'],
    steps: [
      { title: 'Consulte Avisos', text: 'Leia comunicados ativos e identifique os que afetam professores, turmas ou prazos de lançamento.' },
      { title: 'Abra o Calendário', text: 'Consulte eventos e datas que influenciam dias letivos, reuniões ou fechamento.' },
      { title: 'Relacione prazo e pendência', text: 'Uma pendência perto do fechamento exige prioridade maior do que outra com prazo distante.' },
      { title: 'Comunique com contexto', text: 'Ao orientar professores, informe o que precisa ser feito, a turma/período e o prazo relacionado.' },
      { title: 'Evite duplicidade', text: 'Use os canais institucionais disponíveis e não multiplique mensagens contraditórias sobre o mesmo prazo.' }
    ],
    observe: ['Prazos', 'Eventos', 'Impacto em dias letivos', 'Pendências próximas do fechamento'],
    bestPractices: ['Planeje a semana pedagógica olhando calendário e indicadores juntos.', 'Comunique prazos com antecedência e contexto.'],
    attention: ['O calendário geral não substitui o Calendário do Diário para verificar obrigação de registro por data.'],
    doneWhen: ['Você sabe quais prazos impactam as pendências atuais.', 'As orientações aos professores incluem contexto e prazo.']
  },
  {
    slug: 'validar-documentos',
    title: 'Validar documentos escolares e evidências verificáveis',
    category: 'Fechamento e evidências',
    estimatedTime: '6 min',
    systemRoute: '/admin/document-validator',
    objective: 'Conferir a autenticidade de documentos verificáveis emitidos pelo SIGESC quando isso for necessário no acompanhamento escolar.',
    intro: 'A validação serve para confirmar se um documento verificável corresponde a um registro legítimo do SIGESC. Ela não substitui a análise pedagógica do conteúdo do documento.',
    before: ['Tenha o documento, código ou elemento de verificação disponível.', 'Use a validação somente quando houver necessidade real.'],
    steps: [
      { title: 'Abra Validar Documentos', text: 'Acesse o validador interno disponível ao seu perfil.' },
      { title: 'Informe o dado solicitado', text: 'Digite ou utilize o código/identificador de verificação conforme a tela.' },
      { title: 'Confira o resultado', text: 'Verifique se o sistema reconhece o documento e se os dados essenciais correspondem ao que você recebeu.' },
      { title: 'Trate divergência como evidência', text: 'Se houver inconsistência, não edite o documento manualmente. Encaminhe o caso à equipe responsável pela emissão/origem.' }
    ],
    observe: ['Status da validação', 'Correspondência dos dados essenciais', 'Origem do documento'],
    bestPractices: ['Valide antes de usar documento duvidoso em decisão administrativa ou pedagógica.', 'Preserve o código de verificação sem divulgar dados desnecessários.'],
    attention: ['Validação confirma autenticidade/integridade; não confirma que toda interpretação pedagógica do documento está correta.'],
    doneWhen: ['Você sabe se o documento foi reconhecido pelo SIGESC.', 'Qualquer divergência foi encaminhada sem alteração manual do documento.']
  },
  {
    slug: 'indicadores-ranking',
    title: 'Indicadores e Ranking de Gestão: leitura responsável',
    category: 'Fechamento e evidências',
    estimatedTime: '8 min',
    systemRoute: '/admin/ranking-gestores',
    objective: 'Interpretar indicadores comparativos sem transformar ranking em julgamento isolado de pessoas ou escolas.',
    intro: 'Indicadores comparativos podem ajudar a localizar padrões e boas práticas. Para a coordenação, o valor está em formular perguntas e priorizar apoio — não em reduzir a qualidade pedagógica a uma posição no ranking.',
    before: ['Confirme período e unidade analisada.', 'Saiba quais indicadores compõem a leitura apresentada.'],
    steps: [
      { title: 'Abra Ranking de Gestão', text: 'Observe o panorama e identifique quais dimensões influenciam a posição ou indicador exibido.' },
      { title: 'Leia o indicador antes da posição', text: 'Pergunte o que está sendo medido, em qual período e com quais dados.' },
      { title: 'Procure tendência', text: 'Compare evolução ao longo do tempo quando houver dados disponíveis. Uma posição isolada pode esconder melhora importante.' },
      { title: 'Volte à evidência de origem', text: 'Se um indicador chama atenção, consulte diário, frequência, cobertura ou outro módulo que o sustenta.' },
      { title: 'Transforme comparação em aprendizagem', text: 'Use diferenças para identificar práticas que podem ser compartilhadas e situações que precisam de apoio.' }
    ],
    observe: ['Indicador utilizado', 'Período', 'Tendência', 'Evidências de origem', 'Contexto da escola/turma'],
    bestPractices: ['Compare processos e evolução, não apenas posições.', 'Use rankings para orientar apoio e troca de boas práticas.', 'Evite exposição ou constrangimento de profissionais.'],
    attention: ['Ranking não é diagnóstico completo.', 'Diferenças de contexto precisam ser consideradas antes de qualquer conclusão.'],
    doneWhen: ['Você consegue explicar o que o indicador mede.', 'Você definiu uma pergunta ou ação pedagógica a partir da evidência, e não apenas da posição.']
  }
];

export const coordinatorTutorialBySlug = Object.fromEntries(
  coordinatorTutorials.map((tutorial) => [tutorial.slug, tutorial])
);

export const coordinatorTutorialCategories = [
  'Comece aqui',
  'Rotina pedagógica',
  'Currículo e intervenção',
  'Fechamento e evidências'
];
