/**
 * BulletinViewer — Boletim Online MVP (Passo 5, Fev/2026).
 *
 * Princípio arquitetural (cf. /app/docs/ACADEMIC_EVENT_CONTRACT.md §21):
 * - READ-ONLY ABSOLUTO. Sem edição, sem mutação, sem ação administrativa.
 * - Boletim é PROJEÇÃO consumida do endpoint canônico
 *   GET /api/students/{id}/bulletin?academic_year=YYYY.
 * - Frontend NÃO infere lock/visibilidade. Backend já entrega tudo computado.
 *
 * Objetivo: validar modelo pedagógico antes de transformar em PDF oficial.
 * Sem PDF, sem assinatura, sem hash visível, sem QR, sem download, sem print.
 */
import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useAuth } from '@/contexts/AuthContext';
import { useStudentSearch } from '@/hooks/useStudentSearch';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Search, X, AlertCircle, Calendar, Stethoscope, BookOpen, GraduationCap } from 'lucide-react';
import { downloadBlob } from '@/utils/downloadBlob';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SOURCE_LABEL = {
  origin: 'Turma de Origem',
  destination: 'Turma de Destino',
  sole: 'Turma Única',
};
const EVENT_TYPE_LABEL = {
  transfer: 'Transferência',
  remanejamento: 'Remanejamento',
  reclassificacao: 'Reclassificação',
  progressao_parcial: 'Progressão Parcial',
};

function fmtGrade(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'number' ? v : parseFloat(String(v).replace(',', '.'));
  if (Number.isNaN(n)) return '—';
  return n.toFixed(1).replace('.', ',');
}

function fmtDate(s) {
  if (!s) return '';
  const [y, m, d] = String(s).slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

function SegmentHeader({ seg }) {
  const isOrigin = seg.source === 'origin';
  const isDestination = seg.source === 'destination';
  const eventType = seg.governing_event_type
    ? EVENT_TYPE_LABEL[seg.governing_event_type] || seg.governing_event_type
    : null;

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3 mb-3">
      <div>
        <div className="text-base font-semibold text-zinc-800">
          {seg.class?.name || '(turma sem nome)'}
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">
          {seg.school?.name || ''}
          {seg.class?.grade_level ? ` · ${seg.class.grade_level}` : ''}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-zinc-600 mt-2">
          <Calendar className="w-3.5 h-3.5" />
          <span>
            {fmtDate(seg.period_start)} → {fmtDate(seg.period_end)}
          </span>
        </div>
      </div>
      <div className="flex flex-col items-end gap-1">
        <Badge
          data-testid={`segment-source-badge-${seg.period_index}`}
          className={
            isOrigin
              ? 'bg-amber-100 text-amber-800 hover:bg-amber-100'
              : isDestination
              ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-100'
              : 'bg-zinc-100 text-zinc-800 hover:bg-zinc-100'
          }
        >
          {SOURCE_LABEL[seg.source] || seg.source}
        </Badge>
        {eventType && (
          <span className="text-[11px] text-zinc-500">
            {eventType}
            {seg.governing_effective_date && ` em ${fmtDate(seg.governing_effective_date)}`}
          </span>
        )}
        {seg.bimesters_owned?.length > 0 && (
          <span className="text-[11px] text-zinc-500" data-testid={`segment-bims-${seg.period_index}`}>
            Fecha bimestre(s): {seg.bimesters_owned.join(', ')}
          </span>
        )}
      </div>
    </div>
  );
}

