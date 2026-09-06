import axios from 'axios';
import {
  mergeLegacyAndCanonicalVisibility,
  normalizeCanonicalVisibilityRecord,
  selectCanonicalVisibilityRecords,
  shouldComposeLegacyCanonicalFallback,
} from './contentLegacyCanonicalVisibilityPolicy';

// R2.0g.4 — compatibilidade de leitura para conteúdo canônico sem assignment.
//
// O assistente administrativo grava sempre em content_entries. Em uma turma que
// ainda opera pelo fluxo legado, o contentDvdBridge mantém GET /learning-objects
// quando /professor/diarios não entrega candidato DVD. Esta camada, registrada
// depois dos bridges DVD, preserva a resposta legada e acrescenta somente os
// content_entries sem assignment_id da MESMA turma/componente/período.
//
// Nenhum dado é migrado ou duplicado por esta ponte. Se um item canônico assim
// composto for editado/excluído pelo formulário histórico, a operação continua
// exclusivamente nos endpoints canônicos.

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
const canonicalRoot = (url = '') => {
  const value = String(url || '');
  if (value.includes('/content-entries')) {
    return `${value.split('/content-entries')[0]}/content-entries`;
  }
  return `${apiRoot(value)}/content-entries`;
};

const cacheCanonical = (records = []) => {
  records.forEach((record) => {
    if (record?.id) canonicalCache.set(record.id, normalizeCanonicalVisibilityRecord(record));
  });
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

  // Defesa em profundidade: mesmo que o endpoint canônico retorne algo além do
  // filtro solicitado, a composição local exige novamente turma + componente +
  // data/ano/mês e ausência de assignment. Outros componentes jamais entram.
  return selectCanonicalVisibilityRecords(items, meta);
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

  const id = url.includes('/learning-objects/')
    ? url.split('/').filter(Boolean).pop()
    : '';
  const current = id ? canonicalCache.get(id) : null;
  if (!current) return config;

  // O item veio da composição canônica no fluxo legado. A partir daqui nenhum
  // acesso individual pode voltar para learning_objects.
  if (method === 'get') {
    config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`;
    config.__skipContentDvdBridge = true;
    config.__legacyCanonicalRecord = true;
    return config;
  }

  if (method === 'put') {
    const patch = { ...(config.data || {}) };
    if (current.status === 'published' || current.status === 'corrected') {
      config.method = 'post';
      config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}/correct`;
      config.data = {
        change_note: 'Correção realizada pelo formulário histórico sobre conteúdo canônico.',
        expected_version: current.version ?? null,
        content: patch.content ?? current.content ?? '',
        methodology: patch.methodology ?? current.methodology ?? null,
        observations: patch.observations ?? current.observations ?? null,
        number_of_classes: patch.number_of_classes ?? current.number_of_classes ?? 1,
      };
      config.__skipContentDvdBridge = true;
      config.__legacyCanonicalRecord = true;
      return config;
    }

    config.method = 'post';
    config.url = canonicalRoot(url);
    config.data = {
      class_id: current.class_id,
      course_id: current.course_id || current.component_id,
      component_id: current.component_id || current.course_id,
      date: current.date,
      academic_year: current.academic_year,
      aula_numero: current.aula_numero ?? null,
      teacher_id: current.teacher_id || null,
      assignment_id: null,
      number_of_classes: patch.number_of_classes ?? current.number_of_classes ?? 1,
      content: patch.content ?? current.content ?? '',
      methodology: patch.methodology ?? current.methodology ?? null,
      observations: patch.observations ?? current.observations ?? null,
      expected_version: current.version ?? null,
    };
    config.__skipContentDvdBridge = true;
    config.__legacyCanonicalRecord = true;
    config.__legacyCanonicalAutoPublish = true;
    return config;
  }

  if (method === 'delete') {
    config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`;
    config.data = {
      change_note: 'Exclusão realizada pelo formulário histórico sobre conteúdo canônico.',
    };
    config.__skipContentDvdBridge = true;
    config.__legacyCanonicalDelete = true;
    return config;
  }

  return config;
});

axios.interceptors.response.use(async (response) => {
  const config = response.config || {};
  const finalUrl = String(config.url || '');

  if (
    config.__legacyCanonicalVisibilityList &&
    shouldComposeLegacyCanonicalFallback(finalUrl)
  ) {
    const canonical = await loadCanonicalLegacyMode(config, config.__legacyCanonicalVisibilityList);
    cacheCanonical(canonical);
    const legacy = Array.isArray(response.data) ? response.data : [];
    response.data = mergeLegacyAndCanonicalVisibility(legacy, canonical);
    return response;
  }

  if (
    config.__legacyCanonicalVisibilityCheckDate &&
    shouldComposeLegacyCanonicalFallback(finalUrl)
  ) {
    if (response.data?.has_record) return response;
    const canonical = await loadCanonicalLegacyMode(config, config.__legacyCanonicalVisibilityCheckDate);
    cacheCanonical(canonical);
    if (canonical.length > 0) {
      response.data = { has_record: true, record: canonical[0] };
    }
    return response;
  }

  if (config.__legacyCanonicalAutoPublish && response.data?.id) {
    const draft = normalizeCanonicalVisibilityRecord(response.data);
    if (draft.status === 'draft') {
      const publish = await axios.post(
        `${canonicalRoot(config.url)}/${encodeURIComponent(draft.id)}/publish`,
        { expected_version: draft.version ?? null },
        { __skipContentDvdBridge: true }
      );
      const published = normalizeCanonicalVisibilityRecord(publish.data);
      cacheCanonical([published]);
      response.data = published;
      return response;
    }
  }

  if (config.__legacyCanonicalRecord && response.data?.id) {
    const record = normalizeCanonicalVisibilityRecord(response.data);
    cacheCanonical([record]);
    response.data = record;
  }

  if (config.__legacyCanonicalDelete && response.status >= 200 && response.status < 300) {
    const id = String(finalUrl).split('/').filter(Boolean).pop();
    canonicalCache.delete(id);
  }

  return response;
});
