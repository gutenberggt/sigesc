import axios from 'axios';

// F2.7 — a leitura class-wide do professor é composta no backend, que conhece
// simultaneamente o entitlement legado (teacher_assignments) e os vínculos DVD.
// Esta camada NÃO monta dados: apenas impede que os bridges anteriores convertam
// uma leitura sem componente em uma agregação exclusivamente canônica.
//
// F4 — o mesmo backend já é a SSoT dos writes do formulário histórico em
// /learning-objects: ele identifica IDs canônicos e grava em content_entries,
// preservando RBAC, tenant, auditoria e optimistic locking. Em acessos genéricos
// do professor (sem assignment_id explícito), PUT/DELETE não podem ser bloqueados
// pelo cache privado do contentDvdBridge antes de chegarem a esse adapter.

const isProfessorContentPage = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname === '/professor/objetos-conhecimento';
};

const hasExplicitAssignment = () => {
  if (typeof window === 'undefined') return false;
  return Boolean(new URLSearchParams(window.location.search).get('assignment_id'));
};

const isLearningObjectsList = (url = '') => (
  /\/learning-objects\/?(?:\?|$)/.test(String(url || '')) &&
  !String(url || '').includes('/learning-objects/pdf/') &&
  !String(url || '').includes('/learning-objects/check-date/')
);

const isLearningObjectsRecord = (url = '') => {
  const value = String(url || '');
  if (!/\/learning-objects\/[^/?]+(?:\?|$)/.test(value)) return false;
  if (value.includes('/learning-objects/check-date/')) return false;
  if (value.includes('/copy-to-class')) return false;
  if (value.includes('/learning-objects/pdf/')) return false;
  return true;
};

// Registrado depois dos resolvers DVD existentes. Axios executa request
// interceptors em ordem inversa; portanto este gate roda antes do bridge
// principal e consegue preservar o contrato F4 para writes sem contexto DVD
// explícito. Com assignment_id, o fluxo DVD explícito continua prevalecendo.
axios.interceptors.request.use((config) => {
  if (config.__skipContentDvdBridge || !isProfessorContentPage()) return config;

  const method = String(config.method || 'get').toLowerCase();

  // Um assignment_id explícito significa que a navegação veio de Meus Diários.
  // Nesse contexto, leitura e escrita precisam atravessar o mesmo contentDvdBridge:
  // o GET class-wide alimenta o recordCache usado pelo PUT/DELETE e preserva a
  // resolução por vínculo. Desviar somente o GET para a projeção mista quebraria
  // essa simetria e produziria CONTENT_RELOAD_REQUIRED/404 falsos no salvamento.
  if (hasExplicitAssignment()) return config;

  // F4: a tela genérica já carregou o registro pela projeção backend. Se não há
  // assignment_id explícito na URL, o backend /learning-objects é quem deve
  // decidir se o ID é canônico ou legado. Isto evita CONTENT_RELOAD_REQUIRED
  // falso quando a leitura class-wide foi marcada com __skipContentDvdBridge.
  if (
    !hasExplicitAssignment() &&
    (method === 'put' || method === 'delete') &&
    isLearningObjectsRecord(config.url)
  ) {
    config.__skipContentDvdBridge = true;
    config.__contentPartialCutoverFormWrite = true;
    return config;
  }

  if (method !== 'get' || !isLearningObjectsList(config.url)) return config;

  const params = config.params || {};
  const classId = params.class_id;
  const componentId = params.course_id || params.component_id || null;
  if (!classId || componentId) return config;

  config.__skipContentDvdBridge = true;
  config.__contentPartialCutoverClassWide = true;
  return config;
});
