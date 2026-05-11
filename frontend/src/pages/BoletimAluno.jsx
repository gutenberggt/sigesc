import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Loader2, GraduationCap, Home, Printer, Award, AlertTriangle,
  CheckCircle2, XCircle, Calendar
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Layout } from '@/components/Layout';
import axios from 'axios';
import { valorParaConceito, CONCEITOS_EDUCACAO_INFANTIL, CONCEITOS_ANOS_INICIAIS } from '@/components/grades/gradeHelpers';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SITUATION_LABEL = { aprovado: 'Aprovado', reprovado: 'Reprovado', cursando: 'Cursando' };
const SITUATION_COLOR = {
  aprovado: 'bg-green-100 text-green-800 border-green-300',
  reprovado: 'bg-red-100 text-red-800 border-red-300',
  cursando: 'bg-blue-100 text-blue-800 border-blue-300'
};

const SHIFT_LABEL = {
  morning: 'Matutino',
  afternoon: 'Vespertino',
  evening: 'Noturno',
  night: 'Noturno',
  full_time: 'Integral',
  integral: 'Integral',
  matutino: 'Matutino',
  vespertino: 'Vespertino',
  noturno: 'Noturno',
};
const fmtShift = (s) => {
  if (!s) return '—';
  const key = String(s).toLowerCase().trim();
  return SHIFT_LABEL[key] || s;
};

const fmt = (v) => v === null || v === undefined ? '—' : (typeof v === 'number' ? v.toFixed(1) : v);
// Conceito: converte valor numérico (10/7.5/5/0) para sigla (OD/DP/ND/NT ou C/ED/ND) real
const fmtConceito = (v, gradeLevel) => {
  if (v === null || v === undefined || v === '') return '—';
  // Se já vier como string de conceito (legacy), retorna como está
  if (typeof v === 'string' && isNaN(Number(v))) return v;
  const sigla = valorParaConceito(v, gradeLevel);
  return sigla || '—';
};
const descricaoConceito = (sigla, ehAnosIniciais) => {
  if (!sigla || sigla === '—') return '';
  const tabela = ehAnosIniciais ? CONCEITOS_ANOS_INICIAIS : CONCEITOS_EDUCACAO_INFANTIL;
  return tabela[sigla]?.descricao || '';
};
const corConceito = (sigla, ehAnosIniciais) => {
  if (!sigla || sigla === '—') return 'text-gray-400';
  const tabela = ehAnosIniciais ? CONCEITOS_ANOS_INICIAIS : CONCEITOS_EDUCACAO_INFANTIL;
  return tabela[sigla]?.cor || 'text-gray-700';
};
// Formata data SEM regressão por fuso horário.
// `new Date("YYYY-MM-DD")` é interpretado como UTC meia-noite e, ao converter para
// pt-BR (UTC-3), volta um dia. Forçamos local time via 'T00:00:00' (ou parse manual).
const fmtDate = (s) => {
  if (!s) return '—';
  try {
    const datePart = String(s).split('T')[0]; // aceita ISO completo ou YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
      const [y, m, d] = datePart.split('-');
      return `${d}/${m}/${y}`;
    }
    return new Date(datePart + 'T00:00:00').toLocaleDateString('pt-BR');
  } catch {
    return s;
  }
};

