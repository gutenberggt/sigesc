import axios from 'axios';

// F2.7 — a leitura class-wide do professor é composta no backend, que conhece
// simultaneamente o entitlement legado (teacher_assignments) e os vínculos DVD.
// Esta camada NÃO monta dados: apenas impede que os bridges anteriores convertam
// uma leitura sem componente em uma agregação exclusivamente canônica.

const isProfessorContentPage = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname === '/professor/objetos-conhecimento';
};

const isLearningObjectsList = (url = '') => (
  /\/learning-objects\/?(?:\?|$)/.test(String(url || '')) &&
  !String(url || '').includes('/learning-objects/pdf/') &&
  !String(url || '').includes('/learning-objects/check-date/')
);

// Registrado depois dos resolvers DVD existentes. Axios executa request
// interceptors em ordem inversa; portanto este gate roda primeiro e marca
// somente o GET class-wide para atravessar os bridges sem reescrita.
axios.interceptors.request.use((config) => {
  if (config.__skipContentDvdBridge || !isProfessorContentPage()) return config;

  const method = String(config.method || 'get').toLowerCase();
  if (method !== 'get' || !isLearningObjectsList(config.url)) return config;

  const params = config.params || {};
  const classId = params.class_id;
  const componentId = params.course_id || params.component_id || null;
  if (!classId || componentId) return config;

  config.__skipContentDvdBridge = true;
  config.__contentPartialCutoverClassWide = true;
  return config;
});
