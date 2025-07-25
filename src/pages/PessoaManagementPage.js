import React, { useState, useEffect } from 'react';
import { db, auth } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc, query, where, orderBy, setDoc, getDoc } from 'firebase/firestore';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

function PessoaManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [pessoas, setPessoas] = useState([]);
  const [editingPessoa, setEditingPessoa] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // --- NOVO ESTADO PARA AS SUGESTÕES DE BUSCA ---
  const [personSearchSuggestions, setPersonSearchSuggestions] = useState([]);

  // --- Estados dos Dados Pessoais ---
  const [cpf, setCpf] = useState('');
  const [nomeCompleto, setNomeCompleto] = useState('');
  const [nomeSocialAfetivo, setNomeSocialAfetivo] = useState('');
  const [sexo, setSexo] = useState('Nao Informado');
  const [estadoCivil, setEstadoCivil] = useState('Solteiro(a)');
  const [dataNascimento, setDataNascimento] = useState('');
  const [nacionalidade, setNacionalidade] = useState('');
  const [raca, setRaca] = useState('Nao Declarada');
  const [povoIndigena, setPovoIndigena] = useState('');
  const [religiao, setReligiao] = useState('');
  const [naturalidadeCidade, setNaturalidadeCidade] = useState('');
  const [naturalidadeEstado, setNaturalidadeEstado] = useState('');
  const [falecido, setFalecido] = useState('nao');

  // --- Estados de Informações Familiares (Pessoa Pai/Mãe) ---
  const [pessoaPai, setPessoaPai] = useState('');
  const [telefonePai, setTelefonePai] = useState('');
  const [escolaridadePai, setEscolaridadePai] = useState('Nao Informado');
  const [profissaoPai, setProfissaoPai] = useState('');

  const [pessoaMae, setPessoaMae] = useState('');
  const [telefoneMae, setTelefoneMae] = useState('');
  const [escolaridadeMae, setEscolaridadeMae] = useState('Nao Informado');
  const [profissaoMae, setProfissaoMae] = useState('');

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
  const [certidaoNumero, setCertidaoNumero] = useState('');
  const [certidaoCidade, setCertidaoCidade] = useState('');
  const [passaporteNumero, setPassaporteNumero] = useState('');
  const [passaportePaisEmissor, setPassaportePaisEmissor] = useState('');
  const [passaporteDataEmissao, setPassaporteDataEmissao] = useState('');

  // --- Estados de Endereço ---
  const [cep, setCep] = useState('');
  const [rua, setRua] = useState('');
  const [enderecoNumero, setEnderecoNumero] = useState('');
  const [enderecoComplemento, setEnderecoComplemento] = useState('');
  const [enderecoBairro, setEnderecoBairro] = useState('');
  const [municipioResidencia, setMunicipioResidencia] = useState('');
  const [paisResidencia, setPaisResidencia] = useState('BRASIL');
  const [zonaResidencia, setZonaResidencia] = useState('urbana');
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState('');
  const [pontoReferencia, setPontoReferencia] = useState('');

  // --- Estados de Contato ---
  const [telefoneResidencial, setTelefoneResidencial] = useState('');
  const [celular, setCelular] = useState('');
  const [telefoneAdicional, setTelefoneAdicional] = useState('');
  const [emailContato, setEmailContato] = useState('');

  // Mensagens de feedback
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Opções para Escolaridade
  const escolaridadeOptions = [
    "Não Informado",
    "Não alfabetizada",
    "Ensino Fundamental Incompleto",
    "Ensino Fundamental Completo",
    "Ensino Médio Incompleto",
    "Ensino Médio Completo",
    "Ensino Superior Incompleto",
    "Ensino Superior Completo",
  ];

  // Funções de formatação
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

  // Função de Validação de CPF
  const validateCPF = (rawCpf) => {
    let cpfCleaned = rawCpf.replace(/\D/g, '');
    if (cpfCleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpfCleaned)) return false;
    let sum = 0;
    let remainder;
    for (let i = 1; i <= 9; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false;
    sum = 0;
    for (let i = 1; i <= 10; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i);
    }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false;
    return true;
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
    setPovoIndigena('');
    setReligiao('');
    setNaturalidadeCidade('');
    setNaturalidadeEstado('');
    setFalecido('nao');

    setPessoaPai('');
    setTelefonePai('');
    setEscolaridadePai('Nao Informado');
    setProfissaoPai('');

    setPessoaMae('');
    setTelefoneMae('');
    setEscolaridadeMae('Nao Informado');
    setProfissaoMae('');

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
    setCertidaoNumero('');
    setCertidaoCidade('');
    setPassaporteNumero('');
    setPassaportePaisEmissor('');
    setPassaporteDataEmissao('');

    setCep('');
    setRua('');
    setEnderecoNumero('');
    setEnderecoComplemento('');
    setEnderecoBairro('');
    setMunicipioResidencia('');
    setPaisResidencia('BRASIL');
    setZonaResidencia('urbana');
    setLocalizacaoDiferenciada('');
    setPontoReferencia('');

    setTelefoneResidencial('');
    setCelular('');
    setTelefoneAdicional('');
    setEmailContato('');

    setErrorMessage('');
    setSuccessMessage('');
    setEditingPessoa(null);
  };

  // Filtra pessoas para a busca (da tabela principal)
  const filteredPessoas = pessoas.filter(pessoa =>
    (pessoa.nomeCompleto && pessoa.nomeCompleto.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (pessoa.cpf && pessoa.cpf.includes(searchTerm))
  );

  // Efeito para carregar pessoas existentes (apenas para admins/secretários)
  useEffect(() => {
    if (!loading) {
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }

      const fetchPessoas = async () => {
        try {
          const pessoasCol = collection(db, 'pessoas');
          const pessoaSnapshot = await getDocs(pessoasCol);
          const pessoaList = pessoaSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setPessoas(pessoaList);
        } catch (error) {
          console.error("Erro ao buscar pessoas:", error);
          setErrorMessage("Erro ao carregar lista de pessoas.");
        }
      };
      fetchPessoas();
    }
  }, [loading, userData, navigate]);

  // EFEITO PARA BUSCA COM SUGESTÕES NO CAMPO "Buscar pessoa por nome ou CPF"
  useEffect(() => {
    if (searchTerm.length >= 3) {
      const fetchSearchSuggestions = async () => {
        try {
          const searchLower = searchTerm.toLowerCase();
          const q = query(
            collection(db, 'pessoas'),
            where('nomeCompleto', '>=', searchLower.toUpperCase()),
            where('nomeCompleto', '<=', searchLower.toUpperCase() + '\uf8ff'),
            orderBy('nomeCompleto'),
          );
          const querySnapshot = await getDocs(q);
          const suggestions = querySnapshot.docs.map(doc => ({
            id: doc.id,
            nomeCompleto: doc.data().nomeCompleto,
            cpf: doc.data().cpf,
          }));
          setPersonSearchSuggestions(suggestions);
        } catch (error) {
          console.error("Erro ao buscar sugestões de pessoas:", error);
          setPersonSearchSuggestions([]);
        }
      };
      const handler = setTimeout(() => {
        fetchSearchSuggestions();
      }, 300);
      return () => clearTimeout(handler);
    } else {
      setPersonSearchSuggestions([]);
    }
  }, [searchTerm]);


  // Função para lidar com o cadastro/edição de pessoa
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    // Validações básicas
    if (!nomeCompleto || !cpf || !dataNascimento || !emailContato || !municipioResidencia || !sexo || !estadoCivil || !nacionalidade || !raca || !pessoaMae) {
      setErrorMessage('Nome completo, CPF, Data de Nascimento, E-mail de Contato, Município de Residência, Sexo, Estado Civil, Nacionalidade, Raça e Pessoa Mãe são obrigatórios.');
      return;
    }
    if (!validateCPF(cpf.replace(/\D/g, ''))) {
      setErrorMessage('CPF inválido.');
      return;
    }

    // Objeto com os dados da pessoa
    const pessoaData = {
      // Dados Pessoais
      cpf: cpf.replace(/\D/g, ''),
      nomeCompleto: nomeCompleto.toUpperCase(),
      nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
      sexo,
      estadoCivil,
      dataNascimento,
      nacionalidade: nacionalidade.toUpperCase(),
      raca,
      povoIndigena: povoIndigena.toUpperCase(),
      religiao: religiao.toUpperCase(),
      naturalidadeCidade: naturalidadeCidade.toUpperCase(),
      naturalidadeEstado: naturalidadeEstado.toUpperCase(),
      falecido: falecido === 'sim',

      // Informações Familiares
      pessoaPai: pessoaPai.toUpperCase(),
      telefonePai: telefonePai.replace(/\D/g, ''),
      escolaridadePai,
      profissaoPai: profissaoPai.toUpperCase(),

      pessoaMae: pessoaMae.toUpperCase(),
      telefoneMae: telefoneMae.replace(/\D/g, ''),
      escolaridadeMae,
      profissaoMae: profissaoMae.toUpperCase(),

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
      certidaoNumero: certidaoNumero.replace(/\D/g, ''),
      certidaoCidade: certidaoCidade.toUpperCase(),
      passaporteNumero: passaporteNumero.toUpperCase(),
      passaportePaisEmissor: passaportePaisEmissor.toUpperCase(),
      passaporteDataEmissao,

      // Endereço
      cep: cep.replace(/\D/g, ''),
      enderecoLogradouro: rua.toUpperCase(),
      enderecoNumero,
      enderecoComplemento: enderecoComplemento.toUpperCase(),
      enderecoBairro: enderecoBairro.toUpperCase(),
      municipioResidencia: municipioResidencia.toUpperCase(),
      paisResidencia: paisResidencia.toUpperCase(),
      zonaResidencia,
      localizacaoDiferenciada,
      pontoReferencia: pontoReferencia.toUpperCase(),

      // Contato
      telefoneResidencial: telefoneResidencial.replace(/\D/g, ''),
      celular: celular.replace(/\D/g, ''),
      telefoneAdicional: telefoneAdicional.replace(/\D/g, ''),
      emailContato,

      dataCadastro: new Date(),
      ultimaAtualizacao: new Date(),
    };

    try {
      if (editingPessoa) {
        // MODO EDIÇÃO
        const pessoaDocRef = doc(db, 'pessoas', editingPessoa.id);
        await updateDoc(pessoaDocRef, pessoaData);
        setSuccessMessage('Dados da pessoa atualizados com sucesso!');
        setPessoas(pessoas.map(p => p.id === editingPessoa.id ? { ...p, ...pessoaData } : p));
      } else {
        // MODO CADASTRO
        // 1. Gerar senha automática: 6 primeiros dígitos do CPF (apenas números)
        const password = cpf.replace(/\D/g, '').substring(0, 6);
        if (password.length < 6) {
          setErrorMessage('CPF muito curto para gerar senha automática (mínimo 6 dígitos).');
          return;
        }

        // 2. Criar usuário no Firebase Authentication
        const userCredential = await createUserWithEmailAndPassword(auth, emailContato, password);
        const userAuthId = userCredential.user.uid;

        // 3. Salvar dados da pessoa no Firestore, vinculando ao UID do Auth
        const newPessoaData = {
          ...pessoaData,
          userId: userAuthId, // Adiciona o UID do Firebase Auth ao documento da pessoa
          dataCadastro: new Date(),
          ultimaAtualizacao: new Date(),
        };
        await addDoc(collection(db, 'pessoas'), newPessoaData);

        // 4. Criar um documento inicial na coleção 'users' para o novo usuário criado no Auth
        // com a função 'aluno' e ativo: false para ativação posterior.
        await setDoc(doc(db, 'users', userAuthId), {
          nomeCompleto: nomeCompleto.toUpperCase(),
          email: emailContato,
          funcao: 'aluno', // Padrão para pessoas cadastradas aqui
          ativo: false, // Inativo por padrão, aguardando ativação
          permissoes: [], // Nenhuma permissão de unidade por padrão
          criadoEm: new Date(),
          ultimaAtualizacao: new Date(),
          pessoaId: null, // Pode ser preenchido se a pessoa for vinculada a este userAuthId
        });

        setSuccessMessage('Pessoa cadastrada e usuário criado com sucesso! Senha automática: ' + password);
        // Atualiza a lista de pessoas após o cadastro
        const pessoasCol = collection(db, 'pessoas');
        const pessoaSnapshot = await getDocs(pessoasCol);
        const pessoaList = pessoaSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        setPessoas(pessoaList);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar pessoa ou criar usuário:", error);
      let msg = "Erro ao salvar dados da pessoa: " + error.message;
      if (error.code === 'auth/email-already-in-use') {
        msg = 'Este e-mail já está em uso por outro usuário. Utilize outro e-mail.';
      } else if (error.code === 'auth/weak-password') {
        msg = 'A senha gerada automaticamente é considerada fraca (menos de 6 caracteres). Por favor, verifique o CPF.';
      }
      setErrorMessage(msg);
    }
  };

  // Funções para a tabela: handleEdit
  const handleEdit = (pessoaToEdit) => {
    setEditingPessoa(pessoaToEdit);
    setCpf(pessoaToEdit.cpf || '');
    setNomeCompleto(pessoaToEdit.nomeCompleto || '');
    setNomeSocialAfetivo(pessoaToEdit.nomeSocialAfetivo || '');
    setSexo(pessoaToEdit.sexo || 'Nao Informado');
    setEstadoCivil(pessoaToEdit.estadoCivil || 'Solteiro(a)');
    setDataNascimento(pessoaToEdit.dataNascimento || '');
    setNacionalidade(pessoaToEdit.nacionalidade || '');
    setRaca(pessoaToEdit.raca || 'Nao Declarada');
    setPovoIndigena(pessoaToEdit.povoIndigena || '');
    setReligiao(pessoaToEdit.religiao || '');
    setNaturalidadeCidade(pessoaToEdit.naturalidadeCidade || '');
    setNaturalidadeEstado(pessoaToEdit.naturalidadeEstado || '');
    setFalecido(pessoaToEdit.falecido ? 'sim' : 'nao');

    setPessoaPai(pessoaToEdit.pessoaPai || '');
    setTelefonePai(pessoaToEdit.telefonePai || '');
    setEscolaridadePai(pessoaToEdit.escolaridadePai || 'Nao Informado');
    setProfissaoPai(pessoaToEdit.profissaoPai || '');

    setPessoaMae(pessoaToEdit.pessoaMae || '');
    setTelefoneMae(pessoaToEdit.telefoneMae || '');
    setEscolaridadeMae(pessoaToEdit.escolaridadeMae || 'Nao Informado');
    setProfissaoMae(pessoaToEdit.profissaoMae || '');

    setRgNumero(pessoaToEdit.rgNumero || '');
    setRgDataEmissao(pessoaToEdit.rgDataEmissao || '');
    setRgOrgaoEmissor(pessoaToEdit.rgOrgaoEmissor || '');
    setRgEstado(pessoaToEdit.rgEstado || '');
    setNisPisPasep(pessoaToEdit.nisPisPasep || '');
    setCarteiraSUS(pessoaToEdit.carteiraSUS || '');
    setCertidaoTipo(pessoaToEdit.certidaoTipo || 'Nascimento');
    setCertidaoEstado(pessoaToEdit.certidaoEstado || '');
    setCertidaoCartorio(pessoaToEdit.certidaoCartorio || '');
    setCertidaoDataEmissao(pessoaToEdit.certidaoDataEmissao || '');
    setCertidaoNumero(pessoaToEdit.certidaoNumero || '');
    setCertidaoCidade(pessoaToEdit.certidaoCidade || '');
    setPassaporteNumero(pessoaToEdit.passaporteNumero || '');
    setPassaportePaisEmissor(pessoaToEdit.passaportePaisEmissor || '');
    setPassaporteDataEmissao(pessoaToEdit.passaporteDataEmissao || '');

    setCep(pessoaToEdit.cep || '');
    setRua(pessoaToEdit.enderecoLogradouro || '');
    setEnderecoNumero(pessoaToEdit.enderecoNumero || '');
    setEnderecoComplemento(pessoaToEdit.enderecoComplemento || '');
    setEnderecoBairro(pessoaToEdit.enderecoBairro || '');
    setMunicipioResidencia(pessoaToEdit.municipioResidencia || '');
    setPaisResidencia(pessoaToEdit.paisResidencia || 'BRASIL');
    setZonaResidencia(pessoaToEdit.zonaResidencia || 'urbana');
    setLocalizacaoDiferenciada(pessoaToEdit.localizacaoDiferenciada || '');
    setPontoReferencia(pessoaToEdit.pontoReferencia || '');

    setTelefoneResidencial(pessoaToEdit.telefoneResidencial || '');
    setCelular(pessoaToEdit.celular || '');
    setTelefoneAdicional(pessoaToEdit.telefoneAdicional || '');
    setEmailContato(pessoaToEdit.emailContato || '');

    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleDelete = async (pessoaId) => {
    if (window.confirm('Tem certeza que deseja excluir esta pessoa? Esta ação não pode ser desfeita!')) {
      try {
        // Obter o documento da pessoa para pegar o userId (UID do Auth)
        const pessoaDocRef = doc(db, 'pessoas', pessoaId);
        const pessoaDocSnap = await getDoc(pessoaDocRef);
        let userIdToDelete = null;

        if (pessoaDocSnap.exists()) {
          userIdToDelete = pessoaDocSnap.data().userId;
        }

        // Excluir o documento da pessoa do Firestore
        await deleteDoc(pessoaDocRef);

        // Opcional: Se houver um userId vinculado, você precisará de uma Cloud Function para deletar o usuário do Firebase Auth
        // Ex: const adminDeleteUserCallable = httpsCallable(functions, 'adminDeleteUser');
        // if (userIdToDelete) {
        //   try {
        //     await adminDeleteUserCallable({ uid: userIdToDelete });
        //     console.log('Usuário do Auth deletado com sucesso:', userIdToDelete);
        //   } catch (authError) {
        //     console.warn('Falha ao deletar usuário do Auth (requer Cloud Function):', authError);
        //   }
        // }

        setSuccessMessage('Pessoa excluída com sucesso!');
        setPessoas(pessoas.filter(pessoa => pessoa.id !== pessoaId));
      } catch (error) {
        console.error("Erro ao excluir pessoa:", error);
        setErrorMessage("Erro ao excluir pessoa: " + error.message);
      }
    }
  };

  // Verificação de permissão (apenas admins e secretários podem acessar)
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
    return (
      <div className="flex justify-center items-center h-screen text-red-600 font-bold">
        Acesso Negado: Você não tem permissão para acessar esta página.
      </div>
    );
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-lg mx-auto md:max-w-4xl"> {/* Ajustado max-w para responsividade */}
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingPessoa ? 'Editar Pessoa' : 'Cadastrar Nova Pessoa'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        {/* Campo de Busca com Sugestões */}
        <div className="relative mb-4 max-w-full mx-auto"> {/* Ajustado max-w-full e mx-auto para responsividade */}
          <input
            type="text"
            placeholder="Buscar pessoa por nome ou CPF..."
            className="w-full p-2 border border-gray-300 rounded-md"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
          />
          {searchTerm.length >= 3 && personSearchSuggestions.length > 0 && (
            <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
              {personSearchSuggestions.map(person => (
                <li
                  key={person.id}
                  className="p-2 cursor-pointer hover:bg-gray-200 flex justify-between items-center"
                  onClick={() => {
                    handleEdit(person);
                    setSearchTerm('');
                    setPersonSearchSuggestions([]);
                  }}
                >
                  <span>{person.nomeCompleto}</span>
                  <span className="text-xs text-gray-500">{person.cpf ? formatCPF(person.cpf) : ''}</span>
                </li>
              ))}
            </ul>
          )}
          {searchTerm.length >= 3 && personSearchSuggestions.length === 0 && (
            <p className="text-sm text-gray-500 mt-1">Nenhuma sugestão encontrada.</p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4"> {/* Removido max-w-lg mx-auto daqui */}
          {/* 🧍 Dados Pessoais */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Pessoais</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="cpf" className="block text-sm font-medium text-gray-700">CPF <span className="text-red-500">*</span></label>
                <input type="text" id="cpf" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCPF(cpf)} onChange={(e) => setCpf(e.target.value)} maxLength="14" required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-3"> {/* Adicionado col-span-full */}
                <label htmlFor="nomeCompleto" className="block text-sm font-medium text-gray-700">Nome completo <span className="text-red-500">*</span></label>
                <input type="text" id="nomeCompleto" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeCompleto} onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="nomeSocialAfetivo" className="block text-sm font-medium text-gray-700">Nome social e/ou afetivo</label>
                <input type="text" id="nomeSocialAfetivo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeSocialAfetivo} onChange={(e) => setNomeSocialAfetivo(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="sexo" className="block text-sm font-medium text-gray-700">Sexo <span className="text-red-500">*</span></label>
                <select id="sexo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={sexo} onChange={(e) => setSexo(e.target.value)} required autoComplete="off">
                  <option value="Nao Informado">Não Informado</option>
                  <option value="Masculino">Masculino</option>
                  <option value="Feminino">Feminino</option>
                  <option value="Outro">Outro</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="estadoCivil" className="block text-sm font-medium text-gray-700">Estado civil <span className="text-red-500">*</span></label>
                <select id="estadoCivil" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={estadoCivil} onChange={(e) => setEstadoCivil(e.target.value)} required autoComplete="off">
                  <option value="Solteiro(a)">Solteiro(a)</option>
                  <option value="Casado(a)">Casado(a)</option>
                  <option value="Divorciado(a)">Divorciado(a)</option>
                  <option value="Viúvo(a)">Viúvo(a)</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="dataNascimento" className="block text-sm font-medium text-gray-700">Data de nascimento <span className="text-red-500">*</span></label>
                <input type="date" id="dataNascimento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={dataNascimento} onChange={(e) => setDataNascimento(e.target.value)} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="nacionalidade" className="block text-sm font-medium text-gray-700">Nacionalidade <span className="text-red-500">*</span></label>
                <input type="text" id="nacionalidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nacionalidade} onChange={(e) => setNacionalidade(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="raca" className="block text-sm font-medium text-gray-700">Raça <span className="text-red-500">*</span></label>
                <select id="raca" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={raca} onChange={(e) => setRaca(e.target.value)} required autoComplete="off">
                  <option value="Nao Declarada">Não Declarada</option>
                  <option value="Branca">Branca</option>
                  <option value="Preta">Preta</option>
                  <option value="Parda">Parda</option>
                  <option value="Amarela">Amarela</option>
                  <option value="Indígena">Indígena</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="povoIndigena" className="block text-sm font-medium text-gray-700">Povo Indígena</label>
                <input type="text" id="povoIndigena" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={povoIndigena} onChange={(e) => setPovoIndigena(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="religiao" className="block text-sm font-medium text-gray-700">Religião</label>
                <input type="text" id="religiao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={religiao} onChange={(e) => setReligiao(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="naturalidadeCidade" className="block text-sm font-medium text-gray-700">Naturalidade (Cidade) <span className="text-red-500">*</span></label>
                <input type="text" id="naturalidadeCidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={naturalidadeCidade} onChange={(e) => setNaturalidadeCidade(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="naturalidadeEstado" className="block text-sm font-medium text-gray-700">Naturalidade (Estado) <span className="text-red-500">*</span></label>
                <input type="text" id="naturalidadeEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={naturalidadeEstado} onChange={(e) => setNaturalidadeEstado(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4"> {/* Adicionado col-span-full */}
                <label htmlFor="falecido" className="block text-sm font-medium text-gray-700">Falecido?</label>
                <select id="falecido" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={falecido} onChange={(e) => setFalecido(e.target.value)} autoComplete="off">
                  <option value="nao">Não</option>
                  <option value="sim">Sim</option>
                </select>
              </div>
            </div>
          </div>

          {/* 👨‍👩‍👧‍👦 Informações Familiares */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Informações Familiares</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Seção Mãe */}
              <div className="col-span-full md:col-span-3"> {/* Adicionado col-span-full */}
                <label htmlFor="pessoaMae" className="block text-sm font-medium text-gray-700">Pessoa Mãe (Nome Completo) <span className="text-red-500">*</span></label>
                <input type="text" id="pessoaMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={pessoaMae} onChange={(e) => setPessoaMae(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="telefoneMae" className="block text-sm font-medium text-gray-700">Telefone</label>
                <input type="tel" id="telefoneMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneMae)} onChange={(e) => setTelefoneMae(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="escolaridadeMae" className="block text-sm font-medium text-gray-700">Escolaridade da Mãe</label>
                <select id="escolaridadeMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={escolaridadeMae} onChange={(e) => setEscolaridadeMae(e.target.value)} autoComplete="off">
                  {escolaridadeOptions.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="profissaoMae" className="block text-sm font-medium text-gray-700">Profissão da Mãe</label>
                <input type="text" id="profissaoMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={profissaoMae} onChange={(e) => setProfissaoMae(e.target.value.toUpperCase())} autoComplete="off" />
              </div>

              {/* Seção Pai */}
              <div className="col-span-full md:col-span-3"> {/* Adicionado col-span-full */}
                <label htmlFor="pessoaPai" className="block text-sm font-medium text-gray-700">Pessoa Pai (Nome Completo)</label>
                <input type="text" id="pessoaPai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={pessoaPai} onChange={(e) => setPessoaPai(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="telefonePai" className="block text-sm font-medium text-gray-700">Telefone</label>
                <input type="tel" id="telefonePai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefonePai)} onChange={(e) => setTelefonePai(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="escolaridadePai" className="block text-sm font-medium text-gray-700">Escolaridade do Pai</label>
                <select id="escolaridadePai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={escolaridadePai} onChange={(e) => setEscolaridadePai(e.target.value)} autoComplete="off">
                  {escolaridadeOptions.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="profissaoPai" className="block text-sm font-medium text-gray-700">Profissão do Pai</label>
                <input type="text" id="profissaoPai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={profissaoPai} onChange={(e) => setProfissaoPai(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* 🪪 Documentação */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Documentação</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="rgNumero" className="block text-sm font-medium text-gray-700">RG (Número)</label>
                <input type="text" id="rgNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatRG(rgNumero)} onChange={(e) => setRgNumero(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="rgDataEmissao" className="block text-sm font-medium text-gray-700">RG (Data de Emissão)</label>
                <input type="date" id="rgDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={rgDataEmissao} onChange={(e) => setRgDataEmissao(e.target.value)} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="rgOrgaoEmissor" className="block text-sm font-medium text-gray-700">RG (Órgão Emissor)</label>
                <input type="text" id="rgOrgaoEmissor" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rgOrgaoEmissor} onChange={(e) => setRgOrgaoEmissor(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="rgEstado" className="block text-sm font-medium text-gray-700">RG (Estado)</label>
                <input type="text" id="rgEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rgEstado} onChange={(e) => setRgEstado(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="nisPisPasep" className="block text-sm font-medium text-gray-700">NIS (PIS/PASEP)</label>
                <input type="text" id="nisPisPasep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatNIS(nisPisPasep)} onChange={(e) => setNisPisPasep(e.target.value)} maxLength="11" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="carteiraSUS" className="block text-sm font-medium text-gray-700">Carteira do SUS</label>
                <input type="text" id="carteiraSUS" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCarteiraSUS(carteiraSUS)} onChange={(e) => setCarteiraSUS(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              {/* Certidão */}
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4"> {/* Adicionado col-span-full */}
                <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoTipo" className="block text-sm font-medium text-gray-700">Tipo de certidão civil <span className="text-red-500">*</span></label>
                  <select id="certidaoTipo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={certidaoTipo} onChange={(e) => setCertidaoTipo(e.target.value)} required autoComplete="off">
                    <option value="Nascimento">Nascimento</option>
                    <option value="Casamento">Casamento</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-3"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoNumero" className="block text-sm font-medium text-gray-700">Certidão (Número)</label>
                  <input type="text" id="certidaoNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={certidaoNumero} onChange={(e) => setCertidaoNumero(e.target.value)} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoDataEmissao" className="block text-sm font-medium text-gray-700">Certidão (Data Emissão)</label>
                  <input type="date" id="certidaoDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={certidaoDataEmissao} onChange={(e) => setCertidaoDataEmissao(e.target.value)} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoCartorio" className="block text-sm font-medium text-gray-700">Certidão (Cartório)</label>
                  <input type="text" id="certidaoCartorio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={certidaoCartorio} onChange={(e) => setCertidaoCartorio(e.target.value.toUpperCase())} autoComplete="off" />
                </div>
                {/* Certidão (Cidade) */}
                <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoCidade" className="block text-sm font-medium text-gray-700">Certidão (Cidade)</label>
                  <input type="text" id="certidaoCidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={certidaoCidade} onChange={(e) => setCertidaoCidade(e.target.value.toUpperCase())} autoComplete="off" />
                </div>
                {/* Campo original Certidão (Estado) */}
                <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                  <label htmlFor="certidaoEstado" className="block text-sm font-medium text-gray-700">Certidão (Estado)</label>
                  <input type="text" id="certidaoEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={certidaoEstado} onChange={(e) => setCertidaoEstado(e.target.value.toUpperCase())} autoComplete="off" />
                </div>
              </div>

              {/* Passaporte */}
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4"> {/* Adicionado col-span-full */}
                <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                  <label htmlFor="passaporteNumero" className="block text-sm font-medium text-gray-700">Passaporte (Número)</label>
                  <input type="text" id="passaporteNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={passaporteNumero} onChange={(e) => setPassaporteNumero(e.target.value.toUpperCase())} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                  <label htmlFor="passaporteDataEmissao" className="block text-sm font-medium text-gray-700">Passaporte (Data Emissão)</label>
                  <input type="date" id="passaporteDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={passaporteDataEmissao} onChange={(e) => setPassaporteDataEmissao(e.target.value)} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                  <label htmlFor="passaportePaisEmissor" className="block text-sm font-medium text-gray-700">Passaporte (País Emissor)</label>
                  <input type="text" id="passaportePaisEmissor" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={passaportePaisEmissor} onChange={(e) => setPassaportePaisEmissor(e.target.value.toUpperCase())} autoComplete="off" />
                </div>
              </div>
            </div>
          </div>

          {/* 🏠 Endereço */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Endereço</h3>
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-4"> {/* Adicionado col-span-full */}
                <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
                <input type="text" id="cep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCEP(cep)} onChange={(e) => setCep(e.target.value)} maxLength="9" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4"> {/* Adicionado col-span-full */}
                <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
                <input type="text" id="rua" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rua} onChange={(e) => setRua(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
                <input type="text" id="numero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={enderecoNumero} onChange={(e) => setEnderecoNumero(e.target.value)} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
                <input type="text" id="complemento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={enderecoComplemento} onChange={(e) => setEnderecoComplemento(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4"> {/* Adicionado col-span-full */}
                <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
                <input type="text" id="bairro" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={enderecoBairro} onChange={(e) => setEnderecoBairro(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4"> {/* Adicionado col-span-full */}
                <label htmlFor="municipioResidencia" className="block text-sm font-medium text-gray-700">Município <span className="text-red-500">*</span></label>
                <input type="text" id="municipioResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={municipioResidencia} onChange={(e) => setMunicipioResidencia(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="paisResidencia" className="block text-sm font-medium text-gray-700">País <span className="text-red-500">*</span></label>
                <input type="text" id="paisResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={paisResidencia} onChange={(e) => setPaisResidencia(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2"> {/* Adicionado col-span-full */}
                <label htmlFor="zonaResidencia" className="block text-sm font-medium text-gray-700">Zona de residência</label>
                <select id="zonaResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={zonaResidencia} onChange={(e) => setZonaResidencia(e.target.value)} autoComplete="off">
                  <option value="urbana">Urbana</option>
                  <option value="rural">Rural</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8"> {/* Adicionado col-span-full */}
                <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                  autoComplete="off"
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
              {/* Ponto de Referência */}
              <div className="col-span-full"> {/* Adicionado col-span-full */}
                <label htmlFor="pontoReferencia" className="block text-sm font-medium text-gray-700">Ponto de Referência</label>
                <input type="text" id="pontoReferencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={pontoReferencia} onChange={(e) => setPontoReferencia(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* 📞 Contato */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Contato</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="telefoneResidencial" className="block text-sm font-medium text-gray-700">Telefone residencial</label>
                <input type="tel" id="telefoneResidencial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneResidencial)} onChange={(e) => setTelefoneResidencial(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="celular" className="block text-sm font-medium text-gray-700">Celular</label>
                <input type="tel" id="celular" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(celular)} onChange={(e) => setCelular(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="telefoneAdicional" className="block text-sm font-medium text-gray-700">Telefone adicional</label>
                <input type="tel" id="telefoneAdicional" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneAdicional)} onChange={(e) => setTelefoneAdicional(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              {/* CAMPO E-MAIL MOVIDO E AJUSTADO */}
              <div className="col-span-full md:col-span-1"> {/* Adicionado col-span-full */}
                <label htmlFor="emailContato" className="block text-sm font-medium text-gray-700">E-mail <span className="text-red-500">*</span></label>
                <input type="email" id="emailContato" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={emailContato} onChange={(e) => setEmailContato(e.target.value)} required autoComplete="off" />
              </div>
            </div>
          </div>

          {/* Botões de Ação */}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingPessoa && (
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
              {editingPessoa ? 'Salvar Alterações' : 'Cadastrar Pessoa'}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        {/* Tabela de Pessoas Existentes */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Pessoas</h3>
        {pessoas.length === 0 ? (
          <p className="text-center text-gray-600">Nenhuma pessoa cadastrada ou encontrada.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome</th>
                  <th className="py-3 px-6 text-left">CPF</th>
                  <th className="py-3 px-6 text-left">Celular</th>
                  <th className="py-3 px-6 text-left">Email</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {filteredPessoas.map((pessoa) => (
                  <tr key={pessoa.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{pessoa.nomeCompleto}</td>
                    <td className="py-3 px-6 text-left">{formatCPF(pessoa.cpf || '')}</td>
                    <td className="py-3 px-6 text-left">{formatTelefone(pessoa.celular || pessoa.telefoneResidencial || '')}</td>
                    <td className="py-3 px-6 text-left">{pessoa.emailContato}</td>
                    <td className="py-3 px-6 text-center">
                      <div className="flex item-center justify-center space-x-2">
                        <button onClick={() => handleEdit(pessoa)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">
                          Editar
                        </button>
                        <button onClick={() => handleDelete(pessoa.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">
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

export default PessoaManagementPage;