import axios from 'axios';

const getAssignmentId = () => {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('assignment_id') || '';
};

const isProfessorContentPage = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname === '/professor/objetos-conhecimento';
};

const isLearningObjectsUrl = (url = '') => url.includes('/learning-objects');
const isPdfUrl = (url = '') => url.includes('/learning-objects/pdf/');
const isCheckDateUrl = (url = '') => url.includes('/learning-objects/check-date/');
const isCopyUrl = (url = '') => url.includes('/copy-to-class');

const canonicalBase = (url = '') => url.replace('/learning-objects', '/content-entries');
const canonicalRoot = (url = '') => {
  const prefix = url.split('/content-entries')[0];
  return `${prefix}/content-entries`;
};
const apiRoot = (url = '') => url.split('/learning-objects')[0];

const recordCache = new Map();
const diaryCache = new Map();

const normalizeRecord = (record = {}) => ({
  ...record,
  course_id: record.course_id || record.component_id || null,
  component_id: record.component_id || record.course_id || null,
  source: record.source || 'content_entries',
  legacy: record.legacy === true,
  read_only: record.read_only === true,
});

const withHistoryAssignment = (record = {}, historyAssignmentId = '') => ({
  ...record,
  history_assignment_id: record.assignment_id || record.history_assignment_id || historyAssignmentId || null,
});

const cacheRecords = (records = []) => {
  records.forEach((record) => {
    if (record?.id) recordCache.set(record.id, normalizeRecord(record));
  });
};

const filterByLegacyListParams = (items, meta = {}) => {
  const { academicYear, month } = meta;
  return items.filter((item) => {
    if (academicYear && Number(item.academic_year) !== Number(academicYear)) return false;
    if (month) {
      const m = Number(String(item.date || '').slice(5, 7));
      if (m !== Number(month)) return false;
    }
    return true;
  });
};

const correctionNote = 'Correção realizada pelo Diário de Conteúdos por Vínculo.';
const legacyReadOnlyMessage = 'Este conteúdo pertence ao histórico anterior ao Diário por Vínculo e está disponível somente para consulta.';

const isLegacyReadOnly = (record) => Boolean(record?.legacy || record?.read_only || record?.source === 'learning_objects');

const rejectLegacyWrite = () => {
  const error = new Error(legacyReadOnlyMessage);
  error.response = {
    status: 409,
    data: {
      detail: {
        code: 'DVD_LEGACY_CONTENT_READ_ONLY',
        message: legacyReadOnlyMessage,
      },
    },
  };
  return Promise.reject(error);
};

const bridgeError = (code, message, status = 409) => {
  const error = new Error(message);
  error.response = { status, data: { detail: { code, message } } };
  return error;
};

const cachedLegacyAdapter = (record) => async (config) => ({
  data: record,
  status: 200,
  statusText: 'OK',
  headers: {},
  config,
  request: null,
});

const isActiveOnDate = (diary, date) => {
  if (!date) return true;
  const d = String(date).slice(0, 10);
  const start = String(diary?.valid_from || '').slice(0, 10);
  const end = String(diary?.valid_until || '').slice(0, 10);
  return (!start || start <= d) && (!end || d <= end);
};

const loadDiaries = async (config, academicYear) => {
  const year = Number(academicYear) || new Date().getFullYear();
  const root = apiRoot(config.url || '');
  const key = `${root}|${year}`;
  if (diaryCache.has(key)) return diaryCache.get(key);

  try {
    const response = await axios.get(`${root}/professor/diarios`, {
      params: { academic_year: year },
      headers: config.headers,
      __skipContentDvdBridge: true,
    });
    const items = Array.isArray(response.data?.items) ? response.data.items : [];
    diaryCache.set(key, items);
    return items;
  } catch (error) {
    // Usuários não-professores ou turmas sem DVD continuam no fluxo legado.
    diaryCache.set(key, []);
    return [];
  }
};

