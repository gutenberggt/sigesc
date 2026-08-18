import axios from 'axios';

const getAssignmentId = () => {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('assignment_id') || '';
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
const recordCache = new Map();

const normalizeRecord = (record = {}) => ({
  ...record,
  course_id: record.course_id || record.component_id || null,
  component_id: record.component_id || record.course_id || null,
  source: record.source || 'content_entries',
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

// Bridge estritamente contextual: sem assignment_id, o fluxo legado permanece intacto.
axios.interceptors.request.use((config) => {
  if (config.__skipContentDvdBridge) return config;
  const assignmentId = getAssignmentId();
  if (!assignmentId || !isLearningObjectsUrl(config.url) || isPdfUrl(config.url)) return config;

  const method = (config.method || 'get').toLowerCase();
  const url = config.url || '';

  if (isCopyUrl(url)) {
    const error = new Error('Cópia entre turmas ainda não está disponível no Diário por Vínculo.');
    error.response = {
      status: 409,
      data: { detail: 'Cópia entre turmas ainda não está disponível no Diário por Vínculo.' },
    };
    return Promise.reject(error);
  }

  if (isCheckDateUrl(url) && method === 'get') {
    const match = url.match(/\/learning-objects\/check-date\/([^/]+)\/([^/]+)\/([^/?]+)/);
    if (!match) return config;
    config.url = canonicalBase(url.split('/check-date/')[0]);
    config.params = {
      class_id: decodeURIComponent(match[1]),
      component_id: decodeURIComponent(match[2]),
      date: decodeURIComponent(match[3]),
      assignment_id: assignmentId,
    };
    config.__contentDvdCheckDate = true;
    return config;
  }

  // GET de lista: content_entries retorna {items,total}; mês/ano são filtrados
  // no response bridge, sem relaxar a filtragem/autorização server-side.
  if (method === 'get' && /\/learning-objects\/?(?:\?|$)/.test(url)) {
    const original = { ...(config.params || {}) };
    config.url = canonicalBase(url);
    config.params = {
      class_id: original.class_id,
      component_id: original.course_id || original.component_id,
      date: original.date,
      assignment_id: assignmentId,
    };
    Object.keys(config.params).forEach((key) => {
      if (config.params[key] === undefined || config.params[key] === null || config.params[key] === '') {
        delete config.params[key];
      }
    });
    config.__contentDvdList = {
      academicYear: original.academic_year,
      month: original.month,
    };
    return config;
  }

  // GET individual.
  if (method === 'get') {
    config.url = canonicalBase(url);
    config.__contentDvdRecord = true;
    return config;
  }

  // A tela histórica entende "Salvar" como lançamento concluído. No DVD, o
  // bridge cria/upserta o draft pelo motor canônico e o publica no response
  // interceptor, preservando esse contrato sem pular versionamento/auditoria.
  if (method === 'post' && /\/learning-objects\/?$/.test(url)) {
    const payload = { ...(config.data || {}) };
    payload.assignment_id = assignmentId;
    payload.component_id = payload.component_id || payload.course_id || null;
    config.url = canonicalBase(url);
    config.data = payload;
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (method === 'put') {
    const id = url.split('/').filter(Boolean).pop();
    const current = recordCache.get(id);
    if (!current) {
      const error = new Error('Recarregue o conteúdo antes de editar.');
      error.response = {
        status: 409,
        data: { detail: 'Recarregue o conteúdo antes de editar.' },
      };
      return Promise.reject(error);
    }
    const patch = { ...(config.data || {}) };

    // Conteúdo publicado/corrigido nunca volta para PUT/upsert: usa a rota
    // institucional de correção com motivo e expected_version.
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

    // Draft: upsert canônico e publicação imediata para manter a semântica da
    // tela atual de uma única ação "Salvar".
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
      assignment_id: assignmentId,
    };
    config.__contentDvdRecord = true;
    config.__contentDvdAutoPublish = true;
    return config;
  }

  if (method === 'delete') {
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
    const raw = Array.isArray(response.data?.items) ? response.data.items : [];
    const items = filterByLegacyListParams(raw.map(normalizeRecord), config.__contentDvdList);
    cacheRecords(items);
    response.data = items;
    return response;
  }

  if (config.__contentDvdCheckDate) {
    const raw = Array.isArray(response.data?.items) ? response.data.items : [];
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
