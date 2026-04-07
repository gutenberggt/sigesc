import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { ChevronLeft, Save, FileText, Plus, Trash2, GraduationCap, Download } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const SERIES = ['1º', '2º', '3º', '4º', '5º', '6º', '7º', '8º', '9º'];

const COMPONENTES_BNCC = {
  'Linguagens': ['Língua Portuguesa', 'Arte', 'Educação Física', 'Língua Inglesa'],
  'Matemática': ['Matemática'],
  'Ciências da Natureza': ['Ciências'],
  'Ciências Humanas': ['História', 'Geografia', 'Ensino Religioso']
};

const COMPONENTES_DIVERSIFICADA = [
  'Ed. Ambiental e Clima', 'Estudos Amazônicos', 'Literatura e Redação',
  'Acomp. Pedagógico', 'Recreação, Esporte e Lazer', 'Arte e Cultura', 'Tecnologia e Informática'
];

const ALL_COMPONENTS = [
  ...Object.values(COMPONENTES_BNCC).flat(),
  ...COMPONENTES_DIVERSIFICADA
];

const RESULTADOS = [
  { value: 'APV', label: 'Aprovado (APV)' },
  { value: 'REP', label: 'Reprovado (REP)' },
  { value: 'DIS', label: 'Dispensado (DIS)' },
  { value: 'E', label: 'Em andamento (E)' }
];

const emptyRecord = (serie) => ({
  serie,
  ano_letivo: '',
  escola: '',
  cidade: '',
  uf: '',
  carga_horaria: '',
  resultado: '',
  grades: {}
});

