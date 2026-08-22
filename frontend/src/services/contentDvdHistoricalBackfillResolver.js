import axios from 'axios';

// P0 22/08/2026 — conteúdo retroativo anterior ao cutover DVD.
//
// O vínculo DVD pode ter sido criado em 18/08, mas o professor precisa continuar
// preenchendo datas pedagógicas anteriores. Esta camada usa o vínculo atual apenas
// como prova de propriedade; não altera valid_from e nunca reabre escrita em
// /learning-objects. O backend revalida propriedade, capability, escola e tenant.

const diaryCache = new Map();
const recordCache = new Map();

const getRootAssignmentId = () => {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('assignment_id') || '';
};

const isLearningObjectsUrl = (url = '') => url.includes('/learning-objects');
const isPdfUrl = (url = '') => url.includes('/learning-objects/pdf/');
const isCheckDateUrl = (url = '') => url.includes('/learning-objects/check-date/');
const isCopyUrl = (url = '') => url.includes('/copy-to-class');
const canonicalBase = (url = '') => url.replace('/learning-objects', '/content-entries');
const apiRoot = (url = '') => url.split('/learning-objects')[0];

const bridgeError = (code, message, status = 409) => {
  const error = new Error(message);
  error.response = { status, data: { detail: { code, message } } };
  return error;
};

const loadDiaries = async (config, academicYear) => {
  const year = Number(academicYear) || new Date().getFullYear();
  const root = apiRoot(config.url || '');
  const key = `${root}|${year}`;

  if (!diaryCache.has(key)) {
    diaryCache.set(
      key,
      axios.get(`${root}/professor/diarios`, {
        params: { academic_year: year },
        headers: config.headers,
        __skipContentDvdBridge: true,
      }).then((response) => (
        Array.isArray(response.data?.items) ? response.data.items : []
      )).catch(() => [])
    );
  }

  return diaryCache.get(key);
};

const resolveHistoricalAssignment = async (
  config,
  { classId, componentId, date, academicYear, preferredAssignmentId = '' }
) => {
  if (!classId || !componentId || !date) return null;
  const target = String(date).slice(0, 10);
  if (!target) return null;

  const diaries = await loadDiaries(config, academicYear);
  const eligible = diaries.filter((item) => (
    item?.class_id === classId &&
    item?.capabilities?.content_enabled === true &&
    item?.valid_from &&
    target < String(item.valid_from).slice(0, 10)
  ));

  const exact = eligible.filter((item) => item?.component_id === componentId);
  const classWide = eligible.filter((item) => !item?.component_id);
  const candidates = exact.length > 0 ? exact : classWide;

  if (preferredAssignmentId) {
    const preferred = candidates.find((item) => item.assignment_id === preferredAssignmentId);
    if (preferred) return preferred;
  }

  if (candidates.length === 1) return candidates[0];
  if (candidates.length === 0) return null;

  throw bridgeError(
    'DVD_CONTENT_ASSIGNMENT_AMBIGUOUS',
    'Há mais de um vínculo posterior compatível para este lançamento histórico. Abra o registro a partir de Meus Diários.'
  );
};

const cacheRecord = (record) => {
  if (!record?.id) return;
  recordCache.set(record.id, {
    ...record,
    course_id: record.course_id || record.component_id || null,
    component_id: record.component_id || record.course_id || null,
  });
};