export default function BoletimAluno() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const r = await axios.get(`${API}/student/me/report-card`);
        setData(r.data);
      } catch (e) {
        setError(e?.response?.data?.detail || e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center py-20"><Loader2 className="w-10 h-10 animate-spin text-blue-600" /></div>
      </Layout>
    );
  }
  if (error) {
    return (
      <Layout>
        <div className="max-w-3xl mx-auto py-10">
          <Card className="border-red-300">
            <CardContent className="p-6 text-center">
              <XCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
              <p className="text-red-700 font-medium">{error}</p>
              <p className="text-sm text-gray-500 mt-2">Se você é aluno e vê este erro, entre em contato com a secretaria da escola.</p>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }
  if (!data) return null;

  const higher = data.higher_grade;
  const conceito = data.usa_conceito;
  const freq = data.frequencia || {};
  const freqPct = freq.percentual_presenca_dias_letivos ?? freq.percentual_presenca_attendance;

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-4 pb-10" data-testid="boletim-aluno">
        {/* Actions - não imprimem */}
        <div className="flex justify-between items-center print:hidden">
          <Link to="/aluno" className="flex items-center gap-2 text-gray-600 hover:text-gray-900">
            <Home size={18} /><span>Início</span>
          </Link>
          <Button variant="outline" onClick={() => window.print()} data-testid="print-btn">
            <Printer className="w-4 h-4 mr-2" /> Imprimir
          </Button>
        </div>

      {/* Cabeçalho oficial */}
      <Card className="border-2">
        <CardContent className="p-5">
          <div className="flex items-center gap-4">
            {data.mantenedora?.brasao_url && (
              <img
                src={data.mantenedora.brasao_url}
                alt="Brasão"
                className="w-16 h-16 object-contain"
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
              />
            )}
            <div className="flex-1 text-center">
              <h1 className="text-sm font-bold uppercase tracking-wide">{data.mantenedora?.nome}</h1>
              {data.mantenedora?.secretaria && (
                <p className="text-xs text-gray-600">{data.mantenedora.secretaria}</p>
              )}
              <h2 className="text-lg font-bold mt-1">{data.escola?.nome}</h2>
              {(data.escola?.municipio || data.escola?.estado || data.escola?.inep) && (
                <p className="text-xs text-gray-500">
                  {[data.escola?.municipio, data.escola?.estado].filter(Boolean).join(' / ')}
                  {data.escola?.inep && (
                    <>
                      {(data.escola?.municipio || data.escola?.estado) && ' · '}
                      INEP: {data.escola.inep}
                    </>
                  )}
                </p>
              )}
            </div>
          </div>
          <div className="border-t mt-3 pt-3 flex items-center justify-center gap-2">
            <GraduationCap className="w-5 h-5 text-blue-600" />
            <span className="text-base font-bold uppercase">Boletim Escolar · Ano Letivo {data.academic_year}</span>
          </div>
        </CardContent>
      </Card>

      {/* Identificação do aluno */}
      <Card>
        <CardContent className="p-4 text-sm grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="col-span-2">
            <div className="text-[10px] uppercase text-gray-500">Aluno(a)</div>
            <div className="font-semibold" data-testid="aluno-nome">{data.aluno?.nome}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-gray-500">Nascimento</div>
            <div>{fmtDate(data.aluno?.nascimento)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-gray-500">Sexo</div>
            <div className="capitalize">{data.aluno?.sexo || '—'}</div>
          </div>
          <div className="col-span-2">
            <div className="text-[10px] uppercase text-gray-500">Turma</div>
            <div className="font-semibold">
              {data.turma?.nome} · {data.turma?.grade_level} · {fmtShift(data.turma?.shift)}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-gray-500">Matrícula</div>
            <div>{data.aluno?.id?.slice(0, 8)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-gray-500">INEP</div>
            <div>{data.aluno?.inep || '—'}</div>
          </div>
        </CardContent>
      </Card>

      {/* Alertas (parabéns ou excesso de faltas) */}
      {data.alerts && data.alerts.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((a, i) => (
            <div key={i}
                 className={`rounded-lg border p-3 flex items-start gap-3 ${
                   a.severity === 'success' ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'
                 }`}
                 data-testid={`alert-${a.type}`}>
              {a.severity === 'success' ? (
                <Award className="w-6 h-6 text-green-600 shrink-0" />
              ) : (
                <AlertTriangle className="w-6 h-6 text-red-600 shrink-0" />
              )}
              <p className={`text-sm font-medium ${a.severity === 'success' ? 'text-green-900' : 'text-red-900'}`}>
                {a.message}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Tabela de notas / conceitos */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {conceito ? (() => {
            const gradeLevel = data.turma?.grade_level;
            const ehAnosIniciais = /1º\s*ano|2º\s*ano|1°\s*ano|2°\s*ano/i.test(gradeLevel || '');
            const tabelaConceitos = ehAnosIniciais ? CONCEITOS_ANOS_INICIAIS : CONCEITOS_EDUCACAO_INFANTIL;
            return (
              <>
                <table className="w-full text-xs" data-testid="boletim-table-conceito">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="px-2 py-2 text-left" rowSpan={2}>Componente Curricular</th>
                      <th className="px-2 py-2 text-center bg-blue-50" colSpan={2}>1º Semestre</th>
                      <th className="px-2 py-2 text-center bg-indigo-50" colSpan={2}>2º Semestre</th>
                      {higher && <th className="px-2 py-2 text-center w-16" rowSpan={2}>Faltas</th>}
                      <th className="px-2 py-2 text-center w-24" rowSpan={2}>Situação</th>
                    </tr>
                    <tr>
                      <th className="px-2 py-1 text-center w-20 bg-blue-50">1º Bim</th>
                      <th className="px-2 py-1 text-center w-20 bg-blue-50">2º Bim</th>
                      <th className="px-2 py-1 text-center w-20 bg-indigo-50">3º Bim</th>
                      <th className="px-2 py-1 text-center w-20 bg-indigo-50">4º Bim</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.componentes && data.componentes.length > 0 ? data.componentes.map((row, i) => {
                      const c1 = fmtConceito(row.b1, gradeLevel);
                      const c2 = fmtConceito(row.b2, gradeLevel);
                      const c3 = fmtConceito(row.b3, gradeLevel);
                      const c4 = fmtConceito(row.b4, gradeLevel);
                      return (
                        <tr key={row.course_id} className={i % 2 ? 'bg-gray-50' : ''}>
                          <td className="px-2 py-1.5 font-medium">{row.course_name}</td>
                          <td className={`px-2 py-1.5 text-center font-bold ${corConceito(c1, ehAnosIniciais)}`} title={descricaoConceito(c1, ehAnosIniciais)}>{c1}</td>
                          <td className={`px-2 py-1.5 text-center font-bold ${corConceito(c2, ehAnosIniciais)}`} title={descricaoConceito(c2, ehAnosIniciais)}>{c2}</td>
                          <td className={`px-2 py-1.5 text-center font-bold ${corConceito(c3, ehAnosIniciais)}`} title={descricaoConceito(c3, ehAnosIniciais)}>{c3}</td>
                          <td className={`px-2 py-1.5 text-center font-bold ${corConceito(c4, ehAnosIniciais)}`} title={descricaoConceito(c4, ehAnosIniciais)}>{c4}</td>
                          {higher && <td className="px-2 py-1.5 text-center">{row.faltas_componente ?? '—'}</td>}
                          <td className="px-2 py-1.5 text-center">
                            {row.situacao && (
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${SITUATION_COLOR[row.situacao]}`}>
                                {SITUATION_LABEL[row.situacao]}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    }) : (
                      <tr><td colSpan={higher ? 7 : 6} className="py-8 text-center text-gray-500">
                        Nenhum componente curricular encontrado para sua turma.
                      </td></tr>
                    )}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={higher ? 7 : 6} className="px-3 py-2 text-[10px] italic text-gray-500 bg-yellow-50">
                        Esta turma é avaliada por <strong>conceito</strong> ({ehAnosIniciais ? '1º / 2º Ano' : 'Educação Infantil'}). Não há recuperação nem média numérica.
                      </td>
                    </tr>
                  </tfoot>
                </table>
                {/* Legenda dos conceitos */}
                <div className="px-4 py-3 border-t bg-gray-50 flex flex-wrap gap-x-6 gap-y-1 text-[11px]">
                  <span className="font-semibold text-gray-700">Legenda:</span>
                  {Object.entries(tabelaConceitos).map(([sigla, info]) => (
                    <span key={sigla} className="flex items-center gap-1">
                      <strong className={info.cor}>{sigla}</strong>
                      <span className="text-gray-600">= {info.descricao}</span>
                    </span>
                  ))}
                </div>
              </>
            );
          })() : (
            <table className="w-full text-xs" data-testid="boletim-table">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-2 py-2 text-left" rowSpan={2}>Componente Curricular</th>
                  <th className="px-2 py-2 text-center bg-blue-50" colSpan={4}>1º Semestre</th>
                  <th className="px-2 py-2 text-center bg-indigo-50" colSpan={4}>2º Semestre</th>
                  <th className="px-2 py-2 text-center w-16 bg-blue-50" rowSpan={2}>Média</th>
                  <th className="px-2 py-2 text-center w-14" rowSpan={2}>Rec Final</th>
                  <th className="px-2 py-2 text-center w-16 bg-blue-50" rowSpan={2}>Final</th>
                  {higher && <th className="px-2 py-2 text-center w-14" rowSpan={2}>Faltas</th>}
                  <th className="px-2 py-2 text-center w-24" rowSpan={2}>Situação</th>
                </tr>
                <tr>
                  <th className="px-2 py-1 text-center w-14 bg-blue-50">1º Bim</th>
                  <th className="px-2 py-1 text-center w-14 bg-blue-50">Rec 1</th>
                  <th className="px-2 py-1 text-center w-14 bg-blue-50">2º Bim</th>
                  <th className="px-2 py-1 text-center w-14 bg-blue-50">Rec 2</th>
                  <th className="px-2 py-1 text-center w-14 bg-indigo-50">3º Bim</th>
                  <th className="px-2 py-1 text-center w-14 bg-indigo-50">Rec 3</th>
                  <th className="px-2 py-1 text-center w-14 bg-indigo-50">4º Bim</th>
                  <th className="px-2 py-1 text-center w-14 bg-indigo-50">Rec 4</th>
                </tr>
              </thead>
              <tbody>
                {data.componentes && data.componentes.length > 0 ? data.componentes.map((row, i) => (
                  <tr key={row.course_id} className={i % 2 ? 'bg-gray-50' : ''}>
                    <td className="px-2 py-1.5 font-medium">{row.course_name}</td>
                    <td className="px-2 py-1.5 text-center">{fmt(row.b1)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-500">{fmt(row.rec_b1)}</td>
                    <td className="px-2 py-1.5 text-center">{fmt(row.b2)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-500">{fmt(row.rec_b2)}</td>
                    <td className="px-2 py-1.5 text-center">{fmt(row.b3)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-500">{fmt(row.rec_b3)}</td>
                    <td className="px-2 py-1.5 text-center">{fmt(row.b4)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-500">{fmt(row.rec_b4)}</td>
                    <td className="px-2 py-1.5 text-center font-semibold bg-blue-50">{fmt(row.media)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-500">{fmt(row.rec_final)}</td>
                    <td className="px-2 py-1.5 text-center font-bold bg-blue-50">{fmt(row.media_final)}</td>
                    {higher && <td className="px-2 py-1.5 text-center">{row.faltas_componente ?? '—'}</td>}
                    <td className="px-2 py-1.5 text-center">
                      {row.situacao && (
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${SITUATION_COLOR[row.situacao]}`}>
                          {SITUATION_LABEL[row.situacao]}
                        </span>
                      )}
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={higher ? 14 : 13} className="py-8 text-center text-gray-500">
                    Nenhum componente curricular encontrado para sua turma.
                  </td></tr>
                )}
              </tbody>
              {data.media_geral !== null && data.media_geral !== undefined && (
                <tfoot className="bg-gray-100 font-bold">
                  <tr>
                    <td colSpan={9} className="px-2 py-2 text-right">Média geral:</td>
                    <td className="px-2 py-2 text-center text-base" data-testid="media-geral">{data.media_geral.toFixed(2)}</td>
                    <td colSpan={higher ? 4 : 3}></td>
                  </tr>
                </tfoot>
              )}
            </table>
          )}
        </CardContent>
      </Card>

      {/* Resumo de frequência + situação final */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Calendar className="w-8 h-8 text-blue-600" />
            <div>
              <div className="text-[10px] uppercase text-gray-500">Dias letivos até hoje</div>
              <div className="text-2xl font-bold">{freq.dias_letivos_ate_hoje ?? '—'}</div>
              <div className="text-[10px] text-gray-500">de {freq.dias_letivos_previstos ?? '—'} previstos</div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <XCircle className="w-8 h-8 text-red-500" />
            <div>
              <div className="text-[10px] uppercase text-gray-500">Total de faltas</div>
              <div className="text-2xl font-bold">{freq.total_faltas ?? 0}</div>
              {freqPct !== null && freqPct !== undefined && (
                <div className="text-[10px] text-gray-500">{freqPct}% de presença</div>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            {data.situacao_final === 'aprovado' ? <CheckCircle2 className="w-8 h-8 text-green-500" /> :
             data.situacao_final === 'reprovado' ? <XCircle className="w-8 h-8 text-red-500" /> :
             <GraduationCap className="w-8 h-8 text-blue-500" />}
            <div>
              <div className="text-[10px] uppercase text-gray-500">Situação Final</div>
              <div className={`text-xl font-bold ${
                data.situacao_final === 'aprovado' ? 'text-green-700' :
                data.situacao_final === 'reprovado' ? 'text-red-700' : 'text-blue-700'
              }`} data-testid="situacao-final">
                {SITUATION_LABEL[data.situacao_final]}
              </div>
              <div className="text-[10px] text-gray-500">Mín: {data.media_aprovacao} · Freq: {data.frequencia_minima}%</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <p className="text-[10px] text-center text-gray-400">
        Gerado em: {new Date(data.computed_at).toLocaleString('pt-BR')}
      </p>
      </div>
    </Layout>
  );
}
