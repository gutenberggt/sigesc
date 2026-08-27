import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { schoolsAPI, classesAPI, studentsAPI } from '@/services/api';
import { toast } from 'sonner';
import { ArrowLeft, FileText, Home, Loader2, ShieldAlert } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const RESULTADOS = [
  'CURSANDO',
  'EM ANDAMENTO',
  'PROMOVIDO(A)',
  'CONCLUIU A ETAPA',
  'APROVADO',
  'APROVADO COM DEPENDÊNCIA',
  'EM DEPENDÊNCIA',
  'REPROVADO',
  'REPROVADO POR FREQUÊNCIA',
  'TRANSFERIDO',
  'DESISTENTE',
  'FALECIDO',
];

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  return data?.students || data?.items || data?.data || [];
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function emptyGrade(courseId) {
  return {
    course_id: courseId,
    b1: '',
    b2: '',
    rec_s1: '',
    b3: '',
    b4: '',
    rec_s2: '',
  };
}

export default function UrgenciaFichaIndividual() {
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);

  const [schoolId, setSchoolId] = useState('');
  const [classId, setClassId] = useState('');
  const [studentSeries, setStudentSeries] = useState('');
  const [studentId, setStudentId] = useState('');
  const [resultado, setResultado] = useState('');
  const [dataEmissao, setDataEmissao] = useState(todayIso());

  const [preview, setPreview] = useState(null);
  const [manualGrades, setManualGrades] = useState({});
  const [loadingSchools, setLoadingSchools] = useState(true);
  const [loadingClasses, setLoadingClasses] = useState(false);
  const [loadingStudents, setLoadingStudents] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);

  const selectedClass = useMemo(
    () => classes.find((item) => item.id === classId),
    [classes, classId]
  );

  const isMultiGrade = Boolean(
    selectedClass?.is_multi_grade ||
    selectedClass?.is_multigrade ||
    selectedClass?.multigrade
  );

  const seriesOptions = useMemo(() => {
    if (!selectedClass) return [];
    const raw = selectedClass.series || selectedClass.grade_levels || selectedClass.series_options || [];
    return Array.isArray(raw) ? raw.filter(Boolean) : [];
  }, [selectedClass]);

  useEffect(() => {
    let active = true;
    setLoadingSchools(true);
    schoolsAPI.getAll()
      .then((data) => {
        if (active) setSchools(Array.isArray(data) ? data : (data?.items || []));
      })
      .catch(() => toast.error('Não foi possível carregar as escolas.'))
      .finally(() => active && setLoadingSchools(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setClassId('');
    setStudentSeries('');
    setStudentId('');
    setStudents([]);
    setPreview(null);
    setManualGrades({});
    if (!schoolId) {
      setClasses([]);
      return;
    }

    let active = true;
    setLoadingClasses(true);
    classesAPI.getAll(schoolId)
      .then((data) => {
        if (active) setClasses(Array.isArray(data) ? data : (data?.items || []));
      })
      .catch(() => toast.error('Não foi possível carregar as turmas.'))
      .finally(() => active && setLoadingClasses(false));
    return () => { active = false; };
  }, [schoolId]);

  useEffect(() => {
    setStudentSeries('');
    setStudentId('');
    setStudents([]);
    setPreview(null);
    setManualGrades({});

    if (!classId || !schoolId) return;

    if (!isMultiGrade) {
      setStudentSeries(selectedClass?.grade_level || selectedClass?.series_name || '');
    }

    let active = true;
    setLoadingStudents(true);
    studentsAPI.getAll({ school_id: schoolId, class_id: classId, page: 1, page_size: 500 })
      .then((data) => {
        if (!active) return;
        const list = normalizeList(data).filter((s) => !s.class_id || s.class_id === classId);
        setStudents(list);
      })
      .catch(() => toast.error('Não foi possível carregar os estudantes da turma.'))
      .finally(() => active && setLoadingStudents(false));

    return () => { active = false; };
  }, [classId, schoolId, isMultiGrade, selectedClass]);

  useEffect(() => {
    setStudentId('');
    setPreview(null);
    setManualGrades({});
  }, [studentSeries]);

  const visibleStudents = useMemo(() => {
    if (!isMultiGrade || !studentSeries) return students;
    return students.filter((student) => {
      const series = student.student_series || student.grade_level || student.series;
      return !series || series === studentSeries;
    });
  }, [students, isMultiGrade, studentSeries]);

  useEffect(() => {
    if (!studentId || !classId || !schoolId || (isMultiGrade && !studentSeries)) {
      setPreview(null);
      setManualGrades({});
      return;
    }

    let active = true;
    setLoadingPreview(true);
    axios.get(`${API}/documents/ficha-individual-manual/preview`, {
      params: {
        school_id: schoolId,
        class_id: classId,
        student_id: studentId,
        student_series: studentSeries || undefined,
      },
    })
      .then((response) => {
        if (!active) return;
        const data = response.data;
        setPreview(data);
        const initial = {};
        (data.courses || []).forEach((course) => {
          initial[course.id] = emptyGrade(course.id);
        });
        setManualGrades(initial);
      })
      .catch((error) => {
        if (!active) return;
        setPreview(null);
        setManualGrades({});
        toast.error(error.response?.data?.detail || 'Não foi possível preparar a ficha individual.');
      })
      .finally(() => active && setLoadingPreview(false));

    return () => { active = false; };
  }, [studentId, classId, schoolId, studentSeries, isMultiGrade]);

  const setGradeValue = (courseId, field, value) => {
    setManualGrades((current) => ({
      ...current,
      [courseId]: {
        ...(current[courseId] || emptyGrade(courseId)),
        [field]: value,
      },
    }));
  };

  const clearForm = () => {
    setStudentId('');
    setResultado('');
    setDataEmissao(todayIso());
    setPreview(null);
    setManualGrades({});
  };

  const serializeGrades = () => Object.values(manualGrades).map((grade) => {
    const out = { course_id: grade.course_id };
    ['b1', 'b2', 'rec_s1', 'b3', 'b4', 'rec_s2'].forEach((field) => {
      const value = grade[field];
      if (value === '' || value === null || value === undefined) {
        out[field] = null;
      } else if (preview?.evaluation_mode === 'concept') {
        out[field] = String(value).trim().toUpperCase();
      } else {
        out[field] = Number(String(value).replace(',', '.'));
      }
    });
    return out;
  });

  const generatePdf = async () => {
    if (!schoolId || !classId || !studentId || !resultado || !dataEmissao) {
      toast.error('Preencha escola, turma, estudante, resultado e data de emissão.');
      return;
    }
    if (isMultiGrade && !studentSeries) {
      toast.error('Selecione o ano/série/etapa do estudante.');
      return;
    }
    if (!preview?.courses?.length) {
      toast.error('Não há currículo resolvido para gerar a ficha.');
      return;
    }

    setGenerating(true);
    try {
      const response = await axios.post(
        `${API}/documents/ficha-individual-manual`,
        {
          school_id: schoolId,
          class_id: classId,
          student_id: studentId,
          student_series: studentSeries || null,
          resultado,
          data_emissao: dataEmissao,
          grades: serializeGrades(),
        },
        { responseType: 'blob' }
      );

      const blobUrl = window.URL.createObjectURL(response.data);
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
      toast.success('Ficha Individual gerada com sucesso.');
    } catch (error) {
      let detail = 'Não foi possível gerar a Ficha Individual.';
      if (error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const parsed = JSON.parse(text);
          detail = parsed.detail || detail;
        } catch { /* mantém fallback */ }
      } else {
        detail = error.response?.data?.detail || detail;
      }
      toast.error(detail);
    } finally {
      setGenerating(false);
    }
  };

  const conceptOptions = preview?.concept_options || [];
  const isConcept = preview?.evaluation_mode === 'concept';

  return (
    <Layout>
      <div className="space-y-6" data-testid="urgencia-ficha-individual-page">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-4 mb-3 text-sm">
              <button type="button" onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-gray-500 hover:text-blue-600">
                <Home size={18} /> Início
              </button>
              <button type="button" onClick={() => navigate('/admin/urgencias')} className="flex items-center gap-2 text-gray-500 hover:text-blue-600">
                <ArrowLeft size={18} /> Urgências
              </button>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FileText className="text-red-600" /> Ficha Individual — Urgência
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Os dados institucionais vêm do SIGESC. Apenas notas/conceitos, resultado e data são informados manualmente para esta emissão.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 flex gap-3">
          <ShieldAlert className="shrink-0 mt-0.5" size={20} />
          <div>
            <strong>Emissão de contingência.</strong> Os valores digitados nesta página não substituem nem alteram Notas, Frequência, Matrícula ou Histórico acadêmico do estudante.
          </div>
        </div>

        <Card>
          <CardContent className="p-6 space-y-5">
            <h2 className="text-lg font-semibold">Identificação</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              <Field label="Escola *">
                <select className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={schoolId} onChange={(e) => setSchoolId(e.target.value)} disabled={loadingSchools} data-testid="urgencia-school">
                  <option value="">Selecione...</option>
                  {schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}
                </select>
              </Field>

              <Field label="Turma *">
                <select className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={classId} onChange={(e) => setClassId(e.target.value)} disabled={!schoolId || loadingClasses} data-testid="urgencia-class">
                  <option value="">Selecione...</option>
                  {classes.map((klass) => (
                    <option key={klass.id} value={klass.id}>
                      {klass.name} {klass.academic_year ? `— ${klass.academic_year}` : ''}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Ano/Série/Etapa *">
                {isMultiGrade ? (
                  <select className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={studentSeries} onChange={(e) => setStudentSeries(e.target.value)} disabled={!classId} data-testid="urgencia-series">
                    <option value="">Selecione...</option>
                    {seriesOptions.map((series) => <option key={series} value={series}>{series}</option>)}
                  </select>
                ) : (
                  <input className="w-full h-10 rounded-md border border-gray-200 bg-gray-50 px-3" value={studentSeries || ''} readOnly data-testid="urgencia-series-readonly" />
                )}
              </Field>

              <Field label="Estudante *">
                <select className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={studentId} onChange={(e) => setStudentId(e.target.value)} disabled={!classId || (isMultiGrade && !studentSeries) || loadingStudents} data-testid="urgencia-student">
                  <option value="">Selecione...</option>
                  {visibleStudents.map((student) => <option key={student.id} value={student.id}>{student.full_name}</option>)}
                </select>
              </Field>

              <Field label="Resultado *">
                <select className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={resultado} onChange={(e) => setResultado(e.target.value)} data-testid="urgencia-result">
                  <option value="">Selecione...</option>
                  {RESULTADOS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </Field>

              <Field label="Data de emissão *">
                <input type="date" className="w-full h-10 rounded-md border border-gray-300 px-3 bg-white" value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} data-testid="urgencia-issue-date" />
              </Field>
            </div>
          </CardContent>
        </Card>

        {loadingPreview && (
          <div className="flex items-center justify-center gap-2 py-8 text-gray-600">
            <Loader2 className="animate-spin" size={20} /> Preparando currículo e dados da ficha...
          </div>
        )}

        {preview && !loadingPreview && (
          <Card>
            <CardContent className="p-0 overflow-x-auto">
              <div className="p-5 border-b bg-gray-50">
                <h2 className="font-semibold text-gray-900">Notas / Conceitos — preenchimento manual</h2>
                <p className="text-sm text-gray-600 mt-1">
                  {isConcept ? 'Avaliação conceitual conforme a etapa selecionada.' : 'Avaliação numérica; processo ponderado, total e média serão calculados pelo backend com as regras oficiais do SIGESC.'}
                </p>
              </div>

              {isConcept ? (
                <ConceptTable courses={preview.courses || []} grades={manualGrades} options={conceptOptions} onChange={setGradeValue} />
              ) : (
                <NumericTable courses={preview.courses || []} grades={manualGrades} onChange={setGradeValue} />
              )}
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap justify-end gap-3">
          <Button type="button" variant="outline" onClick={clearForm} disabled={generating}>Limpar</Button>
          <Button type="button" onClick={generatePdf} disabled={generating || loadingPreview || !preview} data-testid="urgencia-generate-pdf">
            {generating ? <><Loader2 className="animate-spin mr-2" size={18} />Gerando...</> : <><FileText className="mr-2" size={18} />Gerar PDF</>}
          </Button>
        </div>
      </div>
    </Layout>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  );
}

function GradeInput({ value, onChange, testId }) {
  return (
    <input
      inputMode="decimal"
      className="w-16 h-9 rounded border border-gray-300 px-2 text-center"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testId}
      placeholder="—"
    />
  );
}

function NumericTable({ courses, grades, onChange }) {
  return (
    <table className="min-w-[1100px] w-full text-sm border-collapse">
      <thead className="bg-blue-50 text-gray-800">
        <tr>
          <th rowSpan="2" className="border p-2 text-left">Componentes Curriculares</th>
          <th rowSpan="2" className="border p-2">C.H.</th>
          <th colSpan="3" className="border p-2">1º Semestre</th>
          <th colSpan="3" className="border p-2">2º Semestre</th>
          <th colSpan="4" className="border p-2">Proc. Ponderado</th>
          <th rowSpan="2" className="border p-2">Total Pontos</th>
          <th rowSpan="2" className="border p-2">Média Anual</th>
          <th rowSpan="2" className="border p-2">Faltas</th>
          <th rowSpan="2" className="border p-2">% Freq.</th>
        </tr>
        <tr>
          <th className="border p-2">1º</th><th className="border p-2">2º</th><th className="border p-2">REC</th>
          <th className="border p-2">3º</th><th className="border p-2">4º</th><th className="border p-2">REC</th>
          <th className="border p-2">1º×2</th><th className="border p-2">2º×3</th><th className="border p-2">3º×2</th><th className="border p-2">4º×3</th>
        </tr>
      </thead>
      <tbody>
        {courses.map((course) => {
          const g = grades[course.id] || emptyGrade(course.id);
          return (
            <tr key={course.id} className="odd:bg-white even:bg-gray-50">
              <td className="border p-2 font-medium min-w-[220px]">{course.name}</td>
              <td className="border p-2 text-center">{course.carga_horaria ?? course.workload ?? '—'}</td>
              <td className="border p-1 text-center"><GradeInput value={g.b1} onChange={(v) => onChange(course.id, 'b1', v)} /></td>
              <td className="border p-1 text-center"><GradeInput value={g.b2} onChange={(v) => onChange(course.id, 'b2', v)} /></td>
              <td className="border p-1 text-center"><GradeInput value={g.rec_s1} onChange={(v) => onChange(course.id, 'rec_s1', v)} /></td>
              <td className="border p-1 text-center"><GradeInput value={g.b3} onChange={(v) => onChange(course.id, 'b3', v)} /></td>
              <td className="border p-1 text-center"><GradeInput value={g.b4} onChange={(v) => onChange(course.id, 'b4', v)} /></td>
              <td className="border p-1 text-center"><GradeInput value={g.rec_s2} onChange={(v) => onChange(course.id, 'rec_s2', v)} /></td>
              <td className="border p-2 text-center text-gray-500" colSpan="4">automático</td>
              <td className="border p-2 text-center text-gray-500">automático</td>
              <td className="border p-2 text-center text-gray-500">automático</td>
              <td className="border p-2 text-center">{course.absences ?? '—'}</td>
              <td className="border p-2 text-center">{course.frequency_percentage != null ? `${Number(course.frequency_percentage).toFixed(2)}%` : '—'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ConceptTable({ courses, grades, options, onChange }) {
  return (
    <table className="min-w-[900px] w-full text-sm border-collapse">
      <thead className="bg-blue-50 text-gray-800">
        <tr>
          <th className="border p-2 text-left">Componentes/Campos</th>
          <th className="border p-2">C.H.</th>
          <th className="border p-2">1º Bim.</th>
          <th className="border p-2">2º Bim.</th>
          <th className="border p-2">3º Bim.</th>
          <th className="border p-2">4º Bim.</th>
          <th className="border p-2">Conceito Final</th>
          <th className="border p-2">Faltas</th>
          <th className="border p-2">% Freq.</th>
        </tr>
      </thead>
      <tbody>
        {courses.map((course) => {
          const g = grades[course.id] || emptyGrade(course.id);
          return (
            <tr key={course.id} className="odd:bg-white even:bg-gray-50">
              <td className="border p-2 font-medium min-w-[260px]">{course.name}</td>
              <td className="border p-2 text-center">{course.carga_horaria ?? course.workload ?? '—'}</td>
              {['b1', 'b2', 'b3', 'b4'].map((field) => (
                <td className="border p-1 text-center" key={field}>
                  <select className="h-9 rounded border border-gray-300 px-2 bg-white" value={g[field] || ''} onChange={(e) => onChange(course.id, field, e.target.value)}>
                    <option value="">—</option>
                    {options.map((option) => (
                      <option key={option.value || option} value={option.value || option}>{option.label || option}</option>
                    ))}
                  </select>
                </td>
              ))}
              <td className="border p-2 text-center text-gray-500">automático</td>
              <td className="border p-2 text-center">{course.absences ?? '—'}</td>
              <td className="border p-2 text-center">{course.frequency_percentage != null ? `${Number(course.frequency_percentage).toFixed(2)}%` : '—'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
