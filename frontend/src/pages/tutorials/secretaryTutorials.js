export const secretaryTutorials = [
  {
    slug: 'primeiros-passos',
    title: 'Primeiros passos e painel do secretário',
    category: 'Comece aqui',
    estimatedTime: '7 min',
    systemRoute: '/dashboard',
    objective: 'Entender o papel do secretário no SIGESC, conferir escola e perfil ativos e localizar os recursos usados na rotina da secretaria escolar.',
    intro: 'O secretário trabalha no encontro entre cadastro, matrícula, documentação e acompanhamento da vida escolar. Antes de alterar qualquer informação, confirme sempre a escola, o ano letivo, o estudante e o vínculo corretos.',
    before: ['Tenha seu usuário e senha do SIGESC.', 'Confirme que o perfil ativo é Secretário(a).', 'Saiba quais escolas estão vinculadas ao seu acesso.'],
    steps: [
      { title: 'Entre e confira o contexto', text: 'Faça login e confirme seu nome, perfil ativo e as escolas vinculadas. Se você possui mais de um papel, verifique se está usando o papel correto antes de trabalhar.' },
      { title: 'Leia os cards do painel', text: 'Os cards resumem escolas, alunos, turmas e avisos dentro do escopo do seu acesso. Use-os como orientação inicial, não como substitutos da conferência detalhada.' },
      { title: 'Use o Acesso Rápido', text: 'Escolas, Turmas, Alunos, Servidores e Usuários aparecem como atalhos para a rotina cadastral e administrativa.' },
      { title: 'Reconheça o Menu de Administração', text: 'Localize os grupos Gestão Institucional, Gestão Escolar, Gestão Pedagógica, Gestão Social e Comunitária, Monitoramento e Análise e Recursos Humanos.' },
      { title: 'Use a busca do menu', text: 'Digite parte do nome da função, como “pré-matrícula”, “declaração”, “frequência”, “Bolsa” ou “RH”, em vez de procurar visualmente por toda a tela.' }
    ],
    observe: ['Perfil ativo', 'Escola vinculada', 'Ano letivo', 'Acesso Rápido', 'Itens visíveis no menu'],
    bestPractices: ['Confira o contexto antes de cadastrar ou movimentar um estudante.', 'Não compartilhe credenciais.', 'Quando houver dúvida sobre uma permissão, siga o que a interface efetivamente permite no seu perfil.'],
    attention: ['A rede pode aplicar ajustes de visibilidade por perfil.', 'Acesso a uma tela não significa que todas as ações de edição estejam liberadas.'],
    doneWhen: ['Você identifica os atalhos principais da secretaria.', 'Você sabe confirmar escola, perfil e ano letivo antes de iniciar uma operação.']
  },
  {
    slug: 'escola-equipe-usuarios',
    title: 'Escola, servidores e usuários: conferência de contexto',
    category: 'Comece aqui',
    estimatedTime: '8 min',
    systemRoute: '/admin/schools',
    objective: 'Conferir a unidade escolar, a equipe e os usuários vinculados antes de executar rotinas que dependem desses cadastros.',
    intro: 'Muitos erros operacionais começam fora da ficha do aluno: escola incorreta, servidor sem vínculo ou usuário sem o perfil esperado. Esta conferência evita retrabalho.',
    before: ['Confirme a escola em que vai trabalhar.', 'Tenha o nome do servidor ou usuário que deseja localizar.'],
    steps: [
      { title: 'Abra Escolas', text: 'Use o Acesso Rápido e confirme a unidade, situação e dados essenciais. Não altere dados institucionais sem autorização e sem que a ação esteja disponível no seu perfil.' },
      { title: 'Confira Servidores', text: 'Abra Servidores e localize o profissional pelo nome. Verifique o vínculo com a unidade antes de relacioná-lo a processos escolares.' },
      { title: 'Confira Usuários', text: 'Abra Usuários para verificar conta, papel e vínculo. Ações de criação ou edição devem respeitar as permissões exibidas na tela.' },
      { title: 'Resolva o cadastro-base primeiro', text: 'Se a pessoa ou a unidade estiver incorreta, corrija ou encaminhe o cadastro-base antes de tentar compensar o problema em matrícula, turma ou documento.' }
    ],
    observe: ['Unidade correta', 'Servidor correto', 'Papel do usuário', 'Vínculo com a escola', 'Ação disponível no perfil'],
    bestPractices: ['Trate cadastro de usuário e cadastro de servidor como conceitos diferentes.', 'Evite criar duplicidade por pequenas diferenças de nome.', 'Registre a necessidade de correção quando não tiver permissão para fazê-la.'],
    attention: ['O Secretário possui acesso às telas de Escolas, Servidores e Usuários, mas o nível de edição pode variar.', 'Nunca crie uma segunda conta para contornar um vínculo incorreto.'],
    doneWhen: ['Você consegue localizar escola, servidor e usuário corretos.', 'Você sabe diferenciar vínculo funcional de credencial de acesso.']
  },
  {
    slug: 'cadastro-aluno',
    title: 'Cadastrar um novo estudante com segurança',
    category: 'Cadastro e matrícula',
    estimatedTime: '12 min',
    systemRoute: '/admin/students',
    objective: 'Cadastrar um estudante sem duplicidade e com os dados essenciais conferidos antes da matrícula.',
    intro: 'Cadastro e matrícula são etapas diferentes. Primeiro existe a pessoa estudante; depois é criado o vínculo escolar correspondente ao ano, escola e turma.',
    before: ['Tenha os documentos e dados fornecidos pela família.', 'Pesquise o estudante antes de criar um novo cadastro.', 'Confirme a escola de atendimento.'],
    steps: [
      { title: 'Pesquise antes de cadastrar', text: 'Use nome, CPF ou outros identificadores disponíveis. Se já existir cadastro, atualize o registro existente em vez de criar outro.' },
      { title: 'Abra o cadastro de novo estudante', text: 'Use o botão de novo aluno e preencha os dados pessoais exatamente conforme a documentação apresentada.' },
      { title: 'Preencha endereço e contatos', text: 'Registre endereço estruturado, telefone e demais contatos quando disponíveis. Não invente informação para preencher campo desconhecido.' },
      { title: 'Revise responsáveis e documentos', text: 'Confirme os responsáveis informados e os identificadores antes de salvar.' },
      { title: 'Salve e confira a ficha', text: 'Após salvar, reabra ou revise o cadastro antes de iniciar a matrícula.' }
    ],
    observe: ['Duplicidade', 'Nome e data de nascimento', 'CPF/NIS quando informados', 'Responsáveis', 'Endereço', 'Escola'],
    bestPractices: ['Copie dados de documentos oficiais sem abreviações improvisadas.', 'Mantenha informação desconhecida como não informada quando o sistema permitir.', 'Faça a revisão antes da matrícula.'],
    attention: ['Não altere raça/cor, deficiência, comunidade tradicional ou outros dados sensíveis por suposição.', 'Um cadastro duplicado prejudica histórico, documentos e integrações.'],
    doneWhen: ['Existe um único cadastro para o estudante.', 'Os dados essenciais foram conferidos e a ficha está pronta para receber uma matrícula.']
  },
  {
    slug: 'busca-edicao-cadastral',
    title: 'Buscar, filtrar e corrigir dados cadastrais',
    category: 'Cadastro e matrícula',
    estimatedTime: '9 min',
    systemRoute: '/admin/students',
    objective: 'Localizar rapidamente o estudante correto e corrigir o cadastro sem alterar indevidamente seu vínculo escolar.',
    intro: 'Nem toda correção de cadastro exige movimentação de matrícula. Separar dados da pessoa de dados do vínculo evita mudanças acidentais de turma, escola ou status.',
    before: ['Tenha uma informação confiável para localizar o estudante.', 'Saiba exatamente qual dado precisa ser corrigido.'],
    steps: [
      { title: 'Use busca e filtros', text: 'Pesquise por nome e aplique filtros de escola, turma, situação ou outros disponíveis até reduzir a lista ao registro correto.' },
      { title: 'Confirme a identidade', text: 'Antes de editar, valide nome completo, data de nascimento e vínculo atual para evitar homônimos.' },
      { title: 'Edite somente o dado necessário', text: 'Corrija o campo cadastral específico. Não use alteração cadastral para simular transferência, remanejamento ou encerramento de matrícula.' },
      { title: 'Revise e salve', text: 'Compare o dado corrigido com a fonte apresentada e salve.' },
      { title: 'Confira o resultado', text: 'Volte à listagem e confirme que o estudante continua com o vínculo escolar esperado.' }
    ],
    observe: ['Homônimos', 'Escola e turma atuais', 'Campo que será alterado', 'Status da matrícula'],
    bestPractices: ['Faça alterações mínimas e justificáveis.', 'Preserve o histórico escolar.', 'Evite editar diversos campos sem necessidade.'],
    attention: ['Movimentações escolares devem usar as ações próprias de vínculo.', 'Correções sensíveis exigem fonte documental ou informação formal da família.'],
    doneWhen: ['O estudante correto foi identificado.', 'O dado foi corrigido sem mudar indevidamente a matrícula.']
  },
  {
    slug: 'documentos-aluno',
    title: 'Documentos e anexos do estudante',
    category: 'Cadastro e matrícula',
    estimatedTime: '8 min',
    systemRoute: '/admin/students',
    objective: 'Organizar documentos associados ao estudante e saber diferenciar anexo cadastral de documento oficial emitido pelo SIGESC.',
    intro: 'A secretaria lida tanto com documentos recebidos quanto com documentos gerados pelo sistema. Eles têm finalidades diferentes e precisam ser tratados de forma organizada.',
    before: ['Localize o estudante correto.', 'Identifique o tipo de documento e sua finalidade.'],
    steps: [
      { title: 'Abra a ficha do estudante', text: 'Confirme nome, escola e matrícula antes de anexar qualquer arquivo.' },
      { title: 'Use a área de documentos disponível', text: 'Anexe o arquivo no local apropriado, respeitando formatos e limites mostrados pela interface.' },
      { title: 'Nomeie e classifique corretamente', text: 'Quando o sistema solicitar descrição ou tipo, use uma identificação objetiva que permita reconhecer o documento depois.' },
      { title: 'Confira o arquivo salvo', text: 'Verifique se o documento pertence ao estudante correto e se pode ser aberto.' },
      { title: 'Separe anexo de documento oficial', text: 'Declarações, boletins e outros documentos verificáveis devem ser gerados nos módulos próprios quando disponíveis.' }
    ],
    observe: ['Estudante correto', 'Tipo de documento', 'Legibilidade', 'Data/validade quando relevante', 'Local de armazenamento'],
    bestPractices: ['Evite anexos duplicados.', 'Não armazene arquivo de outro estudante.', 'Use os módulos oficiais de emissão quando houver documento verificável.'],
    attention: ['Documentos escolares contêm dados pessoais e devem ser acessados apenas para finalidade institucional.'],
    doneWhen: ['O documento está no cadastro correto e pode ser identificado posteriormente.', 'Você sabe quando usar anexo e quando gerar um documento oficial.']
  },
  {
    slug: 'matricula-turma',
    title: 'Matricular estudante em escola e turma',
    category: 'Cadastro e matrícula',
    estimatedTime: '11 min',
    systemRoute: '/admin/students',
    objective: 'Criar a matrícula correta para o estudante, respeitando escola, turma, ano letivo e histórico existente.',
    intro: 'Matrícula cria um vínculo escolar. Por isso, a conferência anterior deve ser mais rigorosa do que uma simples edição cadastral.',
    before: ['Confirme que o estudante já existe no SIGESC.', 'Confirme escola, turma, etapa/série e ano letivo.', 'Verifique se já existe matrícula ativa equivalente.'],
    steps: [
      { title: 'Localize o estudante', text: 'Abra a ficha correta e revise o vínculo atual.' },
      { title: 'Escolha a ação de matrícula', text: 'Use a ação de vínculo disponível para matricular, sem criar um novo cadastro da pessoa.' },
      { title: 'Selecione escola, turma e ano', text: 'Confira cada seleção antes de confirmar. Turmas com nomes parecidos podem pertencer a turnos ou anos diferentes.' },
      { title: 'Confirme os dados da matrícula', text: 'Revise data, número de matrícula e demais campos apresentados.' },
      { title: 'Valide depois da gravação', text: 'Confirme que o estudante aparece na turma esperada e que o histórico de vínculos permaneceu coerente.' }
    ],
    observe: ['Matrícula já existente', 'Ano letivo', 'Escola', 'Turma', 'Etapa/série', 'Data de matrícula'],
    bestPractices: ['Nunca crie outro estudante para resolver um problema de matrícula.', 'Leia o histórico antes de criar novo vínculo.', 'Confira a turma imediatamente após salvar.'],
    attention: ['Transferência, remanejamento e matrícula inicial são movimentos diferentes.', 'Uma matrícula duplicada compromete relatórios e fechamento.'],
    doneWhen: ['O estudante possui um único vínculo ativo adequado ao contexto.', 'A turma e o ano letivo foram confirmados.']
  },
  {
    slug: 'remanejamento',
    title: 'Remanejar estudante entre turmas',
    category: 'Cadastro e matrícula',
    estimatedTime: '9 min',
    systemRoute: '/admin/students',
    objective: 'Mover o estudante entre turmas da mesma unidade sem apagar o histórico do vínculo anterior.',
    intro: 'Remanejamento não é transferência entre escolas. Ele altera a turma mantendo o contexto da unidade e deve preservar a rastreabilidade do período anterior.',
    before: ['Confirme que origem e destino pertencem à mesma escola.', 'Confira a turma atual e a turma de destino.', 'Saiba a data efetiva do remanejamento.'],
    steps: [
      { title: 'Localize a matrícula atual', text: 'Confirme estudante, escola, turma e ano letivo.' },
      { title: 'Use a ação de remanejamento', text: 'Escolha a ação específica exibida pelo sistema, em vez de editar manualmente o class_id ou criar outro aluno.' },
      { title: 'Escolha a turma de destino', text: 'Confira série/etapa, turno e capacidade ou organização da turma conforme a rotina da escola.' },
      { title: 'Informe a data correta', text: 'Use a data em que a mudança passou a valer, quando solicitada.' },
      { title: 'Confira histórico e turma atual', text: 'Depois da confirmação, verifique o novo vínculo e a preservação do histórico anterior.' }
    ],
    observe: ['Mesma escola', 'Turma de origem', 'Turma de destino', 'Data efetiva', 'Histórico preservado'],
    bestPractices: ['Documente a razão quando o fluxo oferecer campo de observação.', 'Evite apagar registros anteriores.', 'Comunique a equipe pedagógica quando a mudança afetar diário ou frequência.'],
    attention: ['Para mudança de escola use transferência, não remanejamento.'],
    doneWhen: ['A turma atual foi alterada corretamente.', 'O vínculo anterior continua rastreável no histórico.']
  },
  {
    slug: 'transferencia',
    title: 'Transferir estudante entre escolas ou para fora da rede',
    category: 'Cadastro e matrícula',
    estimatedTime: '12 min',
    systemRoute: '/admin/students',
    objective: 'Registrar corretamente a saída da escola de origem e, quando for dentro da rede, criar a entrada na escola de destino sem perder histórico.',
    intro: 'A transferência ocorre em duas etapas quando o destino pertence à rede: registrar a saída na origem e matricular na escola de destino. Para saída externa, a segunda etapa não ocorre no SIGESC.',
    before: ['Confirme a matrícula ativa de origem.', 'Saiba se o destino pertence à rede.', 'Tenha a data e, quando disponível, o motivo da transferência.'],
    steps: [
      { title: 'Localize e confira o vínculo de origem', text: 'Abra a ficha do estudante e confirme escola, turma e situação ativa.' },
      { title: 'Registre a transferência de saída', text: 'Use Ações de Vínculo e selecione Transferir. Informe os dados solicitados e confirme.' },
      { title: 'Confira o encerramento da origem', text: 'A matrícula de origem deve deixar de ser o vínculo ativo atual e o movimento deve ficar registrado.' },
      { title: 'Se o destino for da rede, matricule novamente', text: 'Use a ação Matricular, escolha escola de destino, turma e ano letivo e confirme a nova matrícula.' },
      { title: 'Se o destino for externo, encerre na saída', text: 'Não crie escola ou turma fictícia para representar destino fora da rede.' },
      { title: 'Revise o histórico', text: 'Confirme os registros de saída e, quando aplicável, entrada, sem perda das informações anteriores.' }
    ],
    observe: ['Destino dentro ou fora da rede', 'Data', 'Matrícula de origem', 'Nova matrícula quando interna', 'Histórico'],
    bestPractices: ['Preserve o histórico da escola de origem.', 'Não use edição cadastral para simular transferência.', 'Confirme a escola de destino antes de concluir a entrada.'],
    attention: ['Transferência interna não deve apagar frequência, notas ou registros já produzidos na origem.', 'Em caso de dúvida sobre a data efetiva, confirme com a documentação escolar antes de executar.'],
    doneWhen: ['A saída está registrada corretamente.', 'Se interna, há nova matrícula no destino e o histórico anterior permanece preservado.']
  },
  {
    slug: 'historico-movimentacoes',
    title: 'Histórico escolar e movimentações do estudante',
    category: 'Cadastro e matrícula',
    estimatedTime: '9 min',
    systemRoute: '/admin/students',
    objective: 'Consultar a trajetória de vínculos do estudante antes de corrigir, remanejar, transferir ou emitir documentos.',
    intro: 'O vínculo atual conta apenas uma parte da história. O histórico permite entender entradas, saídas, mudanças e períodos anteriores sem reescrever o passado.',
    before: ['Localize o estudante correto.', 'Defina qual evento ou período deseja confirmar.'],
    steps: [
      { title: 'Abra a ficha e o histórico', text: 'Acesse a opção de histórico/movimentações disponível para o estudante.' },
      { title: 'Leia em ordem cronológica', text: 'Observe escola, turma, ano, datas e tipos de movimento.' },
      { title: 'Compare com o vínculo atual', text: 'Confirme se o estado atual é consequência coerente dos movimentos registrados.' },
      { title: 'Use o histórico antes de corrigir', text: 'Se houver divergência, identifique o ponto exato da trajetória em vez de sobrescrever o cadastro atual.' },
      { title: 'Use a evidência em documentos', text: 'Antes de emitir histórico, declaração ou transferência, confira se os movimentos essenciais estão consistentes.' }
    ],
    observe: ['Ordem cronológica', 'Escola', 'Turma', 'Ano letivo', 'Entrada e saída', 'Situação atual'],
    bestPractices: ['Preserve registros anteriores.', 'Diferencie correção cadastral de reconstrução histórica.', 'Escalone inconsistências que exijam intervenção administrativa especial.'],
    attention: ['Não “conserte” o passado apagando movimentos válidos.', 'Reconstruções excepcionais podem exigir perfil superior.'],
    doneWhen: ['Você consegue explicar a trajetória do estudante.', 'A próxima ação foi escolhida com base no histórico, não apenas no status atual.']
  },
  {
    slug: 'pre-matriculas',
    title: 'Gerenciar solicitações de pré-matrícula',
    category: 'Cadastro e matrícula',
    estimatedTime: '10 min',
    systemRoute: '/admin/pre-matriculas',
    objective: 'Analisar solicitações de pré-matrícula e transformar pedidos válidos em encaminhamentos escolares consistentes.',
    intro: 'Pré-matrícula é uma solicitação anterior à matrícula definitiva. A secretaria deve conferir dados, disponibilidade e documentação antes de consolidar o vínculo escolar.',
    before: ['Confirme a escola e o período de atendimento.', 'Saiba os critérios definidos pela rede para análise das solicitações.'],
    steps: [
      { title: 'Abra Pré-Matrículas', text: 'Use filtros para localizar solicitações pendentes e o período de interesse.' },
      { title: 'Leia os dados enviados', text: 'Confira estudante, responsável, etapa/série pretendida, contatos e demais informações disponíveis.' },
      { title: 'Verifique duplicidade', text: 'Pesquise se o estudante já existe ou já possui matrícula ativa antes de criar novo vínculo.' },
      { title: 'Analise o encaminhamento', text: 'Confirme escola/turma conforme as regras da rede e a disponibilidade mostrada pelo sistema.' },
      { title: 'Atualize o status pelo fluxo previsto', text: 'Use apenas as ações disponíveis e registre a decisão conforme o processo da rede.' },
      { title: 'Confira a matrícula definitiva', text: 'Quando a solicitação for efetivada, confirme o cadastro e a matrícula resultantes.' }
    ],
    observe: ['Status da solicitação', 'Duplicidade', 'Contato do responsável', 'Etapa/série', 'Escola/turma', 'Resultado final'],
    bestPractices: ['Não confunda solicitação com matrícula concluída.', 'Evite cadastrar novamente estudante já existente.', 'Mantenha rastreabilidade da decisão.'],
    attention: ['Os critérios de aceite dependem das regras da rede.', 'Não prometa vaga apenas porque existe uma pré-matrícula registrada.'],
    doneWhen: ['A solicitação foi analisada e recebeu encaminhamento coerente.', 'Quando efetivada, a matrícula definitiva foi conferida.']
  },
  {
    slug: 'frequencia',
    title: 'Frequência: conferência e apoio à regularização',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/attendance',
    objective: 'Consultar frequência, localizar lacunas de registro e apoiar a escola na regularização documental sem substituir o lançamento pedagógico do professor.',
    intro: 'A secretaria precisa compreender a frequência porque ela aparece em documentos, programas sociais e fechamento escolar. O foco é conferir consistência e encaminhar pendências ao responsável pelo registro.',
    before: ['Confirme escola, turma e período.', 'Saiba se a dúvida é ausência do aluno ou ausência de lançamento.'],
    steps: [
      { title: 'Escolha o recorte correto', text: 'Selecione escola, turma, período e estudante quando necessário.' },
      { title: 'Diferencie falta de lançamento de falta do estudante', text: 'Campo vazio ou período sem diário não deve ser interpretado automaticamente como ausência do aluno.' },
      { title: 'Cruze com atestados e justificativas', text: 'Quando houver ausência, confira se existe documentação registrada e seu período de validade.' },
      { title: 'Encaminhe a pendência certa', text: 'Se faltar lançamento, acione o responsável pelo diário. Se houver situação de frequência do aluno, siga o fluxo de acompanhamento da escola.' },
      { title: 'Revise depois da correção', text: 'Confirme se o dado final ficou consistente antes de emitir documentos ou relatórios.' }
    ],
    observe: ['Período', 'Lançamentos ausentes', 'Faltas reais', 'Atestados', 'Consistência para documentos'],
    bestPractices: ['Nunca transforme ausência de dado em presença ou falta por suposição.', 'Conserve evidência documental.', 'Use o diário como fonte do registro pedagógico.'],
    attention: ['O professor é responsável pelo lançamento pedagógico quando essa regra se aplica à rede.', 'Correções devem preservar auditoria e histórico.'],
    doneWhen: ['Você sabe diferenciar ausência de lançamento e ausência do estudante.', 'Pendências foram encaminhadas ao responsável correto.']
  },
  {
    slug: 'notas',
    title: 'Notas: consulta, conferência e pendências',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '8 min',
    systemRoute: '/admin/grades',
    objective: 'Conferir lançamentos de notas e identificar pendências que podem afetar boletins e fechamento.',
    intro: 'O Secretário possui acesso à área de Notas, mas a atuação deve respeitar a responsabilidade pedagógica. O principal uso administrativo é conferir se o registro necessário existe e está associado à turma e ao período corretos.',
    before: ['Confirme turma, componente e período.', 'Saiba se está investigando um estudante ou uma pendência geral.'],
    steps: [
      { title: 'Abra Notas e aplique o recorte', text: 'Selecione escola, turma, disciplina e bimestre/período disponíveis.' },
      { title: 'Procure campos pendentes', text: 'Identifique ausência de lançamento sem confundir com nota baixa já registrada.' },
      { title: 'Confira matrícula e período', text: 'Se um estudante não aparece ou tem dado inesperado, confirme primeiro o vínculo escolar e a competência.' },
      { title: 'Encaminhe questões pedagógicas', text: 'Quando a dúvida for sobre valor da nota ou critério avaliativo, encaminhe ao professor/coordenação.' },
      { title: 'Revise antes do boletim', text: 'Use a conferência para evitar emissão de documento com período incompleto.' }
    ],
    observe: ['Turma', 'Componente', 'Período', 'Campo sem lançamento', 'Matrícula do estudante'],
    bestPractices: ['Trate nota registrada como evidência pedagógica.', 'Não altere avaliação para “fechar” boletim sem respaldo.', 'Confirme pendências antes da emissão de documentos.'],
    attention: ['Edição de notas deve respeitar a permissão exibida e a responsabilidade pedagógica.', 'Nota baixa é diferente de nota ausente.'],
    doneWhen: ['Você consegue identificar pendências de lançamento.', 'Questões pedagógicas foram encaminhadas sem adulterar registros.']
  },
  {
    slug: 'atestados-justificativas',
    title: 'Registrar e conferir atestados e justificativas',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/students',
    objective: 'Registrar documentação de ausência no estudante correto e conferir o período de validade antes de usá-la em análises de frequência.',
    intro: 'Atestado ou justificativa não deve ficar apenas em papel ou mensagem. Quando a funcionalidade estiver disponível, o registro no SIGESC permite que a informação acompanhe a vida escolar do estudante.',
    before: ['Localize o estudante correto.', 'Tenha documento, datas e informação necessária para o registro.'],
    steps: [
      { title: 'Abra a ficha do estudante', text: 'Confirme nome, escola, turma e matrícula atual.' },
      { title: 'Acesse a área de atestados/justificativas', text: 'Use o fluxo específico do sistema em vez de inserir informação solta em observações genéricas.' },
      { title: 'Registre datas e tipo corretamente', text: 'Transcreva o período conforme o documento apresentado.' },
      { title: 'Anexe ou referencie o documento quando disponível', text: 'Garanta que a justificativa possa ser comprovada.' },
      { title: 'Confira a frequência', text: 'Depois do registro, consulte o período correspondente para verificar se a informação aparece como esperado na rotina da escola.' }
    ],
    observe: ['Estudante', 'Data inicial/final', 'Tipo de justificativa', 'Documento', 'Período de frequência'],
    bestPractices: ['Não estenda datas além do documento.', 'Evite duplicar o mesmo atestado.', 'Proteja dados de saúde.'],
    attention: ['Atestado não deve ser convertido automaticamente em presença quando a regra da rede não prevê isso.', 'Dados de saúde exigem acesso restrito e finalidade legítima.'],
    doneWhen: ['O documento está vinculado ao estudante e período corretos.', 'A equipe consegue identificar a justificativa ao analisar a frequência.']
  },
  {
    slug: 'acompanhamento-diarios',
    title: 'Acompanhamento dos Diários de Classe',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/diary-dashboard',
    objective: 'Usar o painel de diários para localizar pendências que podem afetar frequência, notas, conteúdo e documentos escolares.',
    intro: 'Para a secretaria, o painel de diários é uma ferramenta de conferência e fechamento. Ele ajuda a saber se a base documental da turma está completa antes de emitir resultados.',
    before: ['Defina escola e período.', 'Saiba qual fechamento ou documento depende da conferência.'],
    steps: [
      { title: 'Abra Acompanhamento de Diários', text: 'Leia primeiro o panorama geral antes de abrir uma turma específica.' },
      { title: 'Identifique pendências', text: 'Localize turmas ou períodos com sinais de falta de frequência, conteúdo, notas ou outros registros.' },
      { title: 'Diferencie dado ausente de dado preocupante', text: 'Ausência de lançamento é pendência operacional; um valor já lançado pode exigir análise pedagógica.' },
      { title: 'Encaminhe ao responsável', text: 'Informe turma, período e tipo de pendência ao professor, coordenação ou direção conforme o caso.' },
      { title: 'Revise antes do fechamento', text: 'Volte ao painel e confirme a regularização antes de gerar documentos finais.' }
    ],
    observe: ['Turmas pendentes', 'Período', 'Tipo de registro ausente', 'Responsável pelo lançamento'],
    bestPractices: ['Faça conferências regulares, não apenas no fim do bimestre.', 'Use evidência objetiva na comunicação.', 'Não corrija registro pedagógico sem competência para isso.'],
    attention: ['O painel mostra sintomas; a causa deve ser confirmada com o responsável pelo registro.'],
    doneWhen: ['As pendências relevantes foram identificadas e encaminhadas.', 'A secretaria consegue verificar se o fechamento está documentalmente pronto.']
  },
  {
    slug: 'registro-conteudos',
    title: 'Registro de Conteúdos: consulta e consistência',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '7 min',
    systemRoute: '/admin/learning-objects',
    objective: 'Consultar conteúdos registrados e reconhecer quando a ausência de informação precisa ser encaminhada à equipe pedagógica.',
    intro: 'O Secretário pode acessar o registro de conteúdos, mas o conteúdo pedagógico pertence ao diário do professor. O uso administrativo é apoiar conferência e documentos, não substituir autoria docente.',
    before: ['Confirme turma, disciplina e período.', 'Defina qual informação precisa ser verificada.'],
    steps: [
      { title: 'Abra Registro de Conteúdos', text: 'Selecione o contexto correto antes de interpretar o que aparece.' },
      { title: 'Confira existência e período', text: 'Verifique se há registros correspondentes aos dias/períodos esperados.' },
      { title: 'Não complete por suposição', text: 'Se faltar conteúdo, encaminhe ao professor ou coordenação.' },
      { title: 'Relacione ao fechamento', text: 'Use a informação para apoiar conferência de diário e documentos quando necessário.' }
    ],
    observe: ['Turma', 'Disciplina', 'Período', 'Dias sem registro', 'Responsável'],
    bestPractices: ['Preserve autoria pedagógica.', 'Use o módulo como evidência de completude.', 'Encaminhe inconsistências com recorte claro.'],
    attention: ['Conteúdo ministrado não deve ser inventado pela secretaria.'],
    doneWhen: ['Você localiza o conteúdo do período correto.', 'Pendências são encaminhadas ao responsável pedagógico.']
  },
  {
    slug: 'calendario-diario',
    title: 'Calendário do Diário: dias letivos e períodos',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '7 min',
    systemRoute: '/admin/diary-calendar',
    objective: 'Conferir o calendário operacional usado pelos diários e evitar interpretações erradas de dias sem lançamento.',
    intro: 'Antes de cobrar um registro de diário, confirme se a data é letiva e se pertence ao período correto. O calendário dá o contexto temporal da escrituração.',
    before: ['Tenha a data ou período que deseja verificar.', 'Confirme a escola/ano letivo.'],
    steps: [
      { title: 'Abra Calendário do Diário', text: 'Selecione o contexto escolar correspondente.' },
      { title: 'Localize a data', text: 'Confira se é dia letivo, evento ou outra situação prevista.' },
      { title: 'Relacione ao diário', text: 'Se houver lacuna de frequência ou conteúdo, confirme primeiro se havia obrigação de registro naquela data.' },
      { title: 'Encaminhe divergências', text: 'Datas incoerentes devem ser tratadas pela gestão responsável pelo calendário, não compensadas manualmente no diário.' }
    ],
    observe: ['Dia letivo', 'Período', 'Evento', 'Compatibilidade com o diário'],
    bestPractices: ['Consulte o calendário antes de classificar um dia como pendente.', 'Evite criar registros em data sem atividade escolar prevista.'],
    attention: ['Alterações de calendário podem ter impacto amplo na escola.'],
    doneWhen: ['Você consegue explicar se a data exige registro.', 'Pendências de diário foram analisadas com o calendário correto.']
  },
  {
    slug: 'integridade-grade',
    title: 'Integridade da Grade Horária',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '8 min',
    systemRoute: '/admin/grade-integrity',
    objective: 'Identificar inconsistências de grade que podem impedir ou distorcer registros de diário e frequência.',
    intro: 'Quando turma, disciplina ou professor não se encaixam corretamente na grade, o problema pode aparecer como falha de diário. A secretaria deve reconhecer essa origem antes de tentar corrigir o sintoma.',
    before: ['Tenha a turma ou problema relatado.', 'Confirme ano letivo e escola.'],
    steps: [
      { title: 'Abra Integridade da Grade', text: 'Observe alertas e inconsistências apresentados.' },
      { title: 'Localize a turma afetada', text: 'Identifique componente, horário, professor ou outro elemento relacionado.' },
      { title: 'Compare com o cadastro da turma', text: 'Verifique se o problema decorre de vínculo ou configuração.' },
      { title: 'Encaminhe a correção adequada', text: 'Use o responsável administrativo/pedagógico conforme a natureza do problema.' },
      { title: 'Revise o diário depois', text: 'Confirme se a regularização da grade removeu a inconsistência operacional.' }
    ],
    observe: ['Turma', 'Componente', 'Professor', 'Horário', 'Ano letivo'],
    bestPractices: ['Corrija a causa estrutural antes de mexer em registros derivados.', 'Documente problemas recorrentes.'],
    attention: ['Não force registros para compensar grade inconsistente.'],
    doneWhen: ['A causa da inconsistência foi identificada.', 'O problema foi encaminhado e a rotina do diário pôde ser conferida novamente.']
  },
  {
    slug: 'diario-aee',
    title: 'Diário AEE: consulta e apoio administrativo',
    category: 'Vida escolar e acompanhamento',
    estimatedTime: '8 min',
    systemRoute: '/admin/diario-aee',
    objective: 'Compreender o Diário AEE sob a ótica da secretaria, apoiando conferência e documentação sem substituir o professor AEE ou a coordenação.',
    intro: 'O Secretário possui acesso ao módulo, mas plano e atendimento são registros pedagógicos especializados. O papel administrativo é conferir existência, vínculo e documentação quando necessário.',
    before: ['Confirme estudante e escola.', 'Saiba qual informação administrativa precisa ser conferida.'],
    steps: [
      { title: 'Abra o Diário AEE', text: 'Use os filtros de escola, ano e turma AEE quando disponíveis.' },
      { title: 'Identifique o estudante', text: 'Confirme se ele aparece no contexto correto antes de consultar plano ou atendimento.' },
      { title: 'Confira existência de registros', text: 'Verifique se há plano, atendimentos e diário consolidado quando isso for necessário para o processo administrativo.' },
      { title: 'Encaminhe questões pedagógicas', text: 'Conteúdo do plano, objetivos e estratégias devem ser tratados com professor AEE e coordenação.' },
      { title: 'Proteja a informação', text: 'Use dados do AEE somente para a finalidade institucional necessária.' }
    ],
    observe: ['Estudante correto', 'Vínculo AEE', 'Existência de plano', 'Atendimentos', 'Diário consolidado'],
    bestPractices: ['Não altere conteúdo pedagógico para resolver pendência administrativa.', 'Evite exposição de informações sensíveis.', 'Encaminhe dúvida técnica à equipe AEE.'],
    attention: ['Acesso ao módulo não transforma a secretaria em responsável pelo registro pedagógico do AEE.'],
    doneWhen: ['Você consegue confirmar a existência dos registros AEE necessários.', 'Questões pedagógicas foram direcionadas à equipe competente.']
  },
  {
    slug: 'boletim-online',
    title: 'Boletim Online: conferir antes de emitir',
    category: 'Documentos e fechamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/bulletins',
    objective: 'Conferir boletins com base na matrícula, notas e período corretos antes de imprimir, entregar ou orientar a família.',
    intro: 'O boletim é resultado de vários registros anteriores. Quando há erro, a correção deve ocorrer na fonte — matrícula, nota, frequência ou configuração — e não no documento final.',
    before: ['Confirme estudante, turma e período.', 'Verifique se os lançamentos do período estão completos.'],
    steps: [
      { title: 'Abra Boletim Online', text: 'Selecione ou localize o estudante e o período correto.' },
      { title: 'Confira identificação', text: 'Valide nome, escola, turma, ano e demais dados de cabeçalho.' },
      { title: 'Revise resultados', text: 'Observe notas e frequência e compare com as fontes quando algo parecer incoerente.' },
      { title: 'Corrija a origem da divergência', text: 'Não tente “ajustar o boletim” sem resolver o dado que o gerou.' },
      { title: 'Só então entregue ou imprima', text: 'Depois da conferência, utilize a opção de visualização/geração disponível.' }
    ],
    observe: ['Identificação', 'Turma', 'Período', 'Notas', 'Frequência', 'Completude'],
    bestPractices: ['Faça amostragem antes de emissão em massa.', 'Guarde rastreabilidade da correção.', 'Use o boletim oficial do sistema.'],
    attention: ['Boletim não deve ser usado para esconder pendência de lançamento.'],
    doneWhen: ['O boletim reflete os dados corretos do período.', 'Qualquer divergência foi resolvida na fonte.']
  },
  {
    slug: 'livro-promocao',
    title: 'Livro de Promoção: conferência do fechamento',
    category: 'Documentos e fechamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/promotion',
    objective: 'Acompanhar o fechamento anual e conferir se a situação final dos estudantes está coerente com os registros escolares.',
    intro: 'O Livro de Promoção consolida resultados finais. Por isso, ele deve ser consultado depois que matrícula, notas, frequência e situação final estiverem consistentes.',
    before: ['Confirme ano letivo e turma.', 'Verifique se os períodos anteriores estão fechados conforme a rotina da rede.'],
    steps: [
      { title: 'Abra Livro de Promoção', text: 'Escolha escola, ano e turma.' },
      { title: 'Leia a situação final', text: 'Observe os resultados apresentados por estudante.' },
      { title: 'Investigue inconsistências na origem', text: 'Se algo estiver inesperado, volte à matrícula, boletim, frequência ou regras de fechamento correspondentes.' },
      { title: 'Confirme pendências antes de concluir', text: 'Não trate resultado parcial como situação definitiva.' },
      { title: 'Registre/extraia somente após conferência', text: 'Use as funções disponíveis quando o conjunto estiver consistente.' }
    ],
    observe: ['Ano letivo', 'Turma', 'Situação final', 'Pendências', 'Compatibilidade com boletim'],
    bestPractices: ['Faça conferência conjunta com direção/coordenação quando houver divergência pedagógica.', 'Não altere resultado final sem base nos registros oficiais.'],
    attention: ['Fechamento anual exige consistência de todos os períodos.'],
    doneWhen: ['A situação final está coerente com os registros.', 'Pendências foram resolvidas antes da emissão final.']
  },
  {
    slug: 'declaracoes',
    title: 'Emitir Declarações Escolares verificáveis',
    category: 'Documentos e fechamento',
    estimatedTime: '9 min',
    systemRoute: '/admin/declaracoes',
    objective: 'Gerar declarações a partir de dados conferidos e preservar os mecanismos de autenticidade e verificação do SIGESC.',
    intro: 'Declaração escolar é documento institucional. Antes da emissão, a secretaria deve confirmar identidade, matrícula e situação correspondente ao tipo de declaração.',
    before: ['Localize o estudante correto.', 'Saiba qual declaração é necessária e para qual finalidade.'],
    steps: [
      { title: 'Abra Declarações Escolares', text: 'Escolha o tipo de documento disponível no módulo.' },
      { title: 'Selecione o estudante', text: 'Confirme nome, escola, turma e matrícula.' },
      { title: 'Revise as informações geradas', text: 'Leia o documento antes de baixar ou imprimir.' },
      { title: 'Corrija a fonte se houver erro', text: 'Se algum dado estiver incorreto, volte ao cadastro ou matrícula e corrija por meio do fluxo adequado.' },
      { title: 'Preserve QR/código de verificação', text: 'Utilize o PDF oficial gerado pelo sistema para manter a autenticidade verificável.' }
    ],
    observe: ['Tipo de declaração', 'Estudante', 'Matrícula', 'Data', 'Código/QR de verificação'],
    bestPractices: ['Leia antes de entregar.', 'Não edite externamente o PDF oficial.', 'Use a verificação pública quando precisar confirmar autenticidade.'],
    attention: ['Documento com dado incorreto deve ser reemitido após correção da fonte, não alterado manualmente.'],
    doneWhen: ['O documento corresponde ao estudante e à situação corretos.', 'O arquivo oficial mantém seus elementos de verificação.']
  },
  {
    slug: 'validar-documentos',
    title: 'Validar documentos escolares',
    category: 'Documentos e fechamento',
    estimatedTime: '6 min',
    systemRoute: '/admin/document-validator',
    objective: 'Verificar autenticidade e integridade de documentos emitidos pelo SIGESC antes de aceitar, reenviar ou arquivar.',
    intro: 'A validação reduz dúvidas sobre cópias, PDFs encaminhados por terceiros e documentos apresentados fora do contexto original.',
    before: ['Tenha o documento, código ou informação de verificação.', 'Confirme que se trata de documento emitido pelo SIGESC.'],
    steps: [
      { title: 'Abra Validar Documentos', text: 'Acesse a ferramenta interna de validação.' },
      { title: 'Informe o identificador solicitado', text: 'Use o código, token ou dado de verificação apresentado no documento.' },
      { title: 'Compare o resultado', text: 'Confira estudante, tipo, emissão e demais informações exibidas.' },
      { title: 'Trate divergência como alerta', text: 'Se a validação não corresponder ao arquivo apresentado, não considere o documento confirmado até esclarecer a origem.' }
    ],
    observe: ['Código', 'Tipo de documento', 'Titular', 'Resultado da validação', 'Integridade'],
    bestPractices: ['Valide documentos recebidos por canais externos quando necessário.', 'Não confie apenas na aparência do PDF.', 'Use o portal público quando apropriado.'],
    attention: ['Falha de validação exige investigação, não edição do documento.'],
    doneWhen: ['Você confirmou se o documento corresponde ao registro verificável do sistema.']
  },
  {
    slug: 'avisos-calendario',
    title: 'Avisos e calendário: comunicação escolar',
    category: 'Gestão administrativa e social',
    estimatedTime: '7 min',
    systemRoute: '/avisos',
    objective: 'Consultar e utilizar avisos e calendário de forma coerente com a comunicação oficial da escola.',
    intro: 'Comunicação clara reduz retrabalho na secretaria. Datas, eventos e avisos precisam estar alinhados com o que a escola efetivamente decidiu.',
    before: ['Confirme se a informação já foi validada pela gestão.', 'Saiba quem é o público do aviso ou evento.'],
    steps: [
      { title: 'Abra Avisos', text: 'Consulte as mensagens vigentes e confirme conteúdo, período e público.' },
      { title: 'Abra o Calendário', text: 'Confira datas e eventos relacionados.' },
      { title: 'Evite mensagens contraditórias', text: 'Antes de orientar famílias, confronte aviso e calendário quando ambos tratam do mesmo evento.' },
      { title: 'Use o canal oficial', text: 'Quando houver permissão para publicar ou editar, faça isso somente com informação institucional confirmada.' }
    ],
    observe: ['Data', 'Público', 'Vigência', 'Evento relacionado', 'Mensagem oficial'],
    bestPractices: ['Escreva datas e horários de forma inequívoca.', 'Revise antes de publicar.', 'Evite duplicar comunicados com informações diferentes.'],
    attention: ['Ação de publicação depende das permissões do perfil e da política da escola.'],
    doneWhen: ['A comunicação consultada ou publicada está coerente com o calendário e com a decisão institucional.']
  },
  {
    slug: 'bolsa-familia-busca-ativa',
    title: 'Bolsa Família e Busca Ativa: acompanhamento de frequência',
    category: 'Gestão administrativa e social',
    estimatedTime: '11 min',
    systemRoute: '/admin/bolsa-familia',
    objective: 'Acompanhar estudantes vinculados às rotinas de frequência do Bolsa Família e identificar casos que exigem conferência ou Busca Ativa.',
    intro: 'Esse módulo transforma registros de frequência em acompanhamento social. A secretaria deve conferir os dados de origem e colaborar com a equipe responsável pelos encaminhamentos.',
    before: ['Confirme competência/período.', 'Verifique se os diários e justificativas do período estão atualizados.'],
    steps: [
      { title: 'Abra Bolsa Família', text: 'Selecione o período e a escola correspondentes.' },
      { title: 'Leia indicadores e casos', text: 'Identifique estudantes com frequência que exige atenção e diferencie dado incompleto de frequência efetivamente baixa.' },
      { title: 'Confira atestados e movimentações', text: 'Antes de encaminhar um caso, revise justificativas, transferência, matrícula e outras situações que alterem a leitura.' },
      { title: 'Abra Busca Ativa quando necessário', text: 'Use o painel específico para acompanhar casos que exigem ação da escola/equipe.' },
      { title: 'Registre o encaminhamento institucional', text: 'Siga o fluxo definido pela rede e mantenha a informação atualizada.' }
    ],
    observe: ['Competência', 'Frequência consolidada', 'Justificativas', 'Transferências', 'Caso de Busca Ativa'],
    bestPractices: ['Confirme a base antes de encaminhar família.', 'Trabalhe junto à equipe pedagógica/social.', 'Preserve dados pessoais e sociais.'],
    attention: ['Percentual baixo pode ser real ou consequência de registro ainda incompleto; investigue antes de concluir.', 'Não exponha publicamente estudantes acompanhados.'],
    doneWhen: ['Os casos foram analisados com dados consistentes.', 'Encaminhamentos necessários ficaram identificados e acompanháveis.']
  },
  {
    slug: 'rh-folha',
    title: 'RH / Folha: conferência administrativa',
    category: 'Gestão administrativa e social',
    estimatedTime: '9 min',
    systemRoute: '/admin/hr',
    objective: 'Consultar e conferir informações funcionais disponíveis ao perfil Secretário sem ultrapassar a competência administrativa definida pela rede.',
    intro: 'RH contém dados funcionais e potencialmente sensíveis. O uso pela secretaria deve ser objetivo, restrito à escola e à finalidade institucional.',
    before: ['Confirme a escola e o servidor.', 'Saiba qual dado funcional precisa ser consultado ou conferido.'],
    steps: [
      { title: 'Abra RH / Folha', text: 'Use os filtros para localizar o servidor ou conjunto relevante.' },
      { title: 'Confira identificação e vínculo', text: 'Valide nome, unidade, função e demais dados mostrados.' },
      { title: 'Analise somente o necessário', text: 'Evite navegar ou compartilhar informações sem relação com a demanda.' },
      { title: 'Use apenas ações autorizadas', text: 'Se a interface não permitir editar determinado campo, encaminhe ao responsável de RH/SEMED.' },
      { title: 'Revise o resultado', text: 'Quando houver alteração permitida, confirme se o dado final ficou correto e documentado.' }
    ],
    observe: ['Servidor', 'Unidade', 'Função/vínculo', 'Carga ou dado funcional', 'Permissão de ação'],
    bestPractices: ['Aplique princípio do mínimo acesso.', 'Não compartilhe informações funcionais por canais informais.', 'Encaminhe questões de folha ao setor competente quando necessário.'],
    attention: ['Acesso à tela não autoriza qualquer alteração.', 'Dados funcionais exigem confidencialidade.'],
    doneWhen: ['Você localizou e conferiu o dado funcional necessário.', 'Qualquer ação ficou dentro da competência do perfil.']
  },
  {
    slug: 'painel-rede',
    title: 'Painel da Rede (CTUE): leitura administrativa',
    category: 'Gestão administrativa e social',
    estimatedTime: '8 min',
    systemRoute: '/admin/rede',
    objective: 'Utilizar o Painel da Rede para contextualizar dados da unidade e reconhecer divergências que precisam ser investigadas na fonte.',
    intro: 'O Painel da Rede agrega informações. Para a secretaria, ele ajuda a comparar totais e contexto, mas não substitui listas e cadastros quando for necessário conferir um caso individual.',
    before: ['Saiba qual indicador ou total deseja conferir.', 'Tenha a escola/período de referência.'],
    steps: [
      { title: 'Abra Painel da Rede', text: 'Observe os indicadores apresentados e o escopo aplicado.' },
      { title: 'Compare com a unidade', text: 'Identifique diferenças que merecem conferência.' },
      { title: 'Volte à fonte', text: 'Para divergência de alunos, turmas ou matrículas, consulte o módulo de origem antes de concluir que existe erro.' },
      { title: 'Registre a inconsistência', text: 'Quando necessário, anote o indicador, período e evidência para encaminhamento.' }
    ],
    observe: ['Escopo', 'Período', 'Totais', 'Diferença em relação à fonte', 'Tendência'],
    bestPractices: ['Use o painel para orientar investigação.', 'Não edite cadastro apenas para “bater número” sem entender a causa.', 'Compare dados do mesmo período.'],
    attention: ['Indicador agregado não explica sozinho a causa de uma divergência.'],
    doneWhen: ['Você sabe interpretar o indicador no contexto correto.', 'Divergências foram verificadas na fonte correspondente.']
  },
  {
    slug: 'cobertura-curricular',
    title: 'Cobertura Curricular: apoio à conferência da escola',
    category: 'Monitoramento e apoio à gestão',
    estimatedTime: '7 min',
    systemRoute: '/admin/curriculo/cobertura',
    objective: 'Compreender a cobertura curricular como indicador de registro e apoiar a gestão sem assumir decisões pedagógicas da coordenação.',
    intro: 'O Secretário tem acesso à Cobertura Curricular. O uso administrativo é reconhecer lacunas que podem afetar a consistência dos registros e encaminhá-las à equipe pedagógica.',
    before: ['Confirme escola, turma e período.', 'Saiba que a decisão sobre currículo cabe à equipe pedagógica.'],
    steps: [
      { title: 'Abra Cobertura Curricular', text: 'Leia o recorte e os indicadores mostrados.' },
      { title: 'Localize lacunas relevantes', text: 'Identifique turmas/componentes com ausência ou baixa cobertura registrada.' },
      { title: 'Confira Registro de Conteúdos', text: 'Antes de concluir, veja se a origem é ausência de registro.' },
      { title: 'Encaminhe à coordenação', text: 'Informe turma, componente e período, sem prescrever solução pedagógica.' }
    ],
    observe: ['Turma', 'Componente', 'Período', 'Cobertura', 'Registro de conteúdos'],
    bestPractices: ['Use como sinal de conferência, não como julgamento docente.', 'Encaminhe com evidência objetiva.'],
    attention: ['Cobertura curricular não mede sozinha qualidade da aprendizagem.'],
    doneWhen: ['Você identifica a lacuna e sua fonte provável.', 'A demanda foi encaminhada à equipe pedagógica competente.']
  },
  {
    slug: 'intervencoes-plano-acao',
    title: 'Intervenções e Plano de Ação: apoio ao acompanhamento',
    category: 'Monitoramento e apoio à gestão',
    estimatedTime: '9 min',
    systemRoute: '/admin/intervencoes',
    objective: 'Consultar intervenções e apoiar o acompanhamento administrativo de ações, responsáveis e prazos definidos pela gestão.',
    intro: 'A secretaria pode contribuir para que intervenções não se percam: localizar registros, conferir responsáveis, acompanhar prazos e manter documentação organizada.',
    before: ['Confirme escola, período e contexto da intervenção.', 'Saiba qual responsável ou prazo precisa ser acompanhado.'],
    steps: [
      { title: 'Abra Intervenções Necessárias', text: 'Leia os casos ou sinais apresentados e identifique o contexto.' },
      { title: 'Confirme a evidência de origem', text: 'Quando necessário, consulte frequência, cobertura, diário ou outro módulo que sustenta o alerta.' },
      { title: 'Acesse Plano de Ação', text: 'Verifique ações, responsáveis e prazos disponíveis para acompanhamento.' },
      { title: 'Apoie a organização', text: 'Contribua com documentação, contato e registro administrativo sem substituir a decisão pedagógica ou de gestão.' },
      { title: 'Revise o status', text: 'Retorne ao plano para verificar se a ação foi concluída ou precisa de novo encaminhamento.' }
    ],
    observe: ['Evidência', 'Responsável', 'Prazo', 'Status', 'Retorno'],
    bestPractices: ['Não transforme alerta em culpa.', 'Registre prazos de forma clara.', 'Separe decisão pedagógica de apoio administrativo.'],
    attention: ['A Secretaria apoia o fluxo; a definição da intervenção deve respeitar as competências da gestão e coordenação.'],
    doneWhen: ['A ação possui responsável e prazo identificáveis.', 'A secretaria consegue verificar posteriormente o retorno.']
  },
  {
    slug: 'ranking-gestao',
    title: 'Ranking de Gestão: leitura responsável',
    category: 'Monitoramento e apoio à gestão',
    estimatedTime: '7 min',
    systemRoute: '/admin/ranking-gestores',
    objective: 'Interpretar indicadores comparativos sem usar posição de ranking como prova isolada de qualidade ou falha.',
    intro: 'O Secretário pode usar o ranking para localizar diferenças e necessidades de conferência. A posição só faz sentido quando se entende quais dados formam o indicador.',
    before: ['Confirme período e unidade.', 'Saiba quais dimensões estão sendo comparadas.'],
    steps: [
      { title: 'Abra Ranking de Gestão', text: 'Leia primeiro os indicadores que compõem a visão.' },
      { title: 'Não pare na posição', text: 'Observe valores, período e tendência quando disponíveis.' },
      { title: 'Volte à fonte', text: 'Se um indicador chama atenção, consulte o módulo que gera a evidência.' },
      { title: 'Encaminhe divergências objetivas', text: 'Leve à gestão o dado, período e fonte em vez de apenas dizer que a escola “subiu” ou “caiu”.' }
    ],
    observe: ['Indicador', 'Período', 'Fonte', 'Tendência', 'Contexto'],
    bestPractices: ['Use comparação para investigação e melhoria.', 'Evite exposição de profissionais.', 'Trabalhe com dados do mesmo período.'],
    attention: ['Ranking não é diagnóstico completo da escola.'],
    doneWhen: ['Você consegue explicar o que o indicador representa.', 'A comparação gerou uma pergunta verificável, não um julgamento automático.']
  },
  {
    slug: 'fechamento-secretaria',
    title: 'Checklist de fechamento da secretaria escolar',
    category: 'Monitoramento e apoio à gestão',
    estimatedTime: '12 min',
    systemRoute: '/dashboard',
    objective: 'Encerrar período ou ano letivo com uma sequência de conferências que reduza documentos incorretos e pendências descobertas tarde demais.',
    intro: 'Fechamento não é apenas clicar em imprimir. É garantir que cadastro, matrícula, diário e documentos contam a mesma história escolar.',
    before: ['Defina período/ano e turmas que serão fechados.', 'Combine responsabilidades com direção e coordenação.'],
    steps: [
      { title: '1. Matrículas e movimentações', text: 'Confira estudantes ativos, transferidos, remanejados e vínculos encerrados. Casos sem turma ou duplicados devem ser tratados antes.' },
      { title: '2. Diários e calendário', text: 'Use Acompanhamento de Diários, Calendário e Integridade da Grade para localizar pendências estruturais.' },
      { title: '3. Frequência, notas e justificativas', text: 'Verifique se os períodos necessários estão registrados e se atestados/movimentações explicam situações especiais.' },
      { title: '4. Boletins e Livro de Promoção', text: 'Faça conferência antes de emitir documentos finais.' },
      { title: '5. Documentos oficiais', text: 'Gere declarações e demais documentos pelo SIGESC, mantendo QR/código de verificação.' },
      { title: '6. Pendências sociais e administrativas', text: 'Revise Bolsa Família/Busca Ativa e outros processos que dependam dos dados escolares.' },
      { title: '7. Revisão final com a gestão', text: 'Compartilhe pendências restantes com responsável e prazo, evitando que problemas fiquem sem dono.' }
    ],
    observe: ['Matrículas', 'Movimentações', 'Diários', 'Frequência', 'Notas', 'Boletins', 'Promoção', 'Documentos', 'Pendências'],
    bestPractices: ['Faça fechamento progressivo durante o período.', 'Use checklist por turma.', 'Resolva a fonte antes de reemitir documento.', 'Mantenha responsáveis e prazos claros.'],
    attention: ['Não apague histórico para “limpar” pendências.', 'Resultado pedagógico deve ser validado pela equipe competente.'],
    doneWhen: ['Cadastro, vínculos, diários e documentos estão coerentes.', 'Toda pendência restante possui responsável e prazo definidos.']
  }
];

export const secretaryTutorialBySlug = Object.fromEntries(
  secretaryTutorials.map((tutorial) => [tutorial.slug, tutorial])
);

export const secretaryTutorialCategories = [
  'Comece aqui',
  'Cadastro e matrícula',
  'Vida escolar e acompanhamento',
  'Documentos e fechamento',
  'Gestão administrativa e social',
  'Monitoramento e apoio à gestão'
];
