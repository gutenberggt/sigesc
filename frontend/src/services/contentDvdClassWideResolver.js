import axios from 'axios';

// P0 21/08/2026 — compatibilidade entre o bridge legado de Objetos de
// Conhecimento e o contrato canônico DVD. No backend, assignment com
// component_id=null autoriza qualquer componente da turma. O bridge original
// filtrava por igualdade estrita e, por isso, deixava algumas escritas caírem
// indevidamente em /learning-objects.

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

const isActiveOnDate = (diary, date) => {
  if (!date) return true;
  const target = String(date).slice(0, 10);
  const start = String(diary?.valid_from || '').slice(0, 10);
  const end = String(diary?.valid_until || '').slice(0, 10);
  return (!start || start <= target) && (!end || target <= end);
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

// Retorna fallback SOMENTE quando o bridge original falharia por existir apenas
// vínculo class-wide. Se houver vínculo específico do componente, ele tem
// precedência e o fluxo original continua responsável pela resolução.
const resolveClassWideFallback = async (
  config,
  { classId, componentId, date, academicYear }
) => {
  if (!classId || !componentId) return null;

  const diaries = await loadDiaries(config, academicYear);
  const eligible = diaries.filter((item) => (
    item?.class_id === classId &&
    item?.capabilities?.content_enabled === true &&
    isActiveOnDate(item, date)
  ));

  const exactCandidates = eligible.filter((item) => item?.component_id === componentId);
  if (exactCandidates.length > 0) return null;

  const classWideCandidates = eligible.filter((item) => !item?.component_id);
  if (classWideCandidates.length === 0) return null;
  if (classWideCandidates.length > 1) {
    throw bridgeError(
      'DVD_CONTENT_ASSIGNMENT_AMBIGUOUS',
      'Há mais de um vínculo class-wide de conteúdo válido para esta turma. Abra o registro a partir de Meus Diários.'
    );
  }

  return classWideCandidates[0];
};

const cacheRecord = (record) => {
  if (!record?.id) return;
  recordCache.set(record.id, {
    ...record,
    course_id: record.course_id || record.component_id || null,
    component_id: record.component_id || record.course_id || null,
  });
};

// IMPORTANTE: este interceptor é registrado DEPOIS de contentDvdBridge.
// Axios executa request interceptors em ordem inversa; portanto esta camada
// corrige exclusivamente o caso class-wide antes que o bridge antigo aplique o
// filtro estrito. Nos demais cenários, devolve a requisição intacta.
axios.interceptors.request.use(async (config) => {
  if (config.__skipContentDvdBridge) return config;
  const url = String(config.url || '');
  if (!isLearningObjectsUrl(url) || isPdfUrl(url)) return config;

  const method = String(config.method || 'get').toLowerCase();

  if (isCheckDateUrl(url) && method === 'get') {
    const match = url.match(/\/learning-objects\/check-date\/([^/]+)\/([^/]+)\/([^/?]+)/);
    if (!match) return config;

    const classId = decodeURIComponent(match[1]);
    const componentId = decodeURIComponent(match[2]);
    const date = decodeURIComponent(match[3]);
    const fallback = await resolveClassWideFallback(config, {
      classId,
      componentId,
      date,
      academicYear: config.params?.academic_year,
    });
    if (!fallback) return config;

    config.url = canonicalBase(url.split('/check-date/')[0]);
    config.params = {
      class_id: classId,
      component_id: componentId,
      date,
      assignment_id: fallback.assignment_id,
    };
    config.__contentDvdCheckDate = true;
    return config;
  }

  if (method === 'get' && /\/learning-objects\/?(?:\?|$)/.test(url)) {
    const original = { ...(config.params || {}) };
    const classId = original.class_id;
    const componentId = original.course_id || original.component_id || null;
    if (!componentId) return config;

    const fallback = await resolveClassWideFallback(config, {
      classId,
      componentId,
      date: original.date,
      academicYear: original.academic_year,
    });
    if (!fallback) return config;

    config.url = canonicalBase(url);
    config.params = {
      class_id: classId,
      component_id: componentId,
      date: original.date,
      assignment_id: fallback.assignment_id,
    };
    Object.keys(config.params).forEach((key) => {
      if (config.params[key] === undefined || config.params[key] === null || config.params[key] === '') {
        delete config.params[key];
      }
    });
    config.__contentDvdList = {
      academicYear: original.academic_year,
      month: original.month,
      classId,
      primaryAssignmentId: fallback.assignment_id,
      siblings: [],
    };
    return config;
  }

  if (method === 'post' && /\/learning-objects\/?$/.test(url)) {
    const payload = { ...(config.data || {}) };
    const componentId = payload.component_id || payload.course_id || null;
    const fallback = await resolveClassWideFallback(config, {
      classId: payload.class_id,
      componentId,
      date: payload.date,
      academicYear: payload.academic_year,
    });
    if (!fallback) return config;

    payload.assignment_id = fallback.assignment_id;
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

    const fallback = await resolveClassWideFallback(config, {
      classId: body.target_class_id,
      componentId: body.target_course_id,
      date: targetDate,
      academicYear: targetAcademicYear,
    });
    if (!fallback) return config;

    const sourceAssignmentId =
      current?.assignment_id || current?.history_assignment_id || getRootAssignmentId() || null;

    config.url = canonicalBase(url);
    config.data = {
      ...body,
      source_assignment_id: sourceAssignmentId,
      target_assignment_id: fallback.assignment_id,
    };
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  return config;
});

// Como este interceptor de resposta é registrado depois do bridge principal,
// ele observa a forma final já normalizada e mantém cache mínimo apenas para
// resolver a origem da cópia quando o destino usa vínculo class-wide.
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