// Registrado depois dos resolvers DVD existentes. Como Axios executa request
// interceptors em ordem inversa, esta camada resolve primeiro o caso histórico;
// requisições que não são retroativas seguem intactas para os bridges existentes.
axios.interceptors.request.use(async (config) => {
  if (config.__skipContentDvdBridge) return config;
  const url = String(config.url || '');
  if (!isLearningObjectsUrl(url) || isPdfUrl(url)) return config;

  const method = String(config.method || 'get').toLowerCase();
  const rootAssignmentId = getRootAssignmentId();

  if (isCheckDateUrl(url) && method === 'get') {
    const match = url.match(/\/learning-objects\/check-date\/([^/]+)\/([^/]+)\/([^/?]+)/);
    if (!match) return config;

    const classId = decodeURIComponent(match[1]);
    const componentId = decodeURIComponent(match[2]);
    const date = decodeURIComponent(match[3]);
    const historical = await resolveHistoricalAssignment(config, {
      classId,
      componentId,
      date,
      academicYear: config.params?.academic_year || Number(String(date).slice(0, 4)),
      preferredAssignmentId: rootAssignmentId,
    });
    if (!historical) return config;

    config.url = canonicalBase(url.split('/check-date/')[0]);
    config.params = {
      class_id: classId,
      component_id: componentId,
      date,
      assignment_id: historical.assignment_id,
    };
    config.__contentDvdCheckDate = true;
    return config;
  }

  // Consulta de uma data específica anterior ao cutover deve usar o history
  // bridge canônico; uma listagem sem data continua com o bridge normal.
  if (method === 'get' && /\/learning-objects\/?(?:\?|$)/.test(url)) {
    const original = { ...(config.params || {}) };
    const componentId = original.course_id || original.component_id || null;
    if (!original.class_id || !componentId || !original.date) return config;

    const historical = await resolveHistoricalAssignment(config, {
      classId: original.class_id,
      componentId,
      date: original.date,
      academicYear: original.academic_year,
      preferredAssignmentId: rootAssignmentId,
    });
    if (!historical) return config;

    config.url = canonicalBase(url);
    config.params = {
      class_id: original.class_id,
      component_id: componentId,
      date: original.date,
      assignment_id: historical.assignment_id,
    };
    config.__contentDvdList = {
      academicYear: original.academic_year,
      month: original.month,
      classId: original.class_id,
      primaryAssignmentId: historical.assignment_id,
      siblings: [],
    };
    return config;
  }

  if (method === 'post' && /\/learning-objects\/?$/.test(url)) {
    const payload = { ...(config.data || {}) };
    const componentId = payload.component_id || payload.course_id || null;
    const historical = await resolveHistoricalAssignment(config, {
      classId: payload.class_id,
      componentId,
      date: payload.date,
      academicYear: payload.academic_year,
      preferredAssignmentId: rootAssignmentId,
    });
    if (!historical) return config;

    payload.assignment_id = historical.assignment_id;
    payload.component_id = componentId;
    config.url = canonicalBase(url);
    config.data = payload;
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (isCopyUrl(url) && method === 'post') {
    const body = { ...(config.data || {}) };
    const sourceId = url.split('/').filter(Boolean).slice(-2, -1)[0];
    const current = recordCache.get(sourceId);
    const targetDate = body.target_date || current?.date || '';
    const targetAcademicYear =
      current?.academic_year || Number(String(targetDate).slice(0, 4)) || new Date().getFullYear();

    const historical = await resolveHistoricalAssignment(config, {
      classId: body.target_class_id,
      componentId: body.target_course_id,
      date: targetDate,
      academicYear: targetAcademicYear,
    });
    if (!historical) return config;

    const sourceAssignmentId =
      current?.assignment_id || current?.history_assignment_id || rootAssignmentId || null;

    config.url = canonicalBase(url);
    config.data = {
      ...body,
      source_assignment_id: sourceAssignmentId,
      target_assignment_id: historical.assignment_id,
    };
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  return config;
});

axios.interceptors.response.use((response) => {
  const url = String(response?.config?.url || '');
  if (!url.includes('/learning-objects') && !url.includes('/content-entries')) {
    return response;
  }

  const data = response.data;
  if (Array.isArray(data)) {
    data.forEach(cacheRecord);
  } else if (Array.isArray(data?.items)) {
    data.items.forEach(cacheRecord);
  } else if (data?.record) {
    cacheRecord(data.record);
  } else {
    cacheRecord(data);
  }

  return response;
});
