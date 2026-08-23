import React from 'react';
import { AlertTriangle, CalendarDays, Download, FileText, ShieldCheck, X } from 'lucide-react';

const STATUS_LABELS = {
  draft: 'Em elaboração',
  active: 'Vigente',
  review: 'Em revisão',
  closed: 'Encerrado',
  cancelled: 'Cancelado',
};

const DAY_LABELS = {
  segunda: 'Segunda-feira',
  'segunda-feira': 'Segunda-feira',
  terca: 'Terça-feira',
  'terça': 'Terça-feira',
  'terca-feira': 'Terça-feira',
  'terça-feira': 'Terça-feira',
  quarta: 'Quarta-feira',
  'quarta-feira': 'Quarta-feira',
  quinta: 'Quinta-feira',
  'quinta-feira': 'Quinta-feira',
  sexta: 'Sexta-feira',
  'sexta-feira': 'Sexta-feira',
};

function text(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (Array.isArray(value)) return value.filter(Boolean).join(', ') || '-';
  if (typeof value === 'object') return value.descricao || value.description || '-';
  return String(value);
}

function descriptions(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === 'string' ? item : item?.descricao || item?.description))
    .filter(Boolean);
}

function ReadField({ label, value, wide = false }) {
  if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
    return null;
  }
  return (
    <div className={wide ? 'md:col-span-2' : ''}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-sm text-gray-800 whitespace-pre-wrap">{text(value)}</div>
    </div>
  );
}

function ReadList({ label, items }) {
  const values = descriptions(items);
  if (!values.length) return null;
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-1">{label}</div>
      <ul className="list-disc pl-5 space-y-1 text-sm text-gray-800">
        {values.map((item, index) => <li key={`${label}-${index}`}>{item}</li>)}
      </ul>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="border rounded-lg p-4 bg-white">
      <h4 className="font-semibold text-gray-900 mb-3">{title}</h4>
      {children}
    </section>
  );
}

