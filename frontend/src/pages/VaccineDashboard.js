import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { studentsAPI, schoolsAPI, classesAPI } from '@/services/api';
import { formatCPF } from '@/utils/formatters';
import { Search, User, Calendar, School, BookOpen, LogOut, X, Loader2, ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react';
import axios from 'axios';
import { normalizeForSearch } from '@/utils/textSearch';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function VaccineDashboard() {
  const navigate = useNavigate();
  const { user, logout, accessToken: token } = useAuth();
  const [searchType, setSearchType] = useState('name');
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [studentDetails, setStudentDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [allStudents, setAllStudents] = useState([]);
  const [schools, setSchools] = useState({});
  const [classes, setClasses] = useState({});
  const [summary, setSummary] = useState(null);
  const [vaccineStatus, setVaccineStatus] = useState(null); // current student vaccine status
  const [savingStatus, setSavingStatus] = useState(false);
  const academicYear = new Date().getFullYear();

  // Estado para listagem por turma
  const [listYear, setListYear] = useState(new Date().getFullYear());
  const [listSchoolId, setListSchoolId] = useState('');
  const [listClassId, setListClassId] = useState('');
  const [schoolsList, setSchoolsList] = useState([]);
  const [classesList, setClassesList] = useState([]);
  const [classStudents, setClassStudents] = useState([]);
  const [classInfo, setClassInfo] = useState(null);
  const [loadingClass, setLoadingClass] = useState(false);

  const loadSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/vaccines/summary?academic_year=${academicYear}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSummary(res.data);
    } catch (e) { console.error(e); }
  }, [academicYear, token]);

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [studentsResponse, schoolsData, classesData] = await Promise.all([
          studentsAPI.getAll({ page_size: 10000 }),
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        setAllStudents(studentsResponse.items || []);
        const schoolsMap = {};
        schoolsData.forEach(s => { schoolsMap[s.id] = s; });
        setSchools(schoolsMap);
        setSchoolsList(schoolsData.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
        const classesMap = {};
        classesData.forEach(c => { classesMap[c.id] = c; });
        setClasses(classesMap);
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
      }
    };
    loadInitialData();
    loadSummary();
  }, [loadSummary]);

  const searchStudents = useCallback((term, type) => {
    if (!term || term.length < 3) {
      setSearchResults([]);
      return;
    }
    setLoading(true);
    const termNormalized = normalizeForSearch(term);
    const termClean = term.replace(/\D/g, '');
    let results = [];
    if (type === 'name') {
      results = allStudents.filter(student => normalizeForSearch(student.full_name).includes(termNormalized));
    } else {
      results = allStudents.filter(student => student.cpf?.replace(/\D/g, '').includes(termClean));
    }
    setSearchResults(results.slice(0, 10));
    setLoading(false);
  }, [allStudents]);

  useEffect(() => {
    const timer = setTimeout(() => {
      searchStudents(searchTerm, searchType);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm, searchType, searchStudents]);

  const loadStudentDetails = async (student) => {
    setSelectedStudent(student);
    setSearchResults([]);
    setSearchTerm('');
    setLoadingDetails(true);
    setVaccineStatus(null);

    try {
      const fullStudent = await studentsAPI.getById(student.id);
      const school = schools[fullStudent.school_id || student.school_id];
      const classInfo = classes[fullStudent.class_id || student.class_id];

      setStudentDetails({
        ...fullStudent,
        school_name: school?.name || 'Não matriculado',
        class_name: classInfo?.name || 'Não informada',
      });

      // Load vaccine status
      const res = await axios.get(`${API}/vaccines/status/batch?student_ids=${student.id}&academic_year=${academicYear}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setVaccineStatus(res.data[student.id] || 'not_verified');
    } catch (error) {
      console.error('Erro ao carregar detalhes:', error);
      setStudentDetails({
        ...student,
        school_name: schools[student.school_id]?.name || 'Não matriculado',
        class_name: classes[student.class_id]?.name || 'Não informada',
      });
      setVaccineStatus('not_verified');
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleStatusChange = async (newStatus) => {
    if (!selectedStudent || savingStatus) return;
    setSavingStatus(true);
    try {
      await axios.put(`${API}/vaccines/status/${selectedStudent.id}`, {
        status: newStatus,
        academic_year: academicYear
      }, { headers: { Authorization: `Bearer ${token}` } });
      setVaccineStatus(newStatus);
      loadSummary();
    } catch (e) {
      console.error(e);
    }
    setSavingStatus(false);
  };

  const handleLogout = () => { logout(); navigate('/login'); };

  const clearSelection = () => {
    setSelectedStudent(null);
    setStudentDetails(null);
    setVaccineStatus(null);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Não informada';
    try {
      const date = new Date(dateStr + 'T00:00:00');
      return date.toLocaleDateString('pt-BR');
    } catch { return dateStr; }
  };

  const isStudentEnrolled = (details) => {
    if (!details) return false;
    return details.school_name !== 'Não matriculado' && details.school_id;
  };

  // Filtrar turmas pela escola selecionada
  useEffect(() => {
    if (!listSchoolId) {
      setClassesList([]);
      setListClassId('');
      return;
    }
    const filtered = Object.values(classes)
      .filter(c => c.school_id === listSchoolId && (c.academic_year === listYear || !c.academic_year))
      .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    setClassesList(filtered);
    setListClassId('');
    setClassStudents([]);
    setClassInfo(null);
  }, [listSchoolId, listYear, classes]);

  // Carregar alunos da turma selecionada
  useEffect(() => {
    if (!listClassId) {
      setClassStudents([]);
      setClassInfo(null);
      return;
    }
    const load = async () => {
      setLoadingClass(true);
      try {
        const res = await axios.get(`${API}/vaccines/class/${listClassId}/students?academic_year=${listYear}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setClassStudents(res.data.students || []);
        setClassInfo({ name: res.data.class_name, total: res.data.total });
      } catch (e) {
        console.error(e);
        setClassStudents([]);
      }
      setLoadingClass(false);
    };
    load();
  }, [listClassId, listYear, token]);

  const handleClassStudentStatus = async (studentId, newStatus) => {
    setSavingStatus(true);
    try {
      await axios.put(`${API}/vaccines/status/${studentId}`, {
        status: newStatus,
        academic_year: listYear
      }, { headers: { Authorization: `Bearer ${token}` } });
      setClassStudents(prev => prev.map(s =>
        s.id === studentId ? { ...s, vaccine_status: newStatus } : s
      ));
      loadSummary();
    } catch (e) { console.error(e); }
    setSavingStatus(false);
  };

  const yearOptions = [];
  for (let y = new Date().getFullYear(); y >= new Date().getFullYear() - 2; y--) yearOptions.push(y);

  return (
    <div className="min-h-screen bg-gray-50 pb-12" data-testid="vaccine-dashboard">
      <header className="bg-blue-600 text-white shadow-lg sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-4">
              <img src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png" alt="SIGESC" className="w-10 h-10 object-contain" />
              <div>
                <h1 className="text-xl font-bold">SIGESC</h1>
                <p className="text-blue-100 text-sm">Controle de Vacinas</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="font-medium">{user?.full_name || 'Usuário'}</p>
                <p className="text-blue-100 text-sm">Agente de Vacinas</p>
              </div>
              <button onClick={handleLogout} className="p-2 hover:bg-blue-700 rounded-lg transition-colors" data-testid="logout-button">
                <LogOut size={20} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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

        {/* Search Section */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-900">Consulta de Alunos</h2>
          <p className="text-gray-600 mt-1">Busque alunos por nome ou CPF para validar o status vacinal</p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex space-x-4 mb-4">
            <button
              onClick={() => { setSearchType('name'); setSearchTerm(''); setSearchResults([]); }}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${searchType === 'name' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              data-testid="search-by-name-btn"
            >
              Buscar por Nome
            </button>
            <button
              onClick={() => { setSearchType('cpf'); setSearchTerm(''); setSearchResults([]); }}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${searchType === 'cpf' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              data-testid="search-by-cpf-btn"
            >
              Buscar por CPF
            </button>
          </div>

          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={searchType === 'name' ? 'Digite o nome do aluno (mínimo 3 caracteres)...' : 'Digite o CPF do aluno (mínimo 3 dígitos)...'}
              className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-lg"
              data-testid="search-input"
            />
            {loading && (
              <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
                <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
              </div>
            )}
          </div>

          {searchResults.length > 0 && (
            <div className="mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-y-auto">
              {searchResults.map((student) => (
                <button
                  key={student.id}
                  onClick={() => loadStudentDetails(student)}
                  className="w-full px-4 py-3 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0 transition-colors"
                  data-testid={`search-result-${student.id}`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-gray-900">{student.full_name}</p>
                      <p className="text-sm text-gray-500">
                        {student.cpf ? formatCPF(student.cpf) : 'CPF não informado'}
                        {student.school_id && schools[student.school_id] && (
                          <span className="ml-2">• {schools[student.school_id].name}</span>
                        )}
                      </p>
                    </div>
                    <User className="h-5 w-5 text-gray-400" />
                  </div>
                </button>
              ))}
            </div>
          )}

          {searchTerm.length >= 3 && searchResults.length === 0 && !loading && (
            <div className="mt-4 text-center py-4 text-gray-500">Nenhum aluno encontrado.</div>
          )}
          {searchTerm.length > 0 && searchTerm.length < 3 && (
            <div className="mt-4 text-center py-4 text-gray-400">Digite pelo menos 3 caracteres...</div>
          )}
        </div>

        {/* Student Details Card */}
        {selectedStudent && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            {/* Blue header */}
            <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
                    <User className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white" data-testid="student-name">
                      {selectedStudent.full_name}
                    </h3>
                    <p className="text-blue-100">
                      {selectedStudent.cpf ? formatCPF(selectedStudent.cpf) : 'CPF não informado'}
                    </p>
                  </div>
                </div>
                <button onClick={clearSelection} className="p-2 hover:bg-white/10 rounded-lg transition-colors" data-testid="close-details-btn">
                  <X className="h-5 w-5 text-white" />
                </button>
              </div>
            </div>

            {loadingDetails ? (
              <div className="p-8 flex items-center justify-center">
                <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
                <span className="ml-3 text-gray-500">Carregando informações...</span>
              </div>
            ) : studentDetails ? (
              <div className="p-6">
                {(() => {
                  const enrolled = isStudentEnrolled(studentDetails);
                  return (
                    <>
                      {/* Info grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="flex items-start space-x-3">
                          <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <Calendar className="h-5 w-5 text-blue-600" />
                          </div>
                          <div>
                            <p className="text-sm text-gray-500">Data de Nascimento</p>
                            <p className="font-medium text-gray-900" data-testid="student-birth-date">
                              {enrolled ? formatDate(studentDetails.birth_date) : '-'}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-start space-x-3">
                          <div className="w-10 h-10 bg-pink-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <User className="h-5 w-5 text-pink-600" />
                          </div>
                          <div>
                            <p className="text-sm text-gray-500">Nome da Mãe</p>
                            <p className="font-medium text-gray-900" data-testid="student-mother-name">
                              {enrolled ? (studentDetails.mother_name || 'Não informado') : '-'}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-start space-x-3">
                          <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <School className="h-5 w-5 text-green-600" />
                          </div>
                          <div>
                            <p className="text-sm text-gray-500">Escola</p>
                            <p className="font-medium text-gray-900" data-testid="student-school">
                              {studentDetails.school_name}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-start space-x-3">
                          <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <BookOpen className="h-5 w-5 text-purple-600" />
                          </div>
                          <div>
                            <p className="text-sm text-gray-500">Ano/Série</p>
                            <p className="font-medium text-gray-900" data-testid="student-class">
                              {enrolled ? (studentDetails.student_series || studentDetails.class_name || '-') : '-'}
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* Vaccine Status Section */}
                      <div className="mt-6 pt-6 border-t border-gray-200">
                        <p className="text-sm text-gray-500 mb-4">Status Vacinal</p>
                        <div className="flex items-center justify-center gap-6">
                          <button
                            onClick={() => handleStatusChange('up_to_date')}
                            disabled={savingStatus || !enrolled}
                            className={`px-8 py-3 rounded-xl text-base font-bold transition-all border-2 ${
                              vaccineStatus === 'up_to_date'
                                ? 'bg-green-500 text-white border-green-600 shadow-lg'
                                : 'bg-gray-200 text-gray-500 border-gray-300 hover:bg-gray-300'
                            }`}
                            data-testid="btn-up-to-date"
                          >
                            Em dia
                          </button>
                          <button
                            onClick={() => handleStatusChange('not_up_to_date')}
                            disabled={savingStatus || !enrolled}
                            className={`px-8 py-3 rounded-xl text-base font-bold transition-all border-2 ${
                              vaccineStatus === 'not_up_to_date'
                                ? 'bg-yellow-500 text-white border-yellow-600 shadow-lg'
                                : 'bg-gray-200 text-gray-500 border-gray-300 hover:bg-gray-300'
                            }`}
                            data-testid="btn-not-up-to-date"
                          >
                            Pendente
                          </button>
                          {savingStatus && <Loader2 size={20} className="text-blue-500 animate-spin" />}
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            ) : null}
          </div>
        )}

        {/* Empty state */}
        {!selectedStudent && searchResults.length === 0 && !listClassId && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Search className="h-8 w-8 text-blue-600" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">Busque um aluno</h3>
            <p className="text-gray-500 max-w-md mx-auto">
              Digite o nome ou CPF do aluno no campo de busca acima para validar o status vacinal.
            </p>
          </div>
        )}

        {/* ===== SEÇÃO: Listagem por Turma ===== */}
        <div className="mt-10">
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-gray-900">Listagem por Turma</h2>
            <p className="text-gray-600 mt-1">Visualize o status vacinal de todos os alunos da turma</p>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano</label>
                <select value={listYear} onChange={e => setListYear(Number(e.target.value))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  data-testid="list-year-filter">
                  {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                <select value={listSchoolId} onChange={e => setListSchoolId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  data-testid="list-school-filter">
                  <option value="">Selecione uma escola</option>
                  {schoolsList.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                <select value={listClassId} onChange={e => setListClassId(e.target.value)}
                  disabled={!listSchoolId}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
                  data-testid="list-class-filter">
                  <option value="">Selecione uma turma</option>
                  {classesList.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            </div>
          </div>

          {loadingClass && (
            <div className="bg-white rounded-xl shadow-sm border p-8 flex items-center justify-center">
              <Loader2 className="h-6 w-6 text-blue-500 animate-spin" />
              <span className="ml-3 text-gray-500">Carregando alunos...</span>
            </div>
          )}

          {!loadingClass && listClassId && classStudents.length === 0 && (
            <div className="bg-white rounded-xl shadow-sm border p-8 text-center text-gray-500">
              Nenhum aluno encontrado nesta turma.
            </div>
          )}

          {!loadingClass && classStudents.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-white font-bold">{classInfo?.name || ''}</h3>
                  <span className="bg-white/20 text-white text-sm px-3 py-1 rounded-full">
                    {classInfo?.total || 0} alunos
                  </span>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider w-8">Nº</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Aluno(a)</th>
                      <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider w-28">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {classStudents.map((student, idx) => {
                      const vSt = student.vaccine_status;
                      const dotColor = vSt === 'up_to_date' ? 'bg-green-500' : vSt === 'not_up_to_date' ? 'bg-yellow-400' : 'bg-gray-300';
                      const dotTitle = vSt === 'up_to_date' ? 'Em dia' : vSt === 'not_up_to_date' ? 'Pendente' : 'Não verificado';
                      return (
                        <tr key={student.id} className="hover:bg-gray-50 transition-colors" data-testid={`class-student-${student.id}`}>
                          <td className="px-6 py-3 text-sm text-gray-500">{idx + 1}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              <span className={`inline-block w-3 h-3 rounded-full flex-shrink-0 ${dotColor}`} title={dotTitle} />
                              <span className="font-medium text-gray-900 text-sm">{student.full_name}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex items-center justify-center gap-1.5">
                              <button
                                onClick={() => handleClassStudentStatus(student.id, 'up_to_date')}
                                disabled={savingStatus}
                                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                                  vSt === 'up_to_date'
                                    ? 'bg-green-500 text-white shadow-sm'
                                    : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
                                }`}
                                data-testid={`class-btn-uptodate-${student.id}`}
                              >
                                Em dia
                              </button>
                              <button
                                onClick={() => handleClassStudentStatus(student.id, 'not_up_to_date')}
                                disabled={savingStatus}
                                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                                  vSt === 'not_up_to_date'
                                    ? 'bg-yellow-500 text-white shadow-sm'
                                    : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
                                }`}
                                data-testid={`class-btn-notuptodate-${student.id}`}
                              >
                                Pendente
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!listClassId && !loadingClass && (
            <div className="bg-white rounded-xl shadow-sm border p-8 text-center text-gray-400">
              Selecione uma escola e turma para visualizar a listagem.
            </div>
          )}
        </div>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 py-3 px-4 text-center text-gray-500 text-sm border-t border-gray-200 bg-white z-30">
        <span>
          © 2026 Desenvolvido por{' '}
          <a href="https://www.facebook.com/prof.gutenbergbarroso" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-700 hover:underline">
            Gutenberg Barroso
          </a>
        </span>
      </footer>
    </div>
  );
}
