import axios from 'axios';

// R2.0g.4 — compatibilidade de leitura para conteúdo canônico sem assignment.
//
// O assistente administrativo grava sempre em content_entries. Em uma turma que
// ainda opera pelo fluxo legado, o contentDvdBridge mantém GET /learning-objects
// quando /professor/diarios não entrega candidato DVD. Esta camada, registrada
// depois dos bridges DVD, preserva a resposta legada e acrescenta somente os
// content_entries sem assignment_id da mesma turma/componente.
//
// Nenhum dado é migrado ou escrito por esta ponte.

const canonicalCache = new Map();

const isProfessorContentPage = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname === '/professor/objetos-conhecimento';
};

const isLearningObjectsList = (url = '') => (
  /\/learning-objects\/?(?:\?|$)/.test(String(url || '')) &&
  !String(url || '').includes('/learning-objects/pdf/') &&
  !String(url || '').includes('/learning-objects/check-date/')
);

const isCheckDateUrl = (url = '') => String(url || '').includes('/learning-objects/check-date/');

const apiRoot = (url = '') => String(url || '').split('/learning-objects')[0];
const canonicalRoot = (url = '') => `${apiRoot(url)}/content-entries`;

const normalizeCanonical = (record = {}) => ({
  ...record,
  course_id: record.course_id || record.component_id || null,
  component_id: record.component_id || record.course_id || null,
  source: 'content_entries',
  legacy: false,
  read_only: false,
});

const cacheCanonical = (records = []) => {
  records.forEach((record) => {
    if (record?.id) canonicalCache.set(record.id, normalizeCanonical(record));
  });
};

const filterByLegacyWindow = (records = [], meta = {}) => records.filter((record) => {
  if (meta.academicYear && Number(record.academic_year) !== Number(meta.academicYear)) return false;
  if (meta.month) {
    const month = Number(String(record.date || '').slice(5, 7));
    if (month !== Number(meta.month)) return false;
  }
  return true;
});

const semanticKey = (record = {}) => [
  record.class_id || '',
  record.component_id || record.course_id || '',
  record.date || '',
  record.teacher_id || record.recorded_by || '',
].join('|');

const mergeLegacyAndCanonical = (legacy = [], canonical = []) => {
  const canonicalKeys = new Set(canonical.map(semanticKey));
  const canonicalLegacyIds = new Set(canonical.map((item) => item.legacy_id).filter(Boolean));
  const legacyFiltered = legacy.filter((item) => (
    !canonicalLegacyIds.has(item.id) && !canonicalKeys.has(semanticKey(item))
  ));
  return [...canonical, ...legacyFiltered].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
};

const loadCanonicalLegacyMode = async (config, meta) => {
  const response = await axios.get(canonicalRoot(meta.originalUrl || config.url), {
    params: {
      class_id: meta.classId,
      component_id: meta.componentId,
      date: meta.date || undefined,
    },
    headers: config.headers,
    __skipContentDvdBridge: true,
  });
  const items = Array.isArray(response.data?.items) ? response.data.items : [];
  const assignmentless = items
    .filter((item) => !item?.assignment_id)
    .map(normalizeCanonical);
  return filterByLegacyWindow(assignmentless, meta);
};

// Axios executa request interceptors em ordem inversa. Como este módulo é
// importado depois dos resolvers existentes, ele apenas marca a intenção e deixa
// os bridges DVD terem a oportunidade de reescrever a rota. A resposta só é
// composta se a URL final continuar sendo /learning-objects.
axios.interceptors.request.use((config) => {
  if (config.__skipContentDvdBridge || !isProfessorContentPage()) return config;

  const method = String(config.method || 'get').toLowerCase();
  const url = String(config.url || '');

  if (method === 'get' && isLearningObjectsList(url)) {
    const params = config.params || {};
    const classId = params.class_id;
    const componentId = params.course_id || params.component_id || null;
    if (!classId || !componentId) return config;

    config.__legacyCanonicalVisibilityList = {
      originalUrl: url,
      classId,
      componentId,
      date: params.date || null,
      academicYear: params.academic_year || null,
      month: params.month || null,
    };
    return config;
  }

  if (method === 'get' && isCheckDateUrl(url)) {
    const match = url.match(/\/learning-objects\/check-date\/([^/]+)\/([^/]+)\/([^/?]+)/);
    if (!match) return config;
    config.__legacyCanonicalVisibilityCheckDate = {
      originalUrl: url,
      classId: decodeURIComponent(match[1]),
      componentId: decodeURIComponent(match[2]),
      date: decodeURIComponent(match[3]),
      academicYear: config.params?.academic_year || Number(decodeURIComponent(match[3]).slice(0, 4)),
    };
    return config;
  }

  // Um registro canônico que entrou pela composição acima pode ser aberto pelo
  // mesmo formulário histórico. O GET individual precisa continuar canônico.
  if (method === 'get' && url.includes('/learning-objects/')) {
    const id = url.split('/').filter(Boolean).pop();
    if (!canonicalCache.has(id)) return config;
    config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`;
    config.__skipContentDvdBridge = true;
    return config;
  }

  return config;
});

axios.interceptors.response.use(async (response) => {
  const config = response.config || {};
  const finalUrl = String(config.url || '');

  if (config.__legacyCanonicalVisibilityList && finalUrl.includes('/learning-objects')) {
    const canonical = await loadCanonicalLegacyMode(config, config.__legacyCanonicalVisibilityList);
    cacheCanonical(canonical);
    const legacy = Array.isArray(response.data) ? response.data : [];
    response.data = mergeLegacyAndCanonical(legacy, canonical);
    return response;
  }

  if (config.__legacyCanonicalVisibilityCheckDate && finalUrl.includes('/learning-objects')) {
    if (response.data?.has_record) return response;
    const canonical = await loadCanonicalLegacyMode(config, config.__legacyCanonicalVisibilityCheckDate);
    cacheCanonical(canonical);
    if (canonical.length > 0) {
      response.data = { has_record: true, record: canonical[0] };
    }
    return response;
  }

  return response;
});