const contentDiariesFor = async (config, { classId, componentId, date, academicYear }) => {
  if (!classId) return [];
  const diaries = await loadDiaries(config, academicYear);
  return diaries.filter((diary) => {
    if (diary?.class_id !== classId) return false;
    if (!diary?.capabilities?.content_enabled) return false;
    if (componentId && diary?.component_id !== componentId) return false;
    return isActiveOnDate(diary, date);
  });
};

const resolveAssignment = async (
  config,
  { classId, componentId, date, academicYear, preferredAssignmentId }
) => {
  const candidates = await contentDiariesFor(config, {
    classId, componentId, date, academicYear,
  });
  if (preferredAssignmentId) {
    const preferred = candidates.find((item) => item.assignment_id === preferredAssignmentId);
    if (preferred) return preferred.assignment_id;
  }
  if (candidates.length === 1) return candidates[0].assignment_id;
  if (candidates.length === 0) return '';
  throw bridgeError(
    'DVD_CONTENT_ASSIGNMENT_AMBIGUOUS',
    'Há mais de um vínculo de conteúdo válido para esta turma/componente. Abra o registro a partir de Meus Diários.'
  );
};

const shouldAttemptDvd = (rootAssignmentId) => Boolean(rootAssignmentId || isProfessorContentPage());