export default function StudentHistory() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const [student, setStudent] = useState(null);
  const [records, setRecords] = useState([]);
  const [observations, setObservations] = useState('');
  const [mediaAprovacao, setMediaAprovacao] = useState(6.0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeSerie, setActiveSerie] = useState(null);
  const [importing, setImporting] = useState(false);

  const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const headers = { 'Authorization': `Bearer ${token}` };

      const [studentRes, historyRes] = await Promise.all([
        fetch(`${API}/api/students/${studentId}`, { headers }),
        fetch(`${API}/api/student-history/${studentId}`, { headers })
      ]);

      if (studentRes.ok) {
        const s = await studentRes.json();
        setStudent(s);
      }

      if (historyRes.ok) {
        const h = await historyRes.json();
        setRecords(h.records || []);
        setObservations(h.observations || '');
        setMediaAprovacao(h.media_aprovacao || 6.0);
      }
    } catch (err) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }, [studentId, token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const addRecord = (serie) => {
    if (records.find(r => r.serie === serie)) {
      toast.error(`Já existe registro para ${serie} Ano`);
      return;
    }
    setRecords(prev => [...prev, emptyRecord(serie)]);
    setActiveSerie(serie);
  };

  const removeRecord = (serie) => {
    setRecords(prev => prev.filter(r => r.serie !== serie));
    if (activeSerie === serie) setActiveSerie(null);
  };

  const updateRecord = (serie, field, value) => {
    setRecords(prev => prev.map(r =>
      r.serie === serie ? { ...r, [field]: value } : r
    ));
  };

  const updateGrade = (serie, component, value) => {
    setRecords(prev => prev.map(r => {
      if (r.serie !== serie) return r;
      const grades = { ...r.grades };
      if (value === '' || value === null) {
        delete grades[component];
      } else {
        grades[component] = parseFloat(value) || value;
      }
      return { ...r, grades };
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const res = await fetch(`${API}/api/student-history/${studentId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ records, observations, media_aprovacao: mediaAprovacao })
      });

      if (res.ok) {
        toast.success('Histórico salvo com sucesso!');
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Erro ao salvar');
      }
    } catch {
      toast.error('Erro ao salvar histórico');
    } finally {
      setSaving(false);
    }
  };

  const handleGeneratePdf = () => {
    window.open(`${API}/api/documents/historico-escolar/${studentId}?token=${token}`, '_blank');
  };

  const handleImport = async () => {
    try {
      setImporting(true);
      const res = await fetch(`${API}/api/student-history/${studentId}/import`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Erro ao importar');
        return;
      }
      const data = await res.json();
      const imported = data.records || [];

      if (imported.length === 0) {
        toast.info('Nenhum dado encontrado no sistema para importar.');
        return;
      }

      // Merge: não sobrescrever registros já preenchidos
      let merged = [...records];
      let added = 0;
      for (const imp of imported) {
        const existing = merged.find(r => r.serie === imp.serie);
        if (!existing) {
          merged.push(imp);
          added++;
        } else {
          // Preencher campos vazios do registro existente
          if (!existing.ano_letivo && imp.ano_letivo) existing.ano_letivo = imp.ano_letivo;
          if (!existing.escola && imp.escola) existing.escola = imp.escola;
          if (!existing.cidade && imp.cidade) existing.cidade = imp.cidade;
          if (!existing.uf && imp.uf) existing.uf = imp.uf;
          if (!existing.carga_horaria && imp.carga_horaria) existing.carga_horaria = imp.carga_horaria;
          if (!existing.resultado && imp.resultado) existing.resultado = imp.resultado;
          // Merge notas: preencher somente componentes sem nota
          for (const [comp, nota] of Object.entries(imp.grades || {})) {
            if (!existing.grades[comp]) existing.grades[comp] = nota;
          }
        }
      }

      setRecords(merged);
      if (merged.length > 0 && !activeSerie) {
        setActiveSerie(merged[0].serie);
      }
      toast.success(`Importados ${added} registros. ${imported.length - added} já existiam (campos vazios preenchidos).`);
    } catch {
      toast.error('Erro ao importar dados');
    } finally {
      setImporting(false);
    }
  };

  const activeRecord = records.find(r => r.serie === activeSerie);
  const usedSeries = records.map(r => r.serie);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="history-loading">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="student-history-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} data-testid="history-back-btn">
            <ChevronLeft size={18} />
          </Button>
          <div>
            <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <GraduationCap size={22} className="text-purple-600" />
              Histórico Escolar
            </h1>
            <p className="text-sm text-gray-500">{student?.full_name}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleImport} disabled={importing} data-testid="history-import-btn">
            <Download size={16} className="mr-1" /> {importing ? 'Importando...' : 'Importar Dados'}
          </Button>
          <Button variant="outline" size="sm" onClick={handleGeneratePdf} data-testid="history-pdf-btn">
            <FileText size={16} className="mr-1" /> Gerar PDF
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving} data-testid="history-save-btn">
            <Save size={16} className="mr-1" /> {saving ? 'Salvando...' : 'Salvar'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Sidebar - Lista de séries */}
        <div className="col-span-3 bg-white rounded-lg border p-3 space-y-2" data-testid="history-series-sidebar">
          <p className="text-xs font-semibold text-gray-500 uppercase">Séries / Anos</p>
          {SERIES.map(serie => {
            const exists = usedSeries.includes(serie);
            const isActive = activeSerie === serie;
            return (
              <div key={serie} className="flex items-center gap-1">
                <button
                  className={`flex-1 text-left px-3 py-2 rounded text-sm transition-colors ${
                    isActive ? 'bg-purple-600 text-white font-medium' :
                    exists ? 'bg-purple-50 text-purple-700 hover:bg-purple-100' :
                    'bg-gray-50 text-gray-400 hover:bg-gray-100'
                  }`}
                  onClick={() => exists ? setActiveSerie(serie) : addRecord(serie)}
                  data-testid={`history-serie-${serie}`}
                >
                  {serie} Ano {exists ? '' : '(+ Adicionar)'}
                </button>
                {exists && (
                  <button
                    onClick={() => removeRecord(serie)}
                    className="p-1 text-red-400 hover:text-red-600"
                    title="Remover série"
                    data-testid={`history-remove-${serie}`}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            );
          })}

          {/* Observações */}
          <div className="mt-4 pt-3 border-t">
            <Label className="text-xs">Observações</Label>
            <textarea
              className="w-full mt-1 p-2 text-xs border rounded resize-none"
              rows={3}
              value={observations}
              onChange={e => setObservations(e.target.value)}
              placeholder="Observações gerais..."
              data-testid="history-observations"
            />
            <Label className="text-xs mt-2">Média de Aprovação</Label>
            <Input
              type="number"
              step="0.1"
              className="mt-1"
              value={mediaAprovacao}
              onChange={e => setMediaAprovacao(parseFloat(e.target.value) || 0)}
              data-testid="history-media-aprovacao"
            />
          </div>
        </div>

        {/* Main content - Formulário da série ativa */}
        <div className="col-span-9" data-testid="history-main-content">
          {activeRecord ? (
            <div className="bg-white rounded-lg border p-4 space-y-4">
              <h2 className="text-base font-semibold text-purple-700 border-b pb-2">
                {activeSerie} Ano
              </h2>

              {/* Dados gerais da série */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <Label className="text-xs">Ano Letivo</Label>
                  <Input
                    type="number"
                    value={activeRecord.ano_letivo}
                    onChange={e => updateRecord(activeSerie, 'ano_letivo', parseInt(e.target.value) || '')}
                    placeholder="2024"
                    data-testid="history-ano-letivo"
                  />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Estabelecimento de Ensino</Label>
                  <Input
                    value={activeRecord.escola}
                    onChange={e => updateRecord(activeSerie, 'escola', e.target.value)}
                    placeholder="Nome da escola"
                    data-testid="history-escola"
                  />
                </div>
                <div className="grid grid-cols-3 gap-1">
                  <div className="col-span-2">
                    <Label className="text-xs">Cidade</Label>
                    <Input
                      value={activeRecord.cidade}
                      onChange={e => updateRecord(activeSerie, 'cidade', e.target.value)}
                      placeholder="Cidade"
                      data-testid="history-cidade"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">UF</Label>
                    <Input
                      value={activeRecord.uf}
                      onChange={e => updateRecord(activeSerie, 'uf', e.target.value)}
                      placeholder="PA"
                      maxLength={2}
                      data-testid="history-uf"
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <Label className="text-xs">Carga Horária Anual</Label>
                  <Input
                    type="number"
                    value={activeRecord.carga_horaria}
                    onChange={e => updateRecord(activeSerie, 'carga_horaria', parseInt(e.target.value) || '')}
                    placeholder="800"
                    data-testid="history-carga-horaria"
                  />
                </div>
                <div>
                  <Label className="text-xs">Resultado</Label>
                  <Select
                    value={activeRecord.resultado}
                    onValueChange={v => updateRecord(activeSerie, 'resultado', v)}
                  >
                    <SelectTrigger data-testid="history-resultado">
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {RESULTADOS.map(r => (
                        <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Notas por componente */}
              <div className="border-t pt-3">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Componentes Curriculares</h3>

                {/* BNCC */}
                {Object.entries(COMPONENTES_BNCC).map(([area, comps]) => (
                  <div key={area} className="mb-3">
                    <p className="text-xs font-semibold text-purple-600 mb-1 uppercase">{area}</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {comps.map(comp => (
                        <div key={comp}>
                          <Label className="text-xs text-gray-600">{comp}</Label>
                          <Input
                            type="number"
                            step="0.1"
                            min="0"
                            max="10"
                            className="h-8 text-sm"
                            value={activeRecord.grades[comp] ?? ''}
                            onChange={e => updateGrade(activeSerie, comp, e.target.value)}
                            placeholder="-"
                            data-testid={`history-grade-${comp.replace(/\s/g, '-')}`}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                {/* Parte Diversificada */}
                <div className="mt-3 pt-2 border-t">
                  <p className="text-xs font-semibold text-amber-600 mb-1 uppercase">Parte Diversificada</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {COMPONENTES_DIVERSIFICADA.map(comp => (
                      <div key={comp}>
                        <Label className="text-xs text-gray-600">{comp}</Label>
                        <Input
                          type="number"
                          step="0.1"
                          min="0"
                          max="10"
                          className="h-8 text-sm"
                          value={activeRecord.grades[comp] ?? ''}
                          onChange={e => updateGrade(activeSerie, comp, e.target.value)}
                          placeholder="-"
                          data-testid={`history-grade-div-${comp.replace(/\s/g, '-')}`}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border p-8 text-center text-gray-400" data-testid="history-empty-state">
              <GraduationCap size={48} className="mx-auto mb-3 opacity-40" />
              <p className="text-sm">Selecione ou adicione uma série na barra lateral para cadastrar o histórico.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