export default function PlanoAEEEffectiveViewer({ payload, onClose, onGeneratePdf }) {
  if (!payload) return null;

  const error = payload.effective_error;
  const dossier = payload.effective_dossier;
  const version = payload.effective_version;
  const source = payload.effective_source;

  const lifecycle = dossier?.lifecycle || {};
  const studyCase = dossier?.study_case || {};
  const paee = dossier?.paee || {};
  const pei = dossier?.pei || {};
  const schedule = dossier?.schedule || {};
  const sessions = Array.isArray(schedule?.sessions) ? schedule.sessions : [];

  const sourceLabel = source === 'sidecar_active'
    ? 'Snapshot V2 vigente'
    : source === 'legacy'
      ? 'Projeção efetiva do Plano legado'
      : 'Fonte Efetiva indisponível';

  const lifecycleLabel = error
    ? 'Integridade pendente'
    : STATUS_LABELS[lifecycle?.status] || lifecycle?.status || '-';

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      data-testid="effective-plan-viewer-overlay"
    >
      <div
        className="bg-white rounded-xl shadow-2xl max-w-5xl w-full max-h-[92vh] overflow-y-auto"
        onClick={(event) => event.stopPropagation()}
        data-testid="effective-plan-viewer"
      >
        <div className="sticky top-0 z-10 bg-white border-b px-6 py-4 flex justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileText size={20} className="text-indigo-600" />
              <h3 className="text-lg font-semibold text-gray-900">Visualização do Plano AEE</h3>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                <ShieldCheck size={12} />
                {sourceLabel}
              </span>
              {source === 'sidecar_active' && version?.document_version != null && (
                <span className="px-2 py-1 rounded-full bg-green-50 text-green-700 border border-green-200" data-testid="effective-plan-version">
                  v{version.document_version}.r{version.revision}
                </span>
              )}
              <span
                className={`px-2 py-1 rounded-full border ${error ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-gray-50 text-gray-700 border-gray-200'}`}
                data-testid="effective-plan-status"
              >
                {lifecycleLabel}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Fechar">
            <X size={24} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && (
            <div className="flex items-start gap-3 p-4 rounded-lg border border-amber-200 bg-amber-50" data-testid="effective-plan-integrity-warning">
              <AlertTriangle size={20} className="text-amber-700 mt-0.5" />
              <div>
                <div className="font-semibold text-amber-900">Integridade da Fonte Efetiva pendente</div>
                <div className="text-sm text-amber-800 mt-1">{error.message || 'O sistema não pode afirmar qual versão do Plano está vigente.'}</div>
                <div className="text-xs text-amber-700 mt-1">Código: {error.code || 'AEE_V2_INTEGRITY_ERROR'}</div>
              </div>
            </div>
          )}

          {error || !dossier ? (
            <Section title="Referência histórica">
              <div className="grid md:grid-cols-2 gap-3">
                <ReadField label="Estudante" value={payload.student_name} />
                <ReadField label="Ano letivo" value={payload.academic_year} />
                <ReadField label="Público-alvo" value={payload.publico_alvo?.replace?.(/_/g, ' ') || payload.publico_alvo} />
                <ReadField label="Situação armazenada no legado" value={payload.status} />
              </div>
              <p className="mt-3 text-xs text-gray-500">
                Estes dados são exibidos apenas como referência histórica; não representam uma Fonte Efetiva confirmada.
              </p>
            </Section>
          ) : (
            <>
              <Section title="Identificação e vigência">
                <div className="grid md:grid-cols-2 gap-3">
                  <ReadField label="Estudante" value={payload.student_name} />
                  <ReadField label="Ano letivo" value={dossier.academic_year} />
                  <ReadField label="Público-alvo" value={dossier.publico_alvo?.replace?.(/_/g, ' ') || dossier.publico_alvo} />
                  <ReadField label="Situação efetiva" value={lifecycleLabel} />
                  <ReadField label="Professor AEE" value={dossier.professor_aee_responsavel_nome} />
                  <ReadField label="Professor regente" value={dossier.professor_regente_nome} />
                  <ReadField label="Turma de origem" value={dossier.turma_origem_nome} />
                  <ReadField label="Escola de origem" value={dossier.escola_origem_nome} />
                  <ReadField label="Elaboração" value={lifecycle.elaborated_at} />
                  <ReadField label="Revisão" value={lifecycle.review_at} />
                  <ReadField label="Vigência inicial" value={lifecycle.effective_from} />
                  <ReadField label="Vigência final" value={lifecycle.effective_to} />
                </div>
              </Section>

              <Section title="Estudo de Caso">
                <div className="grid md:grid-cols-2 gap-4">
                  <ReadField label="Demanda inicial e contexto" value={studyCase.demanda_inicial_contexto} wide />
                  <ReadField label="Potencialidades" value={studyCase.potencialidades} />
                  <ReadField label="Demandas de apoio" value={studyCase.demandas_apoio} />
                  <ReadField label="Comunicação e participação" value={studyCase.comunicacao_participacao} wide />
                  <ReadField label="Participação do estudante" value={studyCase.participacao_estudante} />
                  <ReadField label="Contribuições da família" value={studyCase.contribuicoes_familia} />
                </div>
                <div className="mt-4"><ReadList label="Barreiras/contextos" items={studyCase.barreiras_contexto} /></div>
              </Section>

              <Section title="PAEE">
                <div className="space-y-4">
                  <ReadList label="Barreiras prioritárias" items={paee.barreiras_prioritarias} />
                  <ReadList label="Objetivos" items={paee.objetivos} />
                  <ReadList label="Materiais e recursos" items={paee.materiais_recursos} />
                </div>
              </Section>

              <Section title="PEI">
                <div className="grid md:grid-cols-2 gap-4">
                  <ReadField label="Atividades do AEE" value={pei.atividades_aee} wide />
                  <ReadField label="Articulação com sala comum" value={pei.articulacao_sala_comum} wide />
                  <ReadField label="Acessibilidade curricular" value={pei.acessibilidade_curricular} wide />
                  <ReadField label="Acessibilidade didático-pedagógica" value={pei.acessibilidade_didatico_pedagogica} wide />
                  <ReadField label="Acessibilidade avaliativa" value={pei.acessibilidade_avaliativa} wide />
                  <ReadField label="Estratégias de acompanhamento" value={pei.estrategias_acompanhamento_monitoramento} wide />
                </div>
              </Section>

              <Section title="Agenda / Cronograma">
                <div className="flex items-center gap-2 text-sm text-gray-700 mb-3">
                  <CalendarDays size={16} />
                  <span>Carga horária semanal: {text(schedule.carga_horaria_semanal)}</span>
                </div>
                {sessions.length === 0 ? (
                  <p className="text-sm text-gray-500">Nenhuma sessão registrada.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm border">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left">Dia</th>
                          <th className="px-3 py-2 text-left">Horário</th>
                          <th className="px-3 py-2 text-left">Local</th>
                          <th className="px-3 py-2 text-left">Modalidade</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {sessions.map((session, index) => (
                          <tr key={`${session.weekday || 'dia'}-${index}`}>
                            <td className="px-3 py-2">{DAY_LABELS[String(session.weekday || '').toLowerCase()] || text(session.weekday)}</td>
                            <td className="px-3 py-2">{session.start || '-'}{session.end ? ` – ${session.end}` : ''}</td>
                            <td className="px-3 py-2">{text(session.local)}</td>
                            <td className="px-3 py-2">{text(session.modalidade)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>
            </>
          )}
        </div>

        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-3 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-100">
            Fechar
          </button>
          <button
            onClick={() => onGeneratePdf?.(payload)}
            data-testid="btn-gerar-pdf-plano"
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 inline-flex items-center gap-2"
          >
            <Download size={14} />
            Gerar PDF (Imprimir / Salvar)
          </button>
        </div>
      </div>
    </div>
  );
}