// Bridge contextual: com assignment_id usa o vínculo explícito; no atalho genérico
// do professor, resolve somente vínculos que o endpoint /professor/diarios já autorizou.
axios.interceptors.request.use(async (config) => {
  if (config.__skipContentDvdBridge) return config;
  if (!isLearningObjectsUrl(config.url) || isPdfUrl(config.url)) return config;

  const rootAssignmentId = getAssignmentId();
  if (!shouldAttemptDvd(rootAssignmentId)) return config;

  const method = (config.method || 'get').toLowerCase();
  const url = config.url || '';

  if (isCheckDateUrl(url) && method === 'get') {
    const match = url.match(/\/learning-objects\/check-date\/([^/]+)\/([^/]+)\/([^/?]+)/);
    if (!match) return config;
    const classId = decodeURIComponent(match[1]);
    const componentId = decodeURIComponent(match[2]);
    const date = decodeURIComponent(match[3]);
    const assignmentId = await resolveAssignment(config, {
      classId,
      componentId,
      date,
      academicYear: config.params?.academic_year,
      preferredAssignmentId: rootAssignmentId,
    });
    if (!assignmentId) return config;
    config.url = canonicalBase(url.split('/check-date/')[0]);
    config.params = {
      class_id: classId,
      component_id: componentId,
      date,
      assignment_id: assignmentId,
    };
    config.__contentDvdCheckDate = true;
    return config;
  }

  // GET de lista: para Anos Iniciais/Infantil, uma consulta sem componente
  // agrega todos os assignments de conteúdo do professor na mesma turma.
  if (method === 'get' && /\/learning-objects\/?(?:\?|$)/.test(url)) {
    const original = { ...(config.params || {}) };
    const classId = original.class_id;
    const componentId = original.course_id || original.component_id || null;
    const academicYear = original.academic_year;
    const candidates = await contentDiariesFor(config, {
      classId,
      componentId,
      date: original.date,
      academicYear,
    });

    if (candidates.length === 0) return config;

    let primary = candidates[0];
    if (rootAssignmentId) {
      primary = candidates.find((item) => item.assignment_id === rootAssignmentId) || primary;
    }

    config.url = canonicalBase(url);
    config.params = {
      class_id: classId,
      component_id: componentId || primary.component_id,
      date: original.date,
      assignment_id: primary.assignment_id,
    };
    Object.keys(config.params).forEach((key) => {
      if (config.params[key] === undefined || config.params[key] === null || config.params[key] === '') {
        delete config.params[key];
      }
    });
    config.__contentDvdList = {
      academicYear,
      month: original.month,
      classId,
      primaryAssignmentId: primary.assignment_id,
      siblings: componentId
        ? []
        : candidates
            .filter((item) => item.assignment_id !== primary.assignment_id)
            .map((item) => ({
              assignment_id: item.assignment_id,
              component_id: item.component_id,
            })),
    };
    return config;
  }

  // GET individual. Itens legados já recebidos na listagem são servidos do
  // cache local somente para visualização; nunca são convertidos em content_entry.
  if (method === 'get') {
    const id = url.split('/').filter(Boolean).pop();
    const current = recordCache.get(id);
    if (isLegacyReadOnly(current)) {
      config.adapter = cachedLegacyAdapter(current);
      config.__contentDvdRecord = true;
      return config;
    }
    if (!current && !rootAssignmentId) return config;
    config.url = canonicalBase(url);
    config.__contentDvdRecord = true;
    return config;
  }

  // A tela histórica entende "Salvar" como lançamento concluído. Cada componente
  // recebe o assignment correspondente, inclusive na seleção múltipla dos Anos Iniciais.
  if (method === 'post' && /\/learning-objects\/?$/.test(url)) {
    const payload = { ...(config.data || {}) };
    const componentId = payload.component_id || payload.course_id || null;
    const assignmentId = await resolveAssignment(config, {
      classId: payload.class_id,
      componentId,
      date: payload.date,
      academicYear: payload.academic_year,
      preferredAssignmentId: rootAssignmentId,
    });
    if (!assignmentId) return config;
    payload.assignment_id = assignmentId;
    payload.component_id = componentId;
    config.url = canonicalBase(url);
    config.data = payload;
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (isCopyUrl(url) && method === 'post') {
    const id = url.split('/').filter(Boolean).slice(-2, -1)[0];
    const current = recordCache.get(id);
    // Sem contexto DVD explícito/canonizado, a cópia permanece no endpoint legado.
    // O backend revalida teacher_assignments, tenant, conflito e ano letivo.
    if (!current && !rootAssignmentId) return config;

    const body = { ...(config.data || {}) };
    const targetDate = body.target_date || current?.date || '';
    const targetAcademicYear =
      current?.academic_year || Number(String(targetDate).slice(0, 4)) || new Date().getFullYear();
    const sourceAssignmentId =
      current?.assignment_id || current?.history_assignment_id || rootAssignmentId || null;

    const targetAssignmentId = await resolveAssignment(config, {
      classId: body.target_class_id,
      componentId: body.target_course_id,
      date: targetDate,
      academicYear: targetAcademicYear,
      preferredAssignmentId: '',
    });
    if (!targetAssignmentId) {
      throw bridgeError(
        'CONTENT_COPY_TARGET_ASSIGNMENT_REQUIRED',
        'Você não possui vínculo de conteúdo com a turma/componente de destino.',
        403
      );
    }
    config.url = canonicalBase(url);
    config.data = {
      ...body,
      source_assignment_id: sourceAssignmentId,
      target_assignment_id: targetAssignmentId,
    };
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (method === 'put') {
    const id = url.split('/').filter(Boolean).pop();
    const current = recordCache.get(id);
    if (!current) {
      throw bridgeError('CONTENT_RELOAD_REQUIRED', 'Recarregue o conteúdo antes de editar.');
    }
    if (isLegacyReadOnly(current)) return rejectLegacyWrite();

    const patch = { ...(config.data || {}) };
    const recordAssignmentId = current.assignment_id || await resolveAssignment(config, {
      classId: current.class_id,
      componentId: current.course_id || current.component_id,
      date: current.date,
      academicYear: current.academic_year,
      preferredAssignmentId: rootAssignmentId,
    });

    if (current.status === 'published' || current.status === 'corrected') {
      config.method = 'post';
      config.url = `${canonicalRoot(canonicalBase(url))}/${id}/correct`;
      config.data = {
        change_note: correctionNote,
        expected_version: current.version ?? null,
        content: patch.content ?? current.content ?? '',
        methodology: patch.methodology ?? current.methodology ?? null,
        observations: patch.observations ?? current.observations ?? null,
        number_of_classes: patch.number_of_classes ?? current.number_of_classes ?? 1,
      };
      config.__contentDvdRecord = true;
      return config;
    }

    config.method = 'post';
    config.url = canonicalRoot(canonicalBase(url));
    config.data = {
      class_id: current.class_id,
      course_id: current.course_id || current.component_id,
      component_id: current.component_id || current.course_id,
      date: current.date,
      academic_year: current.academic_year,
      aula_numero: current.aula_numero ?? null,
      number_of_classes: patch.number_of_classes ?? current.number_of_classes ?? 1,
      content: patch.content ?? current.content ?? '',
      methodology: patch.methodology ?? current.methodology ?? null,
      observations: patch.observations ?? current.observations ?? null,
      expected_version: current.version ?? null,
      assignment_id: recordAssignmentId,
    };
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (method === 'delete') {
    const id = url.split('/').filter(Boolean).pop();
    const current = recordCache.get(id);
    if (isLegacyReadOnly(current)) return rejectLegacyWrite();
    if (!current && !rootAssignmentId) return config;

    config.url = canonicalBase(url);
    config.data = {
      change_note: 'Exclusão realizada pelo Diário de Conteúdos por Vínculo.',
    };
    config.__contentDvdDelete = true;
    return config;
  }

  return config;
});

axios.interceptors.response.use(async (response) => {
  const config = response.config || {};

  if (config.__contentDvdList) {
    const primaryHistoryAssignmentId =
      response.data?.history_bridge?.assignment_id || config.__contentDvdList.primaryAssignmentId || '';
    const raw = Array.isArray(response.data?.items)
      ? response.data.items.map((item) => withHistoryAssignment(item, primaryHistoryAssignmentId))
      : [];
    const combined = [...raw];

    for (const sibling of config.__contentDvdList.siblings || []) {
      const siblingResponse = await axios.get(canonicalRoot(config.url), {
        params: {
          class_id: config.__contentDvdList.classId,
          component_id: sibling.component_id,
          assignment_id: sibling.assignment_id,
        },
        headers: config.headers,
        __skipContentDvdBridge: true,
      });
      if (Array.isArray(siblingResponse.data?.items)) {
        combined.push(
          ...siblingResponse.data.items.map((item) => withHistoryAssignment(item, sibling.assignment_id))
        );
      }
    }

    const unique = new Map();
    combined.map(normalizeRecord).forEach((item) => {
      const key = `${item.source || ''}|${item.id || ''}|${item.component_id || item.course_id || ''}`;
      unique.set(key, item);
    });
    const items = filterByLegacyListParams(
      [...unique.values()],
      config.__contentDvdList
    );
    cacheRecords(items);
    response.data = items;
    return response;
  }

  if (config.__contentDvdCheckDate) {
    const historyAssignmentId = response.data?.history_bridge?.assignment_id || config.params?.assignment_id || '';
    const raw = Array.isArray(response.data?.items)
      ? response.data.items.map((item) => withHistoryAssignment(item, historyAssignmentId))
      : [];
    const items = raw.map(normalizeRecord);
    cacheRecords(items);
    response.data = {
      has_record: items.length > 0,
      record: items[0] || null,
    };
    return response;
  }

  if (config.__contentDvdAutoPublish && response.data?.id) {
    const draft = normalizeRecord(response.data);
    if (draft.status === 'draft') {
      const publishResponse = await axios.post(
        `${canonicalRoot(config.url)}/${draft.id}/publish`,
        { expected_version: draft.version ?? null },
        { __skipContentDvdBridge: true }
      );
      const published = normalizeRecord(publishResponse.data);
      cacheRecords([published]);
      response.data = published;
      return response;
    }
  }

  if (config.__contentDvdRecord && response.data) {
    const record = normalizeRecord(response.data);
    cacheRecords([record]);
    response.data = record;
  }

  return response;
});