function ComponentsTable({ components }) {
  if (!components?.length) {
    return (
      <div className="text-sm text-zinc-500 py-4 italic">
        Nenhum componente curricular vinculado neste período.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm" data-testid="bulletin-components-table">
        <thead className="text-xs uppercase tracking-wide text-zinc-500 bg-zinc-50">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Componente</th>
            <th className="text-center px-2 py-2 font-medium">B1</th>
            <th className="text-center px-2 py-2 font-medium">B2</th>
            <th className="text-center px-2 py-2 font-medium">B3</th>
            <th className="text-center px-2 py-2 font-medium">B4</th>
            <th className="text-center px-2 py-2 font-medium">Rec. 1ºS</th>
            <th className="text-center px-2 py-2 font-medium">Rec. 2ºS</th>
            <th className="text-center px-2 py-2 font-medium">Média</th>
            <th className="text-center px-2 py-2 font-medium">Faltas</th>
          </tr>
        </thead>
        <tbody>
          {components.map((c) => {
            const owned = new Set(c.bimesters_owned_by_this_period || []);
            const cell = (key, idx) => {
              const isOwned = owned.has(idx);
              return (
                <td
                  key={key}
                  className={
                    'text-center px-2 py-2 ' +
                    (isOwned ? 'font-semibold text-zinc-900' : 'text-zinc-400')
                  }
                  title={isOwned ? 'Bimestre fechado por esta turma' : 'Bimestre fechado em outra turma deste boletim'}
                >
                  {fmtGrade(c.grades?.[key])}
                </td>
              );
            };
            return (
              <tr key={c.course_id} className={'border-t' + (c._warning_duplicate_name ? ' bg-amber-50' : '')} data-testid={`bulletin-row-${c.course_id}`}>
                <td className="px-3 py-2">
                  <span className="text-zinc-800">{c.course_name}</span>
                  {c._warning_duplicate_name && (
                    <span
                      className="ml-2 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded"
                      title="Existe outro componente com o mesmo nome nesta turma. Verifique o cadastro."
                      data-testid={`bulletin-row-duplicate-warning-${c.course_id}`}
                    >
                      <AlertCircle className="w-3 h-3" />
                      Duplicidade
                    </span>
                  )}
                  {c.optativo && (
                    <span className="ml-2 text-[10px] text-zinc-500 uppercase">optativo</span>
                  )}
                  {c.atendimento_programa && c.atendimento_programa !== 'regular' && (
                    <span className="ml-2 text-[10px] text-purple-600 uppercase">{c.atendimento_programa}</span>
                  )}
                </td>
                {cell('b1', 1)}
                {cell('b2', 2)}
                {cell('b3', 3)}
                {cell('b4', 4)}
                <td className="text-center px-2 py-2 text-zinc-700">{fmtGrade(c.grades?.rec_s1)}</td>
                <td className="text-center px-2 py-2 text-zinc-700">{fmtGrade(c.grades?.rec_s2)}</td>
                <td className="text-center px-2 py-2 font-semibold text-zinc-900">
                  {fmtGrade(c.grades?.final_average)}
                </td>
                <td className="text-center px-2 py-2 text-zinc-700">
                  {c.absences_in_period ?? 0}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AttendanceRow({ summary }) {
  if (!summary) return null;
  return (
    <div className="text-xs text-zinc-600 mt-3 flex flex-wrap gap-x-4 gap-y-1">
      <span>Aulas registradas: <strong>{summary.total_records}</strong></span>
      <span>Presenças: <strong>{summary.present}</strong></span>
      <span>Faltas: <strong>{summary.absent}</strong></span>
      {summary.frequencia_pct !== null && (
        <span>
          Frequência:{' '}
          <strong className={summary.frequencia_pct < 75 ? 'text-red-600' : 'text-emerald-700'}>
            {summary.frequencia_pct.toFixed(1).replace('.', ',')}%
          </strong>
        </span>
      )}
    </div>
  );
}

function CurricularDiagnoseModal({ open, onClose, classId, mantId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!open || !classId) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    const token = sessionStorage.getItem('accessToken') || localStorage.getItem('accessToken');
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (mantId) headers['X-Mantenedora-Id'] = mantId;
    axios
      .get(`${API}/admin/diagnose-class-courses/${classId}`, { headers })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch((e) => {
        if (cancelled) return;
        const m = e.response?.data?.detail || e.message || 'Erro ao diagnosticar';
        setErr(typeof m === 'string' ? m : JSON.stringify(m));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, classId, mantId]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="curricular-diagnose-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Stethoscope className="w-4 h-4 text-amber-600" />
            Diagnóstico Curricular
          </DialogTitle>
          <DialogDescription>
            Read-only · Decisão de saneamento é responsabilidade administrativa supervisionada.
          </DialogDescription>
        </DialogHeader>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-zinc-500 py-8 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Carregando diagnóstico…
          </div>
        )}
        {err && (
          <div className="text-sm text-red-700 py-4 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            <span data-testid="diagnose-error">{err}</span>
          </div>
        )}
        {!loading && !err && data && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-600 border-b pb-3">
              <span><strong>Turma:</strong> {data.class_name}</span>
              <span><strong>Ano:</strong> {data.academic_year || '—'}</span>
              <span><strong>Componentes:</strong> {data.summary?.total_courses_in_class}</span>
              <span><strong>Duplicidades:</strong> {data.summary?.duplicate_groups}</span>
              <span><strong>Suspeitos (fantasma):</strong> {data.summary?.ghost_courses}</span>
              <span><strong>Notas órfãs:</strong> {data.summary?.orphan_course_ids}</span>
            </div>

            {data.duplicates_by_name?.length > 0 && (
              <div data-testid="diagnose-duplicates-section">
                <div className="text-xs uppercase tracking-wide text-amber-700 mb-2">
                  Componentes com nome duplicado
                </div>
                <div className="space-y-3">
                  {data.duplicates_by_name.map((dup, i) => (
                    <div key={i} className="border border-amber-200 rounded p-3 bg-amber-50/40">
                      <div className="text-sm font-semibold text-amber-900 mb-2">
                        {dup.course_name}
                      </div>
                      <table className="min-w-full text-xs">
                        <thead className="text-zinc-500 uppercase tracking-wide">
                          <tr>
                            <th className="text-left py-1">course_id</th>
                            <th className="text-center py-1">Notas</th>
                            <th className="text-center py-1">Faltas</th>
                            <th className="text-center py-1">Snapshots</th>
                            <th className="text-center py-1">Docs</th>
                            <th className="text-center py-1">Render</th>
                            <th className="text-center py-1">Ativo</th>
                            <th className="text-center py-1">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dup.courses.map((c) => (
                            <tr key={c.course_id} className="border-t border-amber-100">
                              <td className="py-1 font-mono text-[11px]">{c.course_id}</td>
                              <td className="text-center">{c.grades_count}</td>
                              <td className="text-center">{c.attendance_count}</td>
                              <td className="text-center">{c.linked_snapshots_count ?? 0}</td>
                              <td className="text-center">{c.linked_documents_count ?? 0}</td>
                              <td className="text-center">{c.linked_render_jobs_count ?? 0}</td>
                              <td className="text-center">{c.active ? 'sim' : 'não'}</td>
                              <td className="text-center">
                                {c.safe_to_remove ? (
                                  <span
                                    className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded text-[10px] uppercase"
                                    data-testid={`diagnose-safe-${c.course_id}`}
                                  >
                                    Removível
                                  </span>
                                ) : (
                                  <span className="text-red-700 bg-red-50 px-1.5 py-0.5 rounded text-[10px] uppercase">
                                    Bloqueado
                                  </span>
                                )}
                                {c.suspected_ghost && (
                                  <span className="ml-1 text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded text-[10px] uppercase">
                                    Fantasma
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.orphan_grades?.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-zinc-600 mb-2">
                  Notas órfãs (course_id não está em class.course_ids)
                </div>
                <table className="min-w-full text-xs">
                  <thead className="text-zinc-500 uppercase tracking-wide">
                    <tr>
                      <th className="text-left py-1">course_id</th>
                      <th className="text-left py-1">Nome (cadastro atual)</th>
                      <th className="text-center py-1">Notas</th>
                      <th className="text-center py-1">Alunos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.orphan_grades.map((o) => (
                      <tr key={o.course_id} className="border-t">
                        <td className="py-1 font-mono text-[11px]">{o.course_id}</td>
                        <td className="py-1">{o.course_name_resolved || o.course_name_from_grade || '—'}</td>
                        <td className="text-center">{o.grades_count}</td>
                        <td className="text-center">{o.students_with_records}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="text-[11px] text-zinc-500 italic border-t pt-3">
              Saneamento (remoção de componente da turma) é uma operação acadêmica
              crítica. Bloqueada automaticamente se houver notas, frequência,
              snapshots, documentos ou render jobs vinculados. Exige confirmação
              institucional explícita e justificativa formal — não disponível
              nesta visualização.
            </div>
          </div>
        )}
        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={onClose} data-testid="diagnose-close-btn">
            Fechar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DependencySection({ items }) {  if (!items?.length) return null;
  return (
    <Card className="mt-4 border-amber-200" data-testid="bulletin-dependency-section">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-amber-800">
          Componentes em Dependência
          <span className="ml-2 text-xs text-amber-600 font-normal">
            (não compõem cálculo regular da turma)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <table className="min-w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-zinc-500 bg-amber-50">
            <tr>
              <th className="text-left px-3 py-2 font-medium">Componente</th>
              <th className="text-center px-2 py-2 font-medium">B1</th>
              <th className="text-center px-2 py-2 font-medium">B2</th>
              <th className="text-center px-2 py-2 font-medium">B3</th>
              <th className="text-center px-2 py-2 font-medium">B4</th>
              <th className="text-center px-2 py-2 font-medium">Média</th>
              <th className="text-center px-2 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.dependency_id || d.course_id} className="border-t border-amber-100">
                <td className="px-3 py-2 text-amber-900">{d.course_name}</td>
                <td className="text-center px-2 py-2">{fmtGrade(d.grades?.b1)}</td>
                <td className="text-center px-2 py-2">{fmtGrade(d.grades?.b2)}</td>
                <td className="text-center px-2 py-2">{fmtGrade(d.grades?.b3)}</td>
                <td className="text-center px-2 py-2">{fmtGrade(d.grades?.b4)}</td>
                <td className="text-center px-2 py-2 font-semibold">{fmtGrade(d.grades?.final_average)}</td>
                <td className="text-center px-2 py-2 text-xs text-zinc-600">{d.grades?.status || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function BulletinHeader({ data }) {
  const stu = data.student;
  return (
    <Card data-testid="bulletin-header">
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase text-zinc-500 tracking-wide">Boletim Online</div>
            <h1 className="text-2xl font-semibold text-zinc-900 mt-1">
              {stu?.full_name || '(sem nome)'}
            </h1>
            <div className="text-sm text-zinc-600 mt-1">
              {stu?.registration_number ? `Matrícula: ${stu.registration_number}` : ''}
              <span className="mx-2">·</span>
              Ano letivo: <strong>{data.academic_year}</strong>
            </div>
            {data.primary_school?.name && (
              <div className="text-xs text-zinc-500 mt-2">
                {data.primary_school.name}
                {data.primary_class?.name ? ` · ${data.primary_class.name}` : ''}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-1">
            {data.is_composite ? (
              <Badge
                data-testid="bulletin-composite-badge"
                className="bg-indigo-100 text-indigo-800 hover:bg-indigo-100"
              >
                Boletim Composto · {data.composite_segments?.length || 0} períodos
              </Badge>
            ) : (
              <Badge
                data-testid="bulletin-simple-badge"
                className="bg-zinc-100 text-zinc-700 hover:bg-zinc-100"
              >
                Boletim Simples
              </Badge>
            )}
            {stu?.dependency_mode && stu.dependency_mode !== 'none' && (
              <span className="text-[11px] text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
                Modo: {stu.dependency_mode === 'with_dependency'
                  ? 'Com dependência'
                  : 'Apenas dependência'}
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StudentPicker({ value, onSelect, mantId }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const { results, loading } = useStudentSearch(query, { tenantId: mantId, limit: 10 });

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
        <Input
          data-testid="bulletin-student-search"
          value={query}
          placeholder="Buscar aluno por nome (mín. 2 letras)…"
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          className="pl-9 pr-9"
        />
        {query && (
          <button
            type="button"
            data-testid="bulletin-student-search-clear"
            onClick={() => { setQuery(''); setOpen(false); }}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-zinc-400 hover:text-zinc-600"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      {open && query.length >= 2 && (
        <div className="absolute z-10 w-full mt-1 bg-white border rounded shadow-lg max-h-72 overflow-y-auto">
          {loading && (
            <div className="px-3 py-2 text-sm text-zinc-500 flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" /> Buscando…
            </div>
          )}
          {!loading && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-zinc-500">Nenhum aluno encontrado.</div>
          )}
          {!loading && results.map((s) => (
            <button
              type="button"
              key={s.id}
              data-testid={`bulletin-student-option-${s.id}`}
              onClick={() => {
                onSelect(s);
                setOpen(false);
                setQuery(s.full_name || '');
              }}
              className="w-full text-left px-3 py-2 hover:bg-zinc-50 text-sm border-b last:border-0"
            >
              <div className="text-zinc-900">{s.full_name}</div>
              <div className="text-xs text-zinc-500">
                {s.registration_number ? `Matrícula ${s.registration_number}` : ''}
                {s.class_name ? ` · ${s.class_name}` : ''}
              </div>
            </button>
          ))}
        </div>
      )}
      {value && (
        <div className="mt-2 text-xs text-zinc-500" data-testid="bulletin-selected-student">
          Selecionado: <strong>{value.full_name}</strong>
        </div>
      )}
    </div>
  );
}

export default function BulletinViewer() {
  const { user } = useAuth();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [bulletinsIndex, setBulletinsIndex] = useState([]);
  const [indexLoading, setIndexLoading] = useState(false);
  // Chave: "regular" ou "dep:<class_id>"
  const [activeBulletinKey, setActiveBulletinKey] = useState('regular');
  const [bulletin, setBulletin] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [diagnoseClassId, setDiagnoseClassId] = useState(null);

  const isAdmin = user && ['admin', 'super_admin'].includes(user.role);

  const mantId = useMemo(() => {
    try {
      return sessionStorage.getItem('sigesc_active_mantenedora_id') || null;
    } catch {
      return null;
    }
  }, []);

  const authHeaders = useMemo(() => {
    const token = sessionStorage.getItem('accessToken') || localStorage.getItem('accessToken');
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (mantId) headers['X-Mantenedora-Id'] = mantId;
    return headers;
  }, [mantId]);

  // 1) Fetch bulletins-index (catálogo) ao trocar aluno/ano
  useEffect(() => {
    if (!selectedStudent?.id) {
      setBulletinsIndex([]);
      setActiveBulletinKey('regular');
      return;
    }
    let cancelled = false;
    setIndexLoading(true);
    axios
      .get(`${API}/students/${selectedStudent.id}/bulletins-index`, {
        params: { academic_year: year },
        headers: authHeaders,
      })
      .then((r) => {
        if (cancelled) return;
        const items = Array.isArray(r.data?.items) ? r.data.items : [];
        setBulletinsIndex(items);
        // Auto-seleciona o primeiro disponível
        const first = items[0];
        if (first) {
          setActiveBulletinKey(
            first.type === 'regular' ? 'regular' : `dep:${first.class_id}`
          );
        } else {
          setActiveBulletinKey('regular'); // fallback (sem catálogo)
        }
      })
      .catch(() => {
        if (cancelled) return;
        // Catálogo é "best effort". Em caso de erro, segue com regular.
        setBulletinsIndex([]);
        setActiveBulletinKey('regular');
      })
      .finally(() => { if (!cancelled) setIndexLoading(false); });
    return () => { cancelled = true; };
  }, [selectedStudent?.id, year, authHeaders]);

  // 2) Fetch boletim ativo (regular ou dependência) conforme seleção
  useEffect(() => {
    if (!selectedStudent?.id) {
      setBulletin(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const isDependency = activeBulletinKey.startsWith('dep:');
    const url = isDependency
      ? `${API}/students/${selectedStudent.id}/dependency-bulletin`
      : `${API}/students/${selectedStudent.id}/bulletin`;
    const params = isDependency
      ? { academic_year: year, target_class_id: activeBulletinKey.slice(4) }
      : { academic_year: year };

    axios
      .get(url, { params, headers: authHeaders })
      .then((r) => {
        if (!cancelled) setBulletin(r.data);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail || err.message || 'Erro ao carregar boletim';
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
        setBulletin(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedStudent?.id, year, activeBulletinKey, authHeaders]);

  const showSelector = bulletinsIndex.length > 1;

  return (
    <Layout>
      <div className="max-w-5xl mx-auto py-6 px-4 space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Boletim Online</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Visualização pedagógica · Read-only · Composto por períodos quando houver
            movimentação acadêmica no ano.
          </p>
        </div>

        <Card>
          <CardContent className="pt-6 grid gap-3 sm:grid-cols-[1fr_140px]">
            <StudentPicker
              value={selectedStudent}
              onSelect={(s) => setSelectedStudent(s)}
              mantId={mantId}
            />
            <Input
              data-testid="bulletin-year-input"
              type="number"
              min="2000"
              max="2099"
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value, 10) || currentYear)}
              placeholder="Ano letivo"
            />
          </CardContent>
        </Card>

        {selectedStudent && showSelector && (
          <Card data-testid="bulletin-selector-card">
            <CardContent className="pt-6 space-y-2">
              <div className="text-xs uppercase tracking-wide text-zinc-500">
                Selecione qual boletim visualizar
              </div>
              <Tabs
                value={activeBulletinKey}
                onValueChange={setActiveBulletinKey}
                data-testid="bulletin-selector-tabs"
              >
                <TabsList className="flex-wrap h-auto">
                  {bulletinsIndex.map((it) => {
                    const key = it.type === 'regular' ? 'regular' : `dep:${it.class_id}`;
                    const Icon = it.type === 'regular' ? BookOpen : GraduationCap;
                    return (
                      <TabsTrigger
                        key={key}
                        value={key}
                        data-testid={`bulletin-tab-${key}`}
                        className="gap-1.5"
                      >
                        <Icon className="w-3.5 h-3.5" />
                        {it.label || (it.type === 'regular' ? 'Regular' : `Dependência · ${it.class_name}`)}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>
              </Tabs>
              {indexLoading && (
                <div className="text-[11px] text-zinc-500 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Atualizando catálogo…
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {loading && (
          <div className="flex items-center gap-2 text-sm text-zinc-500 py-8 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Carregando boletim…
          </div>
        )}

        {error && (
          <Card className="border-red-200">
            <CardContent className="pt-6 flex items-center gap-2 text-sm text-red-700">
              <AlertCircle className="w-4 h-4" />
              <span data-testid="bulletin-error">{error}</span>
            </CardContent>
          </Card>
        )}

        {!loading && !error && bulletin && (
          <>
            <BulletinHeader data={bulletin} />

            {bulletin.bulletin_type === 'dependency' && (
              <Card className="border-amber-200 bg-amber-50/30" data-testid="bulletin-dependency-context">
                <CardContent className="pt-4 pb-4 text-xs text-amber-800 flex items-start gap-2">
                  <GraduationCap className="w-4 h-4 mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <strong>Boletim de Dependência</strong> · {bulletin.primary_class?.name || ''}
                    {bulletin.primary_school?.name ? ` · ${bulletin.primary_school.name}` : ''}
                    <div className="text-amber-700 mt-0.5">
                      Componentes isolados — não compõem o boletim regular do aluno.
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-[11px] border-amber-300 text-amber-800 hover:bg-amber-100 shrink-0"
                    data-testid="ficha-dependency-pdf-btn"
                    onClick={() => {
                      const sid = selectedStudent?.id;
                      const cid = activeBulletinKey.startsWith('dep:')
                        ? activeBulletinKey.slice(4)
                        : bulletin.target_class_id;
                      if (!sid || !cid) return;
                      const safe = (selectedStudent?.full_name || 'aluno').replace(/\s+/g, '_');
                      const filename = `ficha_dependencia_${safe}_${year}.pdf`;
                      downloadBlob(
                        `${API}/documents/ficha-individual-dependency/${sid}?target_class_id=${encodeURIComponent(cid)}&academic_year=${year}`,
                        filename,
                        authHeaders
                      ).catch(() => {
                        // eslint-disable-next-line no-alert
                        alert('Não foi possível gerar a Ficha de Dependência.');
                      });
                    }}
                  >
                    Ficha Individual (PDF)
                  </Button>
                </CardContent>
              </Card>
            )}

            {bulletin.warnings?.length > 0 && (
              <Card className="border-amber-200">
                <CardContent className="pt-6 space-y-2">
                  {bulletin.warnings.map((w, i) => (
                    <div
                      key={i}
                      className="text-xs text-amber-700 flex items-center gap-2 flex-wrap"
                      data-testid={`bulletin-warning-${w.code || i}`}
                    >
                      <AlertCircle className="w-3 h-3 shrink-0" />
                      <span>{w.message || w.code}</span>
                      {isAdmin && w.code === 'DUPLICATE_COURSE_NAME' && w.class_id && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 px-2 text-[11px] border-amber-300 text-amber-800 hover:bg-amber-50"
                          onClick={() => setDiagnoseClassId(w.class_id)}
                          data-testid={`bulletin-diagnose-btn-${w.class_id}`}
                        >
                          <Stethoscope className="w-3 h-3 mr-1" />
                          Diagnosticar
                        </Button>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <CurricularDiagnoseModal
              open={!!diagnoseClassId}
              onClose={() => setDiagnoseClassId(null)}
              classId={diagnoseClassId}
              mantId={mantId}
            />

            {bulletin.composite_segments?.map((seg) => (
              <Card key={seg.period_index} data-testid={`bulletin-segment-${seg.period_index}`}>
                <CardContent className="pt-6">
                  <SegmentHeader seg={seg} />
                  <ComponentsTable components={seg.components || []} />
                  <AttendanceRow summary={seg.attendance_summary} />
                </CardContent>
              </Card>
            ))}

            {/* DependencySection (componentes em dependência dentro do boletim regular) só faz sentido no boletim regular */}
            {bulletin.bulletin_type !== 'dependency' && (
              <DependencySection items={bulletin.dependency_components} />
            )}
          </>
        )}

        {!loading && !bulletin && !error && (
          <div className="text-sm text-zinc-500 italic py-12 text-center">
            Selecione um aluno acima para visualizar o boletim.
          </div>
        )}
      </div>
    </Layout>
  );
}
