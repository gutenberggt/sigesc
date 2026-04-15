import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { studentsAPI, schoolsAPI, classesAPI } from '@/services/api';
import { formatCPF } from '@/utils/formatters';
import { Search, User, School, BookOpen, LogOut, Loader2, ShieldCheck, ShieldAlert, ShieldQuestion, Save, CheckCircle2, Filter } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VACCINE_LABELS = {
  not_verified: { label: 'Não verificado', color: 'bg-gray-100 text-gray-600', dot: 'bg-gray-400' },
  up_to_date: { label: 'Em dia', color: 'bg-green-100 text-green-700', dot: 'bg-green-500' },
  not_up_to_date: { label: 'Não está em dia', color: 'bg-yellow-100 text-yellow-700', dot: 'bg-yellow-500' },
};

export default function VaccineDashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [allStudents, setAllStudents] = useState([]);
  const [schools, setSchools] = useState({});
  const [classes, setClasses] = useState({});
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [savedId, setSavedId] = useState(null);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [schoolsList, setSchoolsList] = useState([]);
  const academicYear = new Date().getFullYear();

  const token = localStorage.getItem('accessToken');

  const loadSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/vaccines/summary?academic_year=${academicYear}${selectedSchool ? `&school_id=${selectedSchool}` : ''}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSummary(res.data);
    } catch (e) { console.error(e); }
  }, [academicYear, selectedSchool, token]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [studentsResponse, schoolsData, classesData] = await Promise.all([
          studentsAPI.getAll({ page_size: 10000 }),
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        setAllStudents(studentsResponse.items || []);
        const sMap = {};
        schoolsData.forEach(s => { sMap[s.id] = s; });
        setSchools(sMap);
        setSchoolsList(schoolsData.sort((a, b) => a.name.localeCompare(b.name)));
        const cMap = {};
        classesData.forEach(c => { cMap[c.id] = c; });
        setClasses(cMap);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  // Load vaccine statuses for visible students
  const [vaccineStatuses, setVaccineStatuses] = useState({});

  const loadVaccineStatuses = useCallback(async (studentIds) => {
    if (!studentIds.length) return;
    try {
      const res = await axios.get(`${API}/vaccines/status/batch?student_ids=${studentIds.join(',')}&academic_year=${academicYear}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setVaccineStatuses(prev => ({ ...prev, ...res.data }));
    } catch (e) { console.error(e); }
  }, [academicYear, token]);

  const filteredStudents = useCallback(() => {
    let results = allStudents;
    if (selectedSchool) results = results.filter(s => s.school_id === selectedSchool);
    if (searchTerm.length >= 3) {
      const term = searchTerm.toLowerCase();
      results = results.filter(s => s.full_name?.toLowerCase().includes(term));
    }
    if (statusFilter) {
      results = results.filter(s => {
        const st = vaccineStatuses[s.id] || 'not_verified';
        return st === statusFilter;
      });
    }
    return results.slice(0, 100);
  }, [allStudents, selectedSchool, searchTerm, statusFilter, vaccineStatuses]);

  const visibleStudents = filteredStudents();

  useEffect(() => {
    const ids = visibleStudents.map(s => s.id);
    if (ids.length > 0) loadVaccineStatuses(ids);
  }, [visibleStudents.length, selectedSchool, loadVaccineStatuses]);

  const handleStatusChange = async (studentId, newStatus) => {
    setSavingId(studentId);
    try {
      await axios.put(`${API}/vaccines/status/${studentId}`, {
        status: newStatus,
        academic_year: academicYear
      }, { headers: { Authorization: `Bearer ${token}` } });
      setVaccineStatuses(prev => ({ ...prev, [studentId]: newStatus }));
      setSavedId(studentId);
      setTimeout(() => setSavedId(null), 1500);
      loadSummary();
    } catch (e) {
      console.error(e);
    }
    setSavingId(null);
  };

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <div className="min-h-screen bg-gray-50" data-testid="vaccine-dashboard">
      <header className="bg-teal-600 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-4">
              <img src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png" alt="SIGESC" className="w-10 h-10 object-contain" />
              <div>
                <h1 className="text-xl font-bold">SIGESC</h1>
                <p className="text-teal-100 text-sm">Controle de Vacinas</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="font-medium">{user?.full_name || 'Usuário'}</p>
                <p className="text-teal-100 text-sm">Agente de Vacinas</p>
              </div>
              <button onClick={handleLogout} className="p-2 hover:bg-teal-700 rounded-lg transition-colors" data-testid="logout-button">
                <LogOut size={20} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8" data-testid="vaccine-summary">
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><User className="h-5 w-5 text-blue-600" /></div>
                <div>
                  <p className="text-sm text-gray-500">Total de Alunos</p>
                  <p className="text-2xl font-bold text-gray-900" data-testid="total-students">{summary.total_students}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"><ShieldCheck className="h-5 w-5 text-green-600" /></div>
                <div>
                  <p className="text-sm text-gray-500">Em Dia</p>
                  <p className="text-2xl font-bold text-green-600" data-testid="up-to-date">{summary.up_to_date}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center"><ShieldAlert className="h-5 w-5 text-yellow-600" /></div>
                <div>
                  <p className="text-sm text-gray-500">Não está em Dia</p>
                  <p className="text-2xl font-bold text-yellow-600" data-testid="not-up-to-date">{summary.not_up_to_date}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center"><ShieldQuestion className="h-5 w-5 text-gray-500" /></div>
                <div>
                  <p className="text-sm text-gray-500">Não Verificado</p>
                  <p className="text-2xl font-bold text-gray-600" data-testid="not-verified">{summary.not_verified}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
              <select value={selectedSchool} onChange={e => setSelectedSchool(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500" data-testid="school-filter">
                <option value="">Todas as escolas</option>
                {schoolsList.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status Vacinal</label>
              <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500" data-testid="status-filter">
                <option value="">Todos</option>
                <option value="not_verified">Não verificado</option>
                <option value="up_to_date">Em dia</option>
                <option value="not_up_to_date">Não está em dia</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Buscar por nome</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                  placeholder="Mínimo 3 caracteres..."
                  className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500" data-testid="search-input" />
              </div>
            </div>
          </div>
        </div>

        {/* Student List */}
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="px-6 py-4 border-b bg-gray-50">
            <h3 className="font-semibold text-gray-900">
              Alunos {visibleStudents.length > 0 && <span className="text-gray-500 font-normal">({visibleStudents.length} exibidos)</span>}
            </h3>
          </div>

          {loading ? (
            <div className="p-12 flex items-center justify-center">
              <Loader2 className="h-8 w-8 text-teal-500 animate-spin" />
              <span className="ml-3 text-gray-500">Carregando...</span>
            </div>
          ) : visibleStudents.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              {searchTerm.length >= 3 ? 'Nenhum aluno encontrado.' : 'Selecione filtros ou busque pelo nome.'}
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {visibleStudents.map(student => {
                const vStatus = vaccineStatuses[student.id] || 'not_verified';
                const info = VACCINE_LABELS[vStatus];
                const schoolName = schools[student.school_id]?.name || '';
                const className = classes[student.class_id]?.name || '';
                const isSaving = savingId === student.id;
                const justSaved = savedId === student.id;

                return (
                  <div key={student.id} className="px-6 py-4 hover:bg-gray-50 transition-colors" data-testid={`student-row-${student.id}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4 min-w-0 flex-1">
                        <div className={`w-3 h-3 rounded-full flex-shrink-0 ${info.dot}`} title={info.label} />
                        <div className="min-w-0">
                          <p className="font-medium text-gray-900 truncate">{student.full_name}</p>
                          <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
                            {schoolName && <span className="flex items-center gap-1"><School size={11} />{schoolName}</span>}
                            {className && <span className="flex items-center gap-1"><BookOpen size={11} />{className}</span>}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 flex-shrink-0">
                        <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${info.color}`}>
                          {info.label}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => handleStatusChange(student.id, 'up_to_date')}
                            disabled={isSaving}
                            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                              vStatus === 'up_to_date'
                                ? 'bg-green-600 text-white shadow-sm'
                                : 'bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700'
                            }`}
                            data-testid={`btn-up-to-date-${student.id}`}
                          >
                            Em dia
                          </button>
                          <button
                            onClick={() => handleStatusChange(student.id, 'not_up_to_date')}
                            disabled={isSaving}
                            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                              vStatus === 'not_up_to_date'
                                ? 'bg-yellow-500 text-white shadow-sm'
                                : 'bg-gray-100 text-gray-600 hover:bg-yellow-100 hover:text-yellow-700'
                            }`}
                            data-testid={`btn-not-up-to-date-${student.id}`}
                          >
                            Pendente
                          </button>
                          {isSaving && <Loader2 size={16} className="text-teal-500 animate-spin" />}
                          {justSaved && <CheckCircle2 size={16} className="text-green-500" />}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
