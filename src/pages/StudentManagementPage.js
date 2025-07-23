import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

function StudentManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [students, setStudents] = useState([]);
  const [editingStudent, setEditingStudent] = useState(null);
  const [searchTerm, setSearchTerm] = useState(''); // Estado para o campo de busca

  // --- Estados dos Dados Pessoais ---
  const [cpf, setCpf] = useState('');
  const [nomeCompleto, setNomeCompleto] = useState('');
  const [nomeSocialAfetivo, setNomeSocialAfetivo] = useState('');
  const [sexo, setSexo] = useState('Nao Informado');
  const [estadoCivil, setEstadoCivil] = useState('Solteiro(a)');
  const [dataNascimento, setDataNascimento] = useState('');
  const [nacionalidade, setNacionalidade] = useState('');
  const [raca, setRaca] = useState('Nao Declarada');
  const [religiao, setReligiao] = useState('');
  const [naturalidadeCidade, setNaturalidadeCidade] = useState('');
  const [naturalidadeEstado, setNaturalidadeEstado] = useState('');
  const [falecido, setFalecido] = useState('nao'); // 'sim' ou 'nao'

  // --- Estados de Informações Familiares ---
  const [nomePai, setNomePai] = useState('');
  const [nomeMae, setNomeMae] = useState('');

  // --- Estados de Documentação ---
  const [rgNumero, setRgNumero] = useState('');
  const [rgDataEmissao, setRgDataEmissao] = useState('');
  const [rgOrgaoEmissor, setRgOrgaoEmissor] = useState('');
  const [rgEstado, setRgEstado] = useState('');
  const [nisPisPasep, setNisPisPasep] = useState('');
  const [carteiraSUS, setCarteiraSUS] = useState('');
  const [certidaoTipo, setCertidaoTipo] = useState('Nascimento');
  const [certidaoEstado, setCertidaoEstado] = useState('');
  const [certidaoCartorio, setCertidaoCartorio] = useState('');
  const [certidaoDataEmissao, setCertidaoDataEmissao] = useState('');
  // Campos de documentação removidos (Passaporte, Carteira de Trabalho, Título de Eleitor) não possuem useState aqui.

  // --- Estados de Endereço ---
  const [cep, setCep] = useState('');
  const [rua, setRua] = useState(''); // GARANTIDO: Declaração do estado 'rua'
  const [enderecoNumero, setEnderecoNumero] = useState('');
  const [enderecoComplemento, setEnderecoComplemento] = useState('');
  const [enderecoBairro, setEnderecoBairro] = useState(''); // GARANTIDO: Declaração do estado 'enderecoBairro'
  const [municipioResidencia, setMunicipioResidencia] = useState('');
  const [paisResidencia, setPaisResidencia] = useState('');
  const [zonaResidencia, setZonaResidencia] = useState('urbana');
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState(''); // Select para localização diferenciada

  // --- Estados de Contato ---
  const [telefoneResidencial, setTelefoneResidencial] = useState('');
  const [celular, setCelular] = useState('');
  const [telefoneAdicional, setTelefoneAdicional] = useState('');
  const [fax, setFax] = useState('');
  const [emailContato, setEmailContato] = useState('');

  // --- Estados de Trabalho e Renda (Removidos) ---
  // Os campos de trabalho e renda foram removidos da declaração de estados.

  // --- Estados de Arquivos ---
  const [fotoPessoal, setFotoPessoal] = useState(null);
  const [arquivosAdicionais, setArquivosAdicionais] = useState([]);


  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Funções de formatação (adaptadas)
  const formatCPF = (value) => {
    value = value.replace(/\D/g, '');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    return value.substring(0, 14);
  };
  const formatRG = (value) => value.replace(/\D/g, '').substring(0, 15);
  const formatNIS = (value) => value.replace(/\D/g, '').substring(0, 11);
  const formatCarteiraSUS = (value) => value.replace(/\D/g, '').substring(0, 15);
  const formatTelefone = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
    value = value.replace(/(\d)(\d{4})$/, '$1-$2');
    return value;
  };
  const formatCEP = (value) => {
    value = value.replace(/\D/g, '');
    value = value.replace(/^(\d{5})(\d)/, '$1-$2');
    return value.substring(0, 9);
  };

  // Limpa o formulário
  const resetForm = () => {
    setCpf('');
    setNomeCompleto('');
    setNomeSocialAfetivo('');
    setSexo('Nao Informado');
    setEstadoCivil('Solteiro(a)');
    setDataNascimento('');
    setNacionalidade('');
    setRaca('Nao Declarada');
    setReligiao('');
    setNaturalidadeCidade('');
    setNaturalidadeEstado('');
    setFalecido('nao');

    setNomePai('');
    setNomeMae('');

    setRgNumero('');
    setRgDataEmissao('');
    setRgOrgaoEmissor('');
    setRgEstado('');
    setNisPisPasep('');
    setCarteiraSUS('');
    setCertidaoTipo('Nascimento');
    setCertidaoEstado('');
    setCertidaoCartorio('');
    setCertidaoDataEmissao('');
    // Campos de documentação removidos (Passaporte, Carteira de Trabalho, Título de Eleitor) foram removidos de seus resets.

    setCep('');
    setRua(''); 
    setEnderecoNumero('');
    setEnderecoComplemento('');
    setEnderecoBairro(''); // Resetar estado 'enderecoBairro'
    setMunicipioResidencia('');
    setPaisResidencia('');
    setZonaResidencia('urbana');
    setLocalizacaoDiferenciada(''); 
    
    setTelefoneResidencial('');
    setCelular('');
    setTelefoneAdicional('');
    setFax('');
    setEmailContato('');

    // Campos de Trabalho e Renda (removidos) também foram removidos de seus resets.

    setFotoPessoal(null);
    setArquivosAdicionais([]);

    setErrorMessage('');
    setSuccessMessage('');
    setEditingStudent(null);
  };

  // Filtra alunos para a busca (mantido)
  const filteredStudents = students.filter(student =>
    (student.nomeCompleto && student.nomeCompleto.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (student.cpf && student.cpf.includes(searchTerm))
  );

  // Efeito para carregar alunos existentes (apenas para admins) (mantido)
  useEffect(() => {
    if (!loading) {
      if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
        navigate('/dashboard'); 
        return;
      }

      const fetchStudents = async () => {
        try {
          const studentsCol = collection(db, 'students'); 
          const studentSnapshot = await getDocs(studentsCol);
          const studentList = studentSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setStudents(studentList);
        } catch (error) {
          console.error("Erro ao buscar alunos:", error);
          setErrorMessage("Erro ao carregar lista de alunos.");
        }
      };
      fetchStudents();
    }
  }, [loading, userData, navigate]);

  // Função para lidar com o cadastro/edição de aluno
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    // Validações básicas (adicione mais conforme necessário)
    if (!nomeCompleto || !cpf || !dataNascimento || !nomeMae || !municipioResidencia) {
      setErrorMessage('Nome completo, CPF, Data de Nascimento, Nome da Mãe e Município de Residência são obrigatórios.');
      return;
    }
    // Adicionar validação de CPF (se precisar)
    // if (!validateCPF(cpf)) {
    //   setErrorMessage('CPF inválido.');
    //   return;
    // }

    // Objeto com os dados do aluno
    const studentData = {
      // Dados Pessoais
      cpf: cpf.replace(/\D/g, ''),
      nomeCompleto: nomeCompleto.toUpperCase(),
      nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
      sexo,
      estadoCivil,
      dataNascimento,
      nacionalidade: nacionalidade.toUpperCase(),
      raca,
      religiao: religiao.toUpperCase(),
      naturalidadeCidade: naturalidadeCidade.toUpperCase(),
      naturalidadeEstado: naturalidadeEstado.toUpperCase(),
      falecido: falecido === 'sim',

      // Informações Familiares
      nomePai: nomePai.toUpperCase(),
      nomeMae: nomeMae.toUpperCase(),

      // Documentação
      rgNumero: rgNumero.replace(/\D/g, ''),
      rgDataEmissao,
      rgOrgaoEmissor: rgOrgaoEmissor.toUpperCase(),
      rgEstado: rgEstado.toUpperCase(),
      nisPisPasep: nisPisPasep.replace(/\D/g, ''),
      carteiraSUS: carteiraSUS.replace(/\D/g, ''),
      certidaoTipo,
      certidaoEstado: certidaoEstado.toUpperCase(),
      certidaoCartorio: certidaoCartorio.toUpperCase(),
      certidaoDataEmissao,
      // Passaporte, Carteira de Trabalho, Título de Eleitor foram removidos de studentData

      // Endereço
      cep: cep.replace(/\D/g, ''),
      enderecoLogradouro: rua.toUpperCase(), // CORREÇÃO AQUI
      enderecoNumero,
      enderecoComplemento: enderecoComplemento.toUpperCase(),
      enderecoBairro: enderecoBairro.toUpperCase(), // CORREÇÃO AQUI
      municipioResidencia: municipioResidencia.toUpperCase(),
      paisResidencia: paisResidencia.toUpperCase(),
      zonaResidencia,
      localizacaoDiferenciada, // Campo atualizado

      // Contato
      telefoneResidencial: telefoneResidencial.replace(/\D/g, ''),
      celular: celular.replace(/\D/g, ''),
      telefoneAdicional: telefoneAdicional.replace(/\D/g, ''),
      fax: fax.replace(/\D/g, ''),
      emailContato,

      // Trabalho e Renda: removido de studentData

      // Arquivos (salvaria as URLs após upload para Firebase Storage)
      // fotoPessoal: 'url_da_foto_aqui',
      // arquivosAdicionais: ['url_arquivo1_aqui', 'url_arquivo2_aqui'],

      dataCadastro: new Date(),
      ultimaAtualizacao: new Date(),
    };

    try {
      if (editingStudent) {
        const studentDocRef = doc(db, 'students', editingStudent.id);
        await updateDoc(studentDocRef, studentData);
        setSuccessMessage('Dados do aluno atualizados com sucesso!');
        setStudents(students.map(s => s.id === editingStudent.id ? { ...s, ...studentData } : s));
      } else {
        await addDoc(collection(db, 'students'), studentData);
        setSuccessMessage('Aluno cadastrado com sucesso!');
        const studentsCol = collection(db, 'students');
        const studentSnapshot = await getDocs(studentsCol);
        const studentList = studentSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        setStudents(studentList);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar aluno:", error);
      setErrorMessage("Erro ao salvar dados do aluno: " + error.message);
    }
  };

  // Funções para a tabela
  const handleEdit = (student) => {
    setEditingStudent(student);
    setCpf(student.cpf || '');
    setNomeCompleto(student.nomeCompleto || '');
    setNomeSocialAfetivo(student.nomeSocialAfetivo || '');
    setSexo(student.sexo || 'Nao Informado');
    setEstadoCivil(student.estadoCivil || 'Solteiro(a)');
    setDataNascimento(student.dataNascimento || '');
    setNacionalidade(student.nacionalidade || '');
    setRaca(student.raca || 'Nao Declarada');
    setReligiao(student.religiao || '');
    setNaturalidadeCidade(student.naturalidadeCidade || '');
    setNaturalidadeEstado(student.naturalidadeEstado || '');
    setFalecido(student.falecido ? 'sim' : 'nao');

    setNomePai(student.nomePai || '');
    setNomeMae(student.nomeMae || '');

    setRgNumero(student.rgNumero || '');
    setRgDataEmissao(student.rgDataEmissao || '');
    setRgOrgaoEmissor(student.rgOrgaoEmissor || '');
    setRgEstado(student.rgEstado || '');
    setNisPisPasep(student.nisPisPasep || '');
    setCarteiraSUS(student.carteiraSUS || '');
    setCertidaoTipo(student.certidaoTipo || 'Nascimento');
    setCertidaoEstado(student.certidaoEstado || '');
    setCertidaoCartorio(student.certidaoCartorio || '');
    setCertidaoDataEmissao(student.certidaoDataEmissao || '');
    // Campos removidos (Passaporte, Carteira de Trabalho, Título de Eleitor) foram removidos dos resets de handleEdit.

    setCep(student.cep || '');
    setRua(student.enderecoLogradouro || ''); // Popula o estado 'rua'
    setEnderecoNumero(student.enderecoNumero || '');
    setEnderecoComplemento(student.enderecoComplemento || '');
    setEnderecoBairro(student.enderecoBairro || ''); // Popula o estado 'enderecoBairro'
    setMunicipioResidencia(student.municipioResidencia || '');
    setPaisResidencia(student.paisResidencia || '');
    setZonaResidencia(student.zonaResidencia || 'urbana');
    setLocalizacaoDiferenciada(student.localizacaoDiferenciada || ''); 

    setTelefoneResidencial(student.telefoneResidencial || '');
    setCelular(student.celular || '');
    setTelefoneAdicional(student.telefoneAdicional || '');
    setFax(student.fax || '');
    setEmailContato(student.emailContato || '');

    // Campos de Trabalho e Renda (removidos) também foram removidos dos resets de handleEdit.

    setFotoPessoal(student.fotoPessoal || null);
    setArquivosAdicionais(student.arquivosAdicionais || []);

    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleDelete = async (studentId) => {
    if (window.confirm('Tem certeza que deseja excluir este aluno? Esta ação não pode ser desfeita!')) {
      try {
        await deleteDoc(doc(db, 'students', studentId));
        setSuccessMessage('Aluno excluído com sucesso!');
        setStudents(students.filter(student => student.id !== studentId));
      } catch (error) {
        console.error("Erro ao excluir aluno:", error);
        setErrorMessage("Erro ao excluir aluno: " + error.message);
      }
    }
  };

  // Verificação de permissão (apenas admins podem acessar)
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
    return (
      <div className="flex justify-center items-center h-screen text-red-600 font-bold">
        Acesso Negado: Você não tem permissão para acessar esta página.
      </div>
    );
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingStudent ? 'Editar Aluno' : 'Cadastrar Novo Aluno'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        <input
          type="text"
          placeholder="Buscar aluno por nome ou CPF..."
          className="w-full p-2 border border-gray-300 rounded-md mb-4"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 🧍 Dados Pessoais */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Pessoais</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label htmlFor="cpf" className="block text-sm font-medium text-gray-700">CPF <span className="text-red-500">*</span></label>
                <input type="text" id="cpf" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCPF(cpf)} onChange={(e) => setCpf(e.target.value)} maxLength="14" required />
              </div>
              <div className="col-span-3">
                <label htmlFor="nomeCompleto" className="block text-sm font-medium text-gray-700">Nome completo <span className="text-red-500">*</span></label>
                <input type="text" id="nomeCompleto" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeCompleto} onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())} required />
              </div>
              <div className="col-span-2">
                <label htmlFor="nomeSocialAfetivo" className="block text-sm font-medium text-gray-700">Nome social e/ou afetivo</label>
                <input type="text" id="nomeSocialAfetivo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeSocialAfetivo} onChange={(e) => setNomeSocialAfetivo(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="sexo" className="block text-sm font-medium text-gray-700">Sexo</label>
                <select id="sexo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={sexo} onChange={(e) => setSexo(e.target.value)}>
                  <option value="Nao Informado">Não Informado</option>
                  <option value="Masculino">Masculino</option>
                  <option value="Feminino">Feminino</option>
                  <option value="Outro">Outro</option>
                </select>
              </div>
              <div>
                <label htmlFor="estadoCivil" className="block text-sm font-medium text-gray-700">Estado civil</label>
                <select id="estadoCivil" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={estadoCivil} onChange={(e) => setEstadoCivil(e.target.value)}>
                  <option value="Solteiro(a)">Solteiro(a)</option>
                  <option value="Casado(a)">Casado(a)</option>
                  <option value="Divorciado(a)">Divorciado(a)</option>
                  <option value="Viúvo(a)">Viúvo(a)</option>
                </select>
              </div>
              <div>
                <label htmlFor="dataNascimento" className="block text-sm font-medium text-gray-700">Data de nascimento <span className="text-red-500">*</span></label>
                <input type="date" id="dataNascimento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={dataNascimento} onChange={(e) => setDataNascimento(e.target.value)} required />
              </div>
              <div>
                <label htmlFor="nacionalidade" className="block text-sm font-medium text-gray-700">Nacionalidade</label>
                <input type="text" id="nacionalidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nacionalidade} onChange={(e) => setNacionalidade(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="raca" className="block text-sm font-medium text-gray-700">Raça</label>
                <select id="raca" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={raca} onChange={(e) => setRaca(e.target.value)}>
                  <option value="Nao Declarada">Não Declarada</option>
                  <option value="Branca">Branca</option>
                  <option value="Preta">Preta</option>
                  <option value="Parda">Parda</option>
                  <option value="Amarela">Amarela</option>
                  <option value="Indígena">Indígena</option>
                </select>
              </div>
              <div className="col-span-2">
                <label htmlFor="religiao" className="block text-sm font-medium text-gray-700">Religião</label>
                <input type="text" id="religiao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={religiao} onChange={(e) => setReligiao(e.target.value.toUpperCase())} />
              </div>
              <div className="col-span-2">
                <label htmlFor="naturalidadeCidade" className="block text-sm font-medium text-gray-700">Naturalidade (Cidade)</label>
                <input type="text" id="naturalidadeCidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={naturalidadeCidade} onChange={(e) => setNaturalidadeCidade(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="naturalidadeEstado" className="block text-sm font-medium text-gray-700">Naturalidade (Estado)</label>
                <input type="text" id="naturalidadeEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={naturalidadeEstado} onChange={(e) => setNaturalidadeEstado(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="falecido" className="block text-sm font-medium text-gray-700">Falecido?</label>
                <select id="falecido" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={falecido} onChange={(e) => setFalecido(e.target.value)}>
                  <option value="nao">Não</option>
                  <option value="sim">Sim</option>
                </select>
              </div>
            </div>
          </div>

          {/* 👨‍👩‍👧‍👦 Informações Familiares */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Informações Familiares</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="nomePai" className="block text-sm font-medium text-gray-700">Nome do Pai</label>
                <input type="text" id="nomePai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomePai} onChange={(e) => setNomePai(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="nomeMae" className="block text-sm font-medium text-gray-700">Nome da Mãe <span className="text-red-500">*</span></label>
                <input type="text" id="nomeMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeMae} onChange={(e) => setNomeMae(e.target.value.toUpperCase())} required />
              </div>
            </div>
          </div>

          {/* 🪪 Documentação */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Documentação</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-2">
                <label htmlFor="rgNumero" className="block text-sm font-medium text-gray-700">RG (Número)</label>
                <input type="text" id="rgNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatRG(rgNumero)} onChange={(e) => setRgNumero(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="rgDataEmissao" className="block text-sm font-medium text-gray-700">RG (Data de Emissão)</label>
                <input type="date" id="rgDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={rgDataEmissao} onChange={(e) => setRgDataEmissao(e.target.value)} />
              </div>
              <div>
                <label htmlFor="rgOrgaoEmissor" className="block text-sm font-medium text-gray-700">RG (Órgão Emissor)</label>
                <input type="text" id="rgOrgaoEmissor" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rgOrgaoEmissor} onChange={(e) => setRgOrgaoEmissor(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="rgEstado" className="block text-sm font-medium text-gray-700">RG (Estado)</label>
                <input type="text" id="rgEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rgEstado} onChange={(e) => setRgEstado(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="nisPisPasep" className="block text-sm font-medium text-gray-700">NIS (PIS/PASEP)</label>
                <input type="text" id="nisPisPasep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatNIS(nisPisPasep)} onChange={(e) => setNisPisPasep(e.target.value)} maxLength="11" />
              </div>
              <div className="col-span-2">
                <label htmlFor="carteiraSUS" className="block text-sm font-medium text-gray-700">Carteira do SUS</label>
                <input type="text" id="carteiraSUS" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCarteiraSUS(carteiraSUS)} onChange={(e) => setCarteiraSUS(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="certidaoTipo" className="block text-sm font-medium text-gray-700">Tipo de certidão civil</label>
                <select id="certidaoTipo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={certidaoTipo} onChange={(e) => setCertidaoTipo(e.target.value)}>
                  <option value="Nascimento">Nascimento</option>
                  <option value="Casamento">Casamento</option>
                </select>
              </div>
              <div>
                <label htmlFor="certidaoEstado" className="block text-sm font-medium text-gray-700">Certidão (Estado)</label>
                <input type="text" id="certidaoEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={certidaoEstado} onChange={(e) => setCertidaoEstado(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="certidaoCartorio" className="block text-sm font-medium text-gray-700">Certidão (Cartório)</label>
                <input type="text" id="certidaoCartorio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={certidaoCartorio} onChange={(e) => setCertidaoCartorio(e.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="certidaoDataEmissao" className="block text-sm font-medium text-gray-700">Certidão (Data de Emissão)</label>
                <input type="date" id="certidaoDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={certidaoDataEmissao} onChange={(e) => setCertidaoDataEmissao(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 🏠 Endereço */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Endereço</h3>
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-6">
                <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
                <input type="text" id="rua" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={rua} onChange={(e) => setRua(e.target.value)} />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
                <input type="text" id="numero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={enderecoNumero} onChange={(e) => setEnderecoNumero(e.target.value)} />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
                <input type="text" id="complemento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={enderecoComplemento} onChange={(e) => setEnderecoComplemento(e.target.value.toUpperCase())} />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
                <input type="text" id="bairro" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={enderecoBairro} onChange={(e) => setEnderecoBairro(e.target.value.toUpperCase())} />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="municipioResidencia" className="block text-sm font-medium text-gray-700">Município <span className="text-red-500">*</span></label>
                <input type="text" id="municipioResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={municipioResidencia} onChange={(e) => setMunicipioResidencia(e.target.value.toUpperCase())} required />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
                <input type="text" id="cep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCEP(cep)} onChange={(e) => setCep(e.target.value)} maxLength="9" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="zonaResidencia" className="block text-sm font-medium text-gray-700">Zona de residência</label>
                <select id="zonaResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={zonaResidencia} onChange={(e) => setZonaResidencia(e.target.value)}>
                  <option value="urbana">Urbana</option>
                  <option value="rural">Rural</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8">
                <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                >
                  <option value="">Selecione</option>
                  <option value="Não está em área de localização diferenciada">Não está em área de localização diferenciada</option>
                  <option value="Área rural">Área rural</option>
                  <option value="Área indígena">Área indígena</option>
                  <option value="Área de assentamento">Área de assentamento</option>
                  <option value="Área quilombola">Área quilombola</option>
                  <option value="Área ribeirinha">Área ribeirinha</option>
                  <option value="Área de comunidade tradicional">Área de comunidade tradicional</option>
                  <option value="Área de difícil acesso">Área de difícil acesso</option>
                  <option value="Área de fronteira">Área de fronteira</option>
                  <option value="Área urbana periférica">Área urbana periférica</option>
                  <option value="Área de zona de conflito">Área de zona de conflito</option>
                  <option value="Área de vulnerabilidade social">Área de vulnerabilidade social</option>
                </select>
              </div>
            </div>
          </div>

          {/* 📞 Contato */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Contato</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="telefoneResidencial" className="block text-sm font-medium text-gray-700">Telefone residencial</label>
                <input type="tel" id="telefoneResidencial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneResidencial)} onChange={(e) => setTelefoneResidencial(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="celular" className="block text-sm font-medium text-gray-700">Celular</label>
                <input type="tel" id="celular" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(celular)} onChange={(e) => setCelular(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="telefoneAdicional" className="block text-sm font-medium text-gray-700">Telefone adicional</label>
                <input type="tel" id="telefoneAdicional" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneAdicional)} onChange={(e) => setTelefoneAdicional(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="fax" className="block text-sm font-medium text-gray-700">Fax</label>
                <input type="tel" id="fax" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={fax} onChange={(e) => setFax(e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <label htmlFor="emailContato" className="block text-sm font-medium text-gray-700">E-mail</label>
                <input type="email" id="emailContato" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={emailContato} onChange={(e) => setEmailContato(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 📎 Arquivos */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Arquivos</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="fotoPessoal" className="block text-sm font-medium text-gray-700">Foto pessoal (jpeg, jpg, png ou gif)</label>
                <input
                  type="file"
                  id="fotoPessoal"
                  className="mt-1 block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-blue-50 file:text-blue-700
                    hover:file:bg-blue-100"
                  accept="image/jpeg,image/jpg,image/png,image/gif"
                  onChange={(e) => setFotoPessoal(e.target.files[0])}
                />
                {fotoPessoal && <p className="text-xs text-gray-500 mt-1">Arquivo selecionado: {fotoPessoal.name}</p>}
                <p className="text-xs text-red-500 mt-1">
                  (Upload de arquivos requer Firebase Storage e Cloud Functions para segurança e persistência.)
                </p>
              </div>
              <div>
                <label htmlFor="arquivosAdicionais" className="block text-sm font-medium text-gray-700">Arquivos adicionais (jpg, png, jpeg, pdf – até 2MB)</label>
                <input
                  type="file"
                  id="arquivosAdicionais"
                  className="mt-1 block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-blue-50 file:text-blue-700
                    hover:file:bg-blue-100"
                  accept="image/jpeg,image/png,image/jpg,application/pdf"
                  multiple 
                  onChange={(e) => setArquivosAdicionais(Array.from(e.target.files))}
                />
                {arquivosAdicionais.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">Arquivos selecionados: {arquivosAdicionais.map(f => f.name).join(', ')}</p>
                )}
                <p className="text-xs text-red-500 mt-1">
                  (Upload de arquivos requer Firebase Storage e Cloud Functions para segurança e persistência.)
                </p>
              </div>
            </div>
          </div>

          {/* Botões de Ação */}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingStudent && (
              <button
                type="button"
                onClick={resetForm}
                className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded"
              >
                Cancelar Edição
              </button>
            )}
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              {editingStudent ? 'Salvar Alterações' : 'Cadastrar Aluno'}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        {/* Tabela de Alunos Existentes */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Alunos</h3>
        {filteredStudents.length === 0 ? (
          <p className="text-center text-gray-600">Nenhum aluno cadastrado ou encontrado.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome</th>
                  <th className="py-3 px-6 text-left">CPF</th>
                  <th className="py-3 px-6 text-left">Telefone</th>
                  <th className="py-3 px-6 text-left">Email</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {filteredStudents.map((student) => (
                  <tr key={student.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{student.nomeCompleto}</td>
                    <td className="py-3 px-6 text-left">{formatCPF(student.cpf || '')}</td>
                    <td className="py-3 px-6 text-left">{formatTelefone(student.celular || student.telefoneResidencial || '')}</td>
                    <td className="py-3 px-6 text-left">{student.emailContato}</td>
                    <td className="py-3 px-6 text-center">
                      <div className="flex item-center justify-center space-x-2">
                        <button onClick={() => handleEdit(student)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">
                          Editar
                        </button>
                        <button onClick={() => handleDelete(student.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">
                          Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default StudentManagementPage;