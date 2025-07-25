import React, { useState, useEffect } from 'react';
import { db, auth } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc, query, where, orderBy, setDoc, getDoc, limit } from 'firebase/firestore';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';
import { getStorage, ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { matriculaModel } from '../firebase/dataModels';

function MatriculaAlunoPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const storage = getStorage();

  // --- Estados para Busca de Pessoa ---
  const [searchPessoaTerm, setSearchPessoaTerm] = useState('');
  const [pessoaSuggestions, setPessoaSuggestions] = useState([]);
  const [selectedPessoaId, setSelectedPessoaId] = useState(null);
  const [selectedPessoaData, setSelectedPessoaData] = useState(null);

  // --- Estados do Formulário de Matrícula ---
  const [codigoAluno, setCodigoAluno] = useState('');
  const [codigoINEP, setCodigoINEP] = useState('');
  const [codigoSistemaEstadual, setCodigoSistemaEstadual] = useState('');
  const [fotoUpload, setFotoUpload] = useState(null);
  const [fotoURL, setFotoURL] = useState('');
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [situacaoMatricula, setSituacaoMatricula] = useState('ATIVA');

  // --- CAMPOS DE DADOS PESSOAIS (usados para nova pessoa ou para exibir dados de pessoa existente) ---
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

  // --- CAMPOS DE INFORMAÇÕES FAMILIARES (usados para nova pessoa ou para exibir dados de pessoa existente) ---
  const [pessoaPai, setPessoaPai] = useState('');
  const [telefonePai, setTelefonePai] = useState('');
  const [escolaridadePai, setEscolaridadePai] = useState('Nao Informado');
  const [profissaoPai, setProfissaoPai] = useState('');
  const [pessoaMae, setPessoaMae] = useState('');
  const [telefoneMae, setTelefoneMae] = useState('');
  const [escolaridadeMae, setEscolaridadeMae] = useState('Nao Informado');
  const [profissaoMae, setProfissaoMae] = useState('');
  const [responsavelLegalNome, setResponsavelLegalNome] = useState('');
  const [responsavelLegalParentesco, setResponsavelLegalParentesco] = useState('');

  // --- CAMPOS DE DOCUMENTAÇÃO (usados para nova pessoa ou para exibir dados de pessoa existente) ---
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

  // --- CAMPOS DE ENDEREÇO (usados para nova pessoa ou para exibir dados de pessoa existente) ---
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

  // --- CAMPOS DE CONTATO (usados para nova pessoa ou para exibir dados de pessoa existente) ---
  const [telefoneResidencial, setTelefoneResidencial] = useState('');
  const [celular, setCelular] = useState('');
  const [telefoneAdicional, setTelefoneAdicional] = useState('');
  const [emailContato, setEmailContato] = useState('');

  // --- Campos para Pessoas Autorizadas a Buscar o Aluno ---
  const [pessoasAutorizadas, setPessoasAutorizadas] = useState([]);
  const [currentPessoaAutorizadaNome, setCurrentPessoaAutorizadaNome] = useState('');
  const [currentPessoaAutorizadaParentesco, setCurrentPessoaAutorizadaParentesco] = useState('');

  // --- Dados Complementares de Matrícula ---
  const [beneficiosSociais, setBeneficiosSociais] = useState('');
  const [deficienciasTranstornos, setDeficienciasTranstornos] = useState('');
  const [alfabetizado, setAlfabetizado] = useState('sim');
  const [emancipado, setEmancipado] = useState('nao');

  // --- Transporte Escolar ---
  const [utilizaTransporte, setUtilizaTransporte] = useState('nao'); // ESTADO FALTANDO
  const [veiculoTransporte, setVeiculoTransporte] = useState(''); // ESTADO FALTANDO
  const [rotaTransporte, setRotaTransporte] = useState(''); // ESTADO FALTANDO

  // --- Documentação (Uploads) de Matrícula ---
  const [documentosDiversos, setDocumentosDiversos] = useState([]);
  const [laudoMedico, setLaudoMedico] = useState(null);

  // --- Observações da Matrícula ---
  const [observacoes, setObservacoes] = useState('');


  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Opções para Escolaridade (mantidas)
  const escolaridadeOptions = [
    "Não Informado", "Não alfabetizada", "Ensino Fundamental Incompleto",
    "Ensino Fundamental Completo", "Ensino Médio Incompleto", "Ensino Médio Completo",
    "Ensino Superior Incompleto", "Ensino Superior Completo",
  ];

  // Funções de formatação CPF (reutilizadas de PessoaManagementPage)
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

  // Validação de CPF (reutilizada de PessoaManagementPage)
  const validateCPF = (rawCpf) => {
    let cpfCleaned = rawCpf.replace(/\D/g, '');
    if (cpfCleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpfCleaned)) return false;
    let sum = 0;
    let remainder;
    for (let i = 1; i <= 9; i++) { sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i); }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false;
    sum = 0;
    for (let i = 1; i <= 10; i++) { sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i); }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false;
    return true;
  };


  // Limpa o formulário
  const resetForm = () => {
    setSearchPessoaTerm('');
    setPessoaSuggestions([]);
    setSelectedPessoaId(null);
    setSelectedPessoaData(null);

    setCodigoAluno('');
    setCodigoINEP('');
    setCodigoSistemaEstadual('');
    setFotoUpload(null);
    setFotoURL('');
    setAnoLetivo(new Date().getFullYear().toString());
    setSituacaoMatricula('ATIVA');

    setPessoasAutorizadas([]);
    setCurrentPessoaAutorizadaNome('');
    setCurrentPessoaAutorizadaParentesco('');

    setResponsavelLegalNome('');
    setResponsavelLegalParentesco('');

    setReligiao('');
    setBeneficiosSociais('');
    setDeficienciasTranstornos('');
    setAlfabetizado('sim');
    setEmancipado('nao');

    // Limpeza de estados de Transporte Escolar
    setUtilizaTransporte('nao');
    setVeiculoTransporte('');
    setRotaTransporte('');

    setDocumentosDiversos([]);
    setLaudoMedico(null);
    setObservacoes('');

    // Campos de Dados Pessoais (se não houver pessoa selecionada)
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

    // Campos de Informações Familiares
    setPessoaPai('');
    setTelefonePai('');
    setEscolaridadePai('Nao Informado');
    setProfissaoPai('');
    setPessoaMae('');
    setTelefoneMae('');
    setEscolaridadeMae('Nao Informado');
    setProfissaoMae('');

    // Campos de Documentação (apenas os gerenciados aqui, não os de PessoaManagementPage)
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

    // Campos de Endereço (não gerenciados aqui, mas limpos se for nova pessoa)
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

    // Campos de Contato (não gerenciados aqui, mas limpos se for nova pessoa)
    setTelefoneResidencial('');
    setCelular('');
    setTelefoneAdicional('');
    setEmailContato('');

    setErrorMessage('');
    setSuccessMessage('');
  };


  // Efeito para verificar permissões de acesso à página
  useEffect(() => {
    if (!loading) {
      // Apenas Administrador e Secretário podem acessar esta página
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
      }
    }
  }, [loading, userData, navigate]);


  // Efeito para buscar sugestões de Pessoa (por nome ou CPF)
  useEffect(() => {
    if (searchPessoaTerm.length >= 3) {
      const fetchSuggestions = async () => {
        try {
          const searchLower = searchPessoaTerm.toLowerCase();
          const pessoasCol = collection(db, 'pessoas');
          
          // Busca por nomeCompleto
          const qName = query(
            pessoasCol,
            where('nomeCompleto', '>=', searchLower.toUpperCase()),
            where('nomeCompleto', '<=', searchLower.toUpperCase() + '\uf8ff'),
            orderBy('nomeCompleto'),
            limit(10)
          );
          const nameSnapshot = await getDocs(qName);
          let suggestions = nameSnapshot.docs.map(doc => ({
            id: doc.id,
            nomeCompleto: doc.data().nomeCompleto,
            cpf: doc.data().cpf,
          }));

          // Se a busca não for apenas numérica (CPF), também busca por e-mail ou outros campos
          if (isNaN(searchPessoaTerm.replace(/\D/g, ''))) {
              const qEmail = query(
                  pessoasCol,
                  where('emailContato', '>=', searchLower),
                  where('emailContato', '<=', searchLower + '\uf8ff'),
                  orderBy('emailContato'),
                  limit(10)
              );
              const emailSnapshot = await getDocs(qEmail);
              emailSnapshot.docs.forEach(doc => {
                  if (!suggestions.some(s => s.id === doc.id)) {
                      suggestions.push({
                          id: doc.id,
                          nomeCompleto: doc.data().nomeCompleto,
                          emailContato: doc.data().emailContato,
                          cpf: doc.data().cpf,
                      });
                  }
              });
          }

          // Filtra por CPF exato se for numérico
          if (!isNaN(searchPessoaTerm.replace(/\D/g, '')) && searchPessoaTerm.replace(/\D/g, '').length >= 6) {
              const qCpf = query(
                  pessoasCol,
                  where('cpf', '==', searchPessoaTerm.replace(/\D/g, '')),
                  limit(1)
              );
              const cpfSnapshot = await getDocs(qCpf);
              cpfSnapshot.docs.forEach(doc => {
                  if (!suggestions.some(s => s.id === doc.id)) {
                      suggestions.push({
                          id: doc.id,
                          nomeCompleto: doc.data().nomeCompleto,
                          emailContato: doc.data().emailContato,
                          cpf: doc.data().cpf,
                      });
                  }
              });
          }

          suggestions.sort((a, b) => a.nomeCompleto.localeCompare(b.nomeCompleto));

          setPessoaSuggestions(suggestions);
        } catch (error) {
          console.error("Erro ao buscar sugestões de pessoas:", error);
          setPessoaSuggestions([]);
        }
      };
      const handler = setTimeout(() => {
        fetchSuggestions();
      }, 300);
      return () => clearTimeout(handler);
    } else {
      setPessoaSuggestions([]);
    }
  }, [searchPessoaTerm]);

  // Função para selecionar uma pessoa da lista de sugestões
  const handleSelectPessoa = async (pessoa) => {
    setSelectedPessoaId(pessoa.id);
    setSearchPessoaTerm(pessoa.nomeCompleto);
    setPessoaSuggestions([]);

    try {
      const pessoaDocRef = doc(db, 'pessoas', pessoa.id);
      const pessoaDocSnap = await getDoc(pessoaDocRef);
      if (pessoaDocSnap.exists()) {
        const data = pessoaDocSnap.data();
        setSelectedPessoaData(data);

        // Pré-preenche os campos de Dados Pessoais e Informações Familiares
        setCpf(data.cpf || '');
        setNomeCompleto(data.nomeCompleto || '');
        setNomeSocialAfetivo(data.nomeSocialAfetivo || '');
        setSexo(data.sexo || 'Nao Informado');
        setEstadoCivil(data.estadoCivil || 'Solteiro(a)');
        setDataNascimento(data.dataNascimento || '');
        setNacionalidade(data.nacionalidade || '');
        setRaca(data.raca || 'Nao Declarada');
        setPovoIndigena(data.povoIndigena || '');
        setReligiao(data.religiao || '');
        setNaturalidadeCidade(data.naturalidadeCidade || '');
        setNaturalidadeEstado(data.naturalidadeEstado || '');
        setFalecido(data.falecido ? 'sim' : 'nao');

        setPessoaPai(data.pessoaPai || '');
        setTelefonePai(data.telefonePai || '');
        setEscolaridadePai(data.escolaridadePai || 'Nao Informado');
        setProfissaoPai(data.profissaoPai || '');
        setPessoaMae(data.pessoaMae || '');
        setTelefoneMae(data.telefoneMae || '');
        setEscolaridadeMae(data.escolaridadeMae || 'Nao Informado');
        setProfissaoMae(data.profissaoMae || '');
        setResponsavelLegalNome(data.responsavelLegalNome || data.pessoaMae || '');
        setResponsavelLegalParentesco(data.responsavelLegalParentesco || 'Mãe');

        // Contato (se necessário)
        setEmailContato(data.emailContato || '');

        // Preenche campos de endereço com base na pessoa
        setCep(data.cep || '');
        setRua(data.enderecoLogradouro || '');
        setEnderecoNumero(data.enderecoNumero || '');
        setEnderecoComplemento(data.enderecoComplemento || '');
        setEnderecoBairro(data.enderecoBairro || '');
        setMunicipioResidencia(data.municipioResidencia || '');
        setPaisResidencia(data.paisResidencia || 'BRASIL');
        setZonaResidencia(data.zonaResidencia || 'urbana');
        setLocalizacaoDiferenciada(data.localizacaoDiferenciada || '');
        setPontoReferencia(data.pontoReferencia || '');

        // Preenche campos de documentação com base na pessoa
        setRgNumero(data.rgNumero || '');
        setRgDataEmissao(data.rgDataEmissao || '');
        setRgOrgaoEmissor(data.rgOrgaoEmissor || '');
        setRgEstado(data.rgEstado || '');
        setNisPisPasep(data.nisPisPasep || '');
        setCarteiraSUS(data.carteiraSUS || '');
        setCertidaoTipo(data.certidaoTipo || 'Nascimento');
        setCertidaoEstado(data.certidaoEstado || '');
        setCertidaoCartorio(data.certidaoCartorio || '');
        setCertidaoDataEmissao(data.certidaoDataEmissao || '');
        setCertidaoNumero(data.certidaoNumero || '');
        setCertidaoCidade(data.certidaoCidade || '');
        setPassaporteNumero(data.passaporteNumero || '');
        setPassaportePaisEmissor(data.passaportePaisEmissor || '');
        setPassaporteDataEmissao(data.passaporteDataEmissao || '');

        setErrorMessage('');
      }
    } catch (error) {
      console.error("Erro ao buscar dados da pessoa selecionada:", error);
      setErrorMessage("Erro ao carregar dados da pessoa selecionada.");
    }
  };

  // Funções para Pessoas Autorizadas a Buscar
  const handleAddPessoaAutorizada = () => {
    if (!currentPessoaAutorizadaNome || !currentPessoaAutorizadaParentesco) {
      setErrorMessage("Preencha Nome e Parentesco para a pessoa autorizada.");
      return;
    }
    const isDuplicate = pessoasAutorizadas.some(p =>
      p.nome === currentPessoaAutorizadaNome && p.parentesco === currentPessoaAutorizadaParentesco
    );

    if (isDuplicate) {
      setErrorMessage("Esta pessoa já foi adicionada como autorizada.");
      return;
    }

    const newPessoaAutorizada = {
      nome: currentPessoaAutorizadaNome.toUpperCase(),
      parentesco: currentPessoaAutorizadaParentesco.toUpperCase(),
    };

    setPessoasAutorizadas([...pessoasAutorizadas, newPessoaAutorizada]);
    setCurrentPessoaAutorizadaNome('');
    setCurrentPessoaAutorizadaParentesco('');
    setErrorMessage('');
  };

  const handleRemovePessoaAutorizada = (index) => {
    const updated = [...pessoasAutorizadas];
    updated.splice(index, 1);
    setPessoasAutorizadas(updated);
  };

  // Função para upload de foto (PLACEHOLDER REAL, precisa de Cloud Functions para uso seguro em prod)
  const handlePhotoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) { // 2MB
        setErrorMessage("O tamanho da imagem não pode exceder 2MB.");
        return;
    }
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
    if (!allowedTypes.includes(file.type)) {
        setErrorMessage("Formato de imagem não permitido. Use JPEG, JPG, PNG ou GIF.");
        return;
    }

    setFotoUpload(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setFotoURL(reader.result); // Define URL para pré-visualização
    };
    reader.readAsDataURL(file);

    setSuccessMessage("Foto selecionada. O upload ocorrerá ao cadastrar/salvar.");
    setErrorMessage('');
  };


  // Função para lidar com o cadastro/edição de matrícula
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    // Validações básicas da matrícula e pessoa
    // Campos de Pessoa Management para Nova Pessoa
    if (!selectedPessoaId) { // Se não selecionou pessoa existente, valida os campos da pessoa
        if (!nomeCompleto || !cpf || !dataNascimento || !emailContato || !municipioResidencia || !sexo || !estadoCivil || !nacionalidade || !raca || !pessoaMae || !responsavelLegalNome) {
            setErrorMessage('Todos os campos obrigatórios em Dados Pessoais, Informações Familiares e Contato são necessários para cadastrar uma nova pessoa.');
            return;
        }
        if (!validateCPF(cpf.replace(/\D/g, ''))) {
            setErrorMessage('CPF inválido.');
            return;
        }
    }
    
    // Validações específicas da matrícula
    if (!codigoINEP) {
        setErrorMessage('Código INEP é obrigatório para a matrícula.');
        return;
    }
    if (!codigoAluno && !selectedPessoaId) { // Código do aluno apenas para nova matrícula sem pessoa existente
        setErrorMessage('Código do Aluno é obrigatório para nova matrícula sem vinculação a pessoa existente.');
        return;
    }


    let currentPessoaId = selectedPessoaId;
    let finalFotoURL = fotoURL;

    try {
      // 1. UPLOAD DA FOTO (se houver uma nova)
      if (fotoUpload) {
        const fileName = `${currentPessoaId || 'nova_pessoa'}_${Date.now()}_${fotoUpload.name}`;
        const storageRef = ref(storage, `fotos_matriculas/${fileName}`);
        const snapshot = await uploadBytes(storageRef, fotoUpload);
        finalFotoURL = await getDownloadURL(snapshot.ref);
        setFotoURL(finalFotoURL);
        setSuccessMessage("Foto enviada para o Storage.");
      }

      // 2. CADASTRAR/ATUALIZAR PESSOA (se for uma nova pessoa)
      if (!selectedPessoaId) {
        const password = cpf.replace(/\D/g, '').substring(0, 6);
        if (password.length < 6) {
            setErrorMessage('CPF muito curto para gerar senha automática (mínimo 6 dígitos).');
            return;
        }
        const userCredential = await createUserWithEmailAndPassword(auth, emailContato, password);
        const userAuthId = userCredential.user.uid;

        const novaPessoaData = {
            cpf: cpf.replace(/\D/g, ''), nomeCompleto: nomeCompleto.toUpperCase(), nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
            sexo, estadoCivil, dataNascimento, nacionalidade: nacionalidade.toUpperCase(), raca,
            povoIndigena: povoIndigena.toUpperCase(), religiao: religiao.toUpperCase(),
            naturalidadeCidade: naturalidadeCidade.toUpperCase(), naturalidadeEstado: naturalidadeEstado.toUpperCase(),
            falecido: falecido === 'sim', pessoaPai: pessoaPai.toUpperCase(),
            telefonePai: telefonePai.replace(/\D/g, ''), escolaridadePai, profissaoPai: profissaoPai.toUpperCase(),
            pessoaMae: pessoaMae.toUpperCase(),
            telefoneMae: telefoneMae.replace(/\D/g, ''), escolaridadeMae, profissaoMae: profissaoMae.toUpperCase(),
            emailContato,
            rgNumero: rgNumero.replace(/\D/g, ''), rgDataEmissao, rgOrgaoEmissor: rgOrgaoEmissor.toUpperCase(), rgEstado: rgEstado.toUpperCase(),
            nisPisPasep: nisPisPasep.replace(/\D/g, ''), carteiraSUS: carteiraSUS.replace(/\D/g, ''),
            certidaoTipo, certidaoEstado: certidaoEstado.toUpperCase(), certidaoCartorio: certidaoCartorio.toUpperCase(),
            certidaoDataEmissao, certidaoNumero: certidaoNumero.replace(/\D/g, ''), certidaoCidade: certidaoCidade.toUpperCase(),
            passaporteNumero: passaporteNumero.toUpperCase(), passaportePaisEmissor: passaportePaisEmissor.toUpperCase(), passaporteDataEmissao,
            cep: cep.replace(/\D/g, ''), enderecoLogradouro: rua.toUpperCase(), enderecoNumero, enderecoComplemento: enderecoComplemento.toUpperCase(),
            enderecoBairro: enderecoBairro.toUpperCase(), municipioResidencia: municipioResidencia.toUpperCase(), paisResidencia: paisResidencia.toUpperCase(),
            zonaResidencia, localizacaoDiferenciada, pontoReferencia: pontoReferencia.toUpperCase(),
            telefoneResidencial: telefoneResidencial.replace(/\D/g, ''), celular: celular.replace(/\D/g, ''), telefoneAdicional: telefoneAdicional.replace(/\D/g, ''),
            userId: userAuthId,
            dataCadastro: new Date(), ultimaAtualizacao: new Date(),
        };
        const docRef = await addDoc(collection(db, 'pessoas'), novaPessoaData);
        currentPessoaId = docRef.id;

        await setDoc(doc(db, 'users', userAuthId), {
            nomeCompleto: nomeCompleto.toUpperCase(),
            email: emailContato,
            funcao: 'aluno',
            ativo: false,
            permissoes: [],
            criadoEm: new Date(),
            ultimaAtualizacao: new Date(),
            pessoaId: currentPessoaId,
        });
        setSuccessMessage('Pessoa cadastrada e usuário criado automaticamente! Senha: ' + password);

      } else {
        // Se a pessoa já existe e seus dados foram editados através deste formulário
        const pessoaDocRef = doc(db, 'pessoas', currentPessoaId);
        const updatedPessoaData = {
            cpf: cpf.replace(/\D/g, ''), nomeCompleto: nomeCompleto.toUpperCase(), nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
            sexo, estadoCivil, dataNascimento, nacionalidade: nacionalidade.toUpperCase(), raca,
            povoIndigena: povoIndigena.toUpperCase(), religiao: religiao.toUpperCase(),
            naturalidadeCidade: naturalidadeCidade.toUpperCase(), naturalidadeEstado: naturalidadeEstado.toUpperCase(),
            falecido: falecido === 'sim', pessoaPai: pessoaPai.toUpperCase(),
            telefonePai: telefonePai.replace(/\D/g, ''), escolaridadePai, profissaoPai: profissaoPai.toUpperCase(),
            pessoaMae: pessoaMae.toUpperCase(),
            telefoneMae: telefoneMae.replace(/\D/g, ''), escolaridadeMae, profissaoMae: profissaoMae.toUpperCase(),
            emailContato,
            rgNumero: rgNumero.replace(/\D/g, ''), rgDataEmissao, rgOrgaoEmissor: rgOrgaoEmissor.toUpperCase(), rgEstado: rgEstado.toUpperCase(),
            nisPisPasep: nisPisPasep.replace(/\D/g, ''), carteiraSUS: carteiraSUS.replace(/\D/g, ''),
            certidaoTipo, certidaoEstado: certidaoEstado.toUpperCase(), certidaoCartorio: certidaoCartorio.toUpperCase(),
            certidaoDataEmissao, certidaoNumero: certidaoNumero.replace(/\D/g, ''), certidaoCidade: certidaoCidade.toUpperCase(),
            passaporteNumero: passaporteNumero.toUpperCase(), passaportePaisEmissor: passaportePaisEmissor.toUpperCase(), passaporteDataEmissao,
            cep: cep.replace(/\D/g, ''), enderecoLogradouro: rua.toUpperCase(), enderecoNumero, enderecoComplemento: enderecoComplemento.toUpperCase(),
            enderecoBairro: enderecoBairro.toUpperCase(), municipioResidencia: municipioResidencia.toUpperCase(), paisResidencia: paisResidencia.toUpperCase(),
            zonaResidencia, localizacaoDiferenciada, pontoReferencia: pontoReferencia.toUpperCase(),
            telefoneResidencial: telefoneResidencial.replace(/\D/g, ''), celular: celular.replace(/\D/g, ''), telefoneAdicional: telefoneAdicional.replace(/\D/g, ''),
            ultimaAtualizacao: new Date(),
        };
        await updateDoc(pessoaDocRef, updatedPessoaData);
        setSuccessMessage('Dados da pessoa atualizados!');
      }

      // 3. CADASTRAR/ATUALIZAR MATRÍCULA
      const matriculaData = {
        ...matriculaModel,
        pessoaId: currentPessoaId,
        codigoAluno: codigoAluno || `ALU-${Date.now().toString().slice(-6)}`,
        codigoINEP,
        codigoSistemaEstadual,
        fotoURL: finalFotoURL,
        anoLetivo,
        situacaoMatricula,
        pessoasAutorizadasBuscar: pessoasAutorizadas,
        utilizaTransporte: utilizaTransporte === 'sim',
        veiculoTransporte: veiculoTransporte.toUpperCase(),
        rotaTransporte: rotaTransporte.toUpperCase(),
        responsavelLegalNome: responsavelLegalNome.toUpperCase(),
        responsavelLegalParentesco: responsavelLegalParentesco.toUpperCase(),
        religiao: religiao.toUpperCase(),
        beneficiosSociais: beneficiosSociais.toUpperCase(),
        deficienciasTranstornos: deficienciasTranstornos.toUpperCase(),
        alfabetizado: alfabetizado === 'sim',
        emancipado: emancipado === 'sim',
        observacoes: observacoes,
        
        dataMatricula: new Date(),
        ultimaAtualizacao: new Date(),
      };

      await addDoc(collection(db, 'matriculas'), matriculaData);
      setSuccessMessage('Matrícula realizada com sucesso!');
      resetForm();

    } catch (error) {
      console.error("Erro ao realizar matrícula:", error);
      let msg = "Erro ao realizar matrícula: " + error.message;
      if (error.code === 'auth/email-already-in-use') {
        msg = 'O e-mail da pessoa já está em uso para outra conta de usuário.';
      } else if (error.code === 'auth/weak-password') {
        msg = 'Senha automática fraca. CPF da pessoa precisa ter no mínimo 6 dígitos para gerar a senha.';
      }
      setErrorMessage(msg);
    }
  };

  // Verificação de permissão
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
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Matrícula de Aluno</h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Seção 1: Identificação do Aluno */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Identificação do Aluno</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="codigoAluno" className="block text-sm font-medium text-gray-700">Código do Aluno</label>
                <input type="text" id="codigoAluno" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoAluno} onChange={(e) => setCodigoAluno(e.target.value)} placeholder="Gerado automaticamente" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="codigoINEP" className="block text-sm font-medium text-gray-700">Código INEP <span className="text-red-500">*</span></label>
                <input type="text" id="codigoINEP" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoINEP} onChange={(e) => setCodigoINEP(e.target.value)} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="codigoSistemaEstadual" className="block text-sm font-medium text-gray-700">Código do sistema/rede estadual</label>
                <input type="text" id="codigoSistemaEstadual" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoSistemaEstadual} onChange={(e) => setCodigoSistemaEstadual(e.target.value)} autoComplete="off" />
              </div>

              {/* Upload de Foto */}
              <div className="col-span-full md:col-span-2">
                <label htmlFor="fotoUpload" className="block text-sm font-medium text-gray-700">Upload de Foto (máx. 2MB)</label>
                <input
                  type="file"
                  id="fotoUpload"
                  className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                  accept="image/jpeg,image/jpg,image/png,image/gif"
                  onChange={handlePhotoUpload}
                />
                {fotoURL && (
                  <div className="mt-2">
                    <img src={fotoURL} alt="Pré-visualização da Foto" className="max-h-32 max-w-32 object-cover rounded-md" />
                    <p className="text-xs text-gray-500 mt-1">Foto selecionada para upload.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Busca Inicial de Pessoa / Dados Pessoais */}
          <div className="md:col-span-2 border p-4 rounded-lg bg-gray-50 mt-4">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Pessoais</h3>
            {/* Campo de Busca de Pessoa */}
            <div className="relative mb-4">
                <label htmlFor="searchPessoa" className="block text-sm font-medium text-gray-700">
                    Buscar Pessoa Cadastrada (Nome ou CPF)
                    {!selectedPessoaId && <span className="text-red-500 ml-1">*</span>}
                </label>
                <input
                    type="text"
                    id="searchPessoa"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={searchPessoaTerm}
                    onChange={(e) => {
                        setSearchPessoaTerm(e.target.value);
                        setSelectedPessoaId(null);
                        setSelectedPessoaData(null);
                        if (e.target.value.length < 3) setPessoaSuggestions([]);
                    }}
                    placeholder="Digite nome ou CPF (mín. 3 caracteres)"
                    autoComplete="off"
                />
                {searchPessoaTerm.length >= 3 && pessoaSuggestions.length > 0 && (
                    <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
                        {pessoaSuggestions.map(pessoa => (
                            <li
                                key={pessoa.id}
                                className="p-2 cursor-pointer hover:bg-gray-200 flex justify-between items-center"
                                onClick={() => handleSelectPessoa(pessoa)}
                            >
                                <span>{pessoa.nomeCompleto}</span>
                                <span className="text-xs text-gray-500">{pessoa.cpf ? formatCPF(pessoa.cpf) : ''}</span>
                            </li>
                        ))}
                    </ul>
                )}
                {searchPessoaTerm.length >= 3 && pessoaSuggestions.length === 0 && (
                    <p className="text-sm text-gray-500 mt-1">Nenhuma pessoa encontrada. Preencha os campos abaixo para cadastrar uma nova pessoa.</p>
                )}
            </div>

            {/* Campos de Dados Pessoais (Editáveis se Nova Pessoa, Read-only/Pre-filled se Existente) */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="cpfPessoa" className="block text-sm font-medium text-gray-700">CPF <span className="text-red-500">*</span></label>
                <input type="text" id="cpfPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.cpf || cpf} onChange={(e) => setCpf(e.target.value)} maxLength="14" required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-3">
                <label htmlFor="nomeCompletoPessoa" className="block text-sm font-medium text-gray-700">Nome completo <span className="text-red-500">*</span></label>
                <input type="text" id="nomeCompletoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.nomeCompleto || nomeCompleto} onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="nomeSocialAfetivoPessoa" className="block text-sm font-medium text-gray-700">Nome social e/ou afetivo</label>
                <input type="text" id="nomeSocialAfetivoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.nomeSocialAfetivo || nomeSocialAfetivo} onChange={(e) => setNomeSocialAfetivo(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="sexoPessoa" className="block text-sm font-medium text-gray-700">Sexo <span className="text-red-500">*</span></label>
                <select id="sexoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.sexo || sexo} onChange={(e) => setSexo(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off">
                  <option value="Nao Informado">Não Informado</option> <option value="Masculino">Masculino</option> <option value="Feminino">Feminino</option> <option value="Outro">Outro</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="estadoCivilPessoa" className="block text-sm font-medium text-gray-700">Estado civil <span className="text-red-500">*</span></label>
                <select id="estadoCivilPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.estadoCivil || estadoCivil} onChange={(e) => setEstadoCivil(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off">
                  <option value="Solteiro(a)">Solteiro(a)</option> <option value="Casado(a)">Casado(a)</option> <option value="Divorciado(a)">Divorciado(a)</option> <option value="Viúvo(a)">Viúvo(a)</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="dataNascimentoPessoa" className="block text-sm font-medium text-gray-700">Data de nascimento <span className="text-red-500">*</span></label>
                <input type="date" id="dataNascimentoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.dataNascimento || dataNascimento} onChange={(e) => setDataNascimento(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="nacionalidadePessoa" className="block text-sm font-medium text-gray-700">Nacionalidade <span className="text-red-500">*</span></label>
                <input type="text" id="nacionalidadePessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.nacionalidade || nacionalidade} onChange={(e) => setNacionalidade(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="racaPessoa" className="block text-sm font-medium text-gray-700">Raça <span className="text-red-500">*</span></label>
                <select id="racaPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.raca || raca} onChange={(e) => setRaca(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off">
                  <option value="Nao Declarada">Não Declarada</option> <option value="Branca">Branca</option> <option value="Preta">Preta</option> <option value="Parda">Parda</option> <option value="Amarela">Amarela</option> <option value="Indígena">Indígena</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="povoIndigenaPessoa" className="block text-sm font-medium text-gray-700">Povo Indígena</label>
                <input type="text" id="povoIndigenaPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.povoIndigena || povoIndigena} onChange={(e) => setPovoIndigena(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="religiaoPessoa" className="block text-sm font-medium text-gray-700">Religião</label>
                <input type="text" id="religiaoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.religiao || religiao} onChange={(e) => setReligiao(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="naturalidadeCidadePessoa" className="block text-sm font-medium text-gray-700">Naturalidade (Cidade) <span className="text-red-500">*</span></label>
                <input type="text" id="naturalidadeCidadePessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.naturalidadeCidade || naturalidadeCidade} onChange={(e) => setNaturalidadeCidade(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="naturalidadeEstadoPessoa" className="block text-sm font-medium text-gray-700">Naturalidade (Estado) <span className="text-red-500">*</span></label>
                <input type="text" id="naturalidadeEstadoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.naturalidadeEstado || naturalidadeEstado} onChange={(e) => setNaturalidadeEstado(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="falecidoPessoa" className="block text-sm font-medium text-gray-700">Falecido?</label>
                <select id="falecidoPessoa" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.falecido ? 'sim' : 'nao'} onChange={(e) => setFalecido(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off">
                  <option value="nao">Não</option> <option value="sim">Sim</option>
                </select>
              </div>
            </div>
          </div>

          {/* 👨‍👩‍👧‍👦 Informações Familiares */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Informações Familiares</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Seção Mãe */}
              <div className="col-span-full md:col-span-3">
                <label htmlFor="pessoaMae" className="block text-sm font-medium text-gray-700">Pessoa Mãe (Nome Completo) <span className="text-red-500">*</span></label>
                <input type="text" id="pessoaMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.pessoaMae || pessoaMae} onChange={(e) => setPessoaMae(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="telefoneMae" className="block text-sm font-medium text-gray-700">Telefone</label>
                <input type="tel" id="telefoneMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.telefoneMae || formatTelefone(telefoneMae)} onChange={(e) => setTelefoneMae(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="escolaridadeMae" className="block text-sm font-medium text-gray-700">Escolaridade da Mãe</label>
                <select id="escolaridadeMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.escolaridadeMae || escolaridadeMae} onChange={(e) => setEscolaridadeMae(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off">
                  {escolaridadeOptions.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="profissaoMae" className="block text-sm font-medium text-gray-700">Profissão da Mãe</label>
                <input type="text" id="profissaoMae" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.profissaoMae || profissaoMae} onChange={(e) => setProfissaoMae(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>

              {/* Seção Pai */}
              <div className="col-span-full md:col-span-3">
                <label htmlFor="pessoaPai" className="block text-sm font-medium text-gray-700">Pessoa Pai (Nome Completo)</label>
                <input type="text" id="pessoaPai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.pessoaPai || pessoaPai} onChange={(e) => setPessoaPai(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="telefonePai" className="block text-sm font-medium text-gray-700">Telefone</label>
                <input type="tel" id="telefonePai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.telefonePai || formatTelefone(telefonePai)} onChange={(e) => setTelefonePai(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="escolaridadePai" className="block text-sm font-medium text-gray-700">Escolaridade do Pai</label>
                <select id="escolaridadePai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.escolaridadePai || escolaridadePai} onChange={(e) => setEscolaridadePai(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off">
                  {escolaridadeOptions.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="profissaoPai" className="block text-sm font-medium text-gray-700">Profissão do Pai</label>
                <input type="text" id="profissaoPai" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.profissaoPai || profissaoPai} onChange={(e) => setProfissaoPai(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* 🪪 Documentação */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Documentação</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-2">
                <label htmlFor="rgNumero" className="block text-sm font-medium text-gray-700">RG (Número)</label>
                <input type="text" id="rgNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.rgNumero || formatRG(rgNumero)} onChange={(e) => setRgNumero(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="rgDataEmissao" className="block text-sm font-medium text-gray-700">RG (Data de Emissão)</label>
                <input type="date" id="rgDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.rgDataEmissao || rgDataEmissao} onChange={(e) => setRgDataEmissao(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="rgOrgaoEmissor" className="block text-sm font-medium text-gray-700">RG (Órgão Emissor)</label>
                <input type="text" id="rgOrgaoEmissor" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.rgOrgaoEmissor || rgOrgaoEmissor} onChange={(e) => setRgOrgaoEmissor(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="rgEstado" className="block text-sm font-medium text-gray-700">RG (Estado)</label>
                <input type="text" id="rgEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.rgEstado || rgEstado} onChange={(e) => setRgEstado(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="nisPisPasep" className="block text-sm font-medium text-gray-700">NIS (PIS/PASEP)</label>
                <input type="text" id="nisPisPasep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.nisPisPasep || formatNIS(nisPisPasep)} onChange={(e) => setNisPisPasep(e.target.value)} maxLength="11" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="carteiraSUS" className="block text-sm font-medium text-gray-700">Carteira do SUS</label>
                <input type="text" id="carteiraSUS" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.carteiraSUS || formatCarteiraSUS(carteiraSUS)} onChange={(e) => setCarteiraSUS(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              {/* Certidão */}
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="col-span-full md:col-span-1">
                  <label htmlFor="certidaoTipo" className="block text-sm font-medium text-gray-700">Tipo de certidão civil <span className="text-red-500">*</span></label>
                  <select id="certidaoTipo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.certidaoTipo || certidaoTipo} onChange={(e) => setCertidaoTipo(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off">
                    <option value="Nascimento">Nascimento</option> <option value="Casamento">Casamento</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-3">
                  <label htmlFor="certidaoNumero" className="block text-sm font-medium text-gray-700">Certidão (Número)</label>
                  <input type="text" id="certidaoNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.certidaoNumero || certidaoNumero} onChange={(e) => setCertidaoNumero(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="certidaoDataEmissao" className="block text-sm font-medium text-gray-700">Certidão (Data Emissão)</label>
                  <input type="date" id="certidaoDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.certidaoDataEmissao || certidaoDataEmissao} onChange={(e) => setCertidaoDataEmissao(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="certidaoCartorio" className="block text-sm font-medium text-gray-700">Certidão (Cartório)</label>
                  <input type="text" id="certidaoCartorio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.certidaoCartorio || certidaoCartorio} onChange={(e) => setCertidaoCartorio(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="certidaoCidade" className="block text-sm font-medium text-gray-700">Certidão (Cidade)</label>
                  <input type="text" id="certidaoCidade" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.certidaoCidade || certidaoCidade} onChange={(e) => setCertidaoCidade(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="certidaoEstado" className="block text-sm font-medium text-gray-700">Certidão (Estado)</label>
                  <input type="text" id="certidaoEstado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.certidaoEstado || certidaoEstado} onChange={(e) => setCertidaoEstado(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
              </div>

              {/* Passaporte */}
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="passaporteNumero" className="block text-sm font-medium text-gray-700">Passaporte (Número)</label>
                  <input type="text" id="passaporteNumero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.passaporteNumero || passaporteNumero} onChange={(e) => setPassaporteNumero(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label htmlFor="passaporteDataEmissao" className="block text-sm font-medium text-gray-700">Passaporte (Data Emissão)</label>
                  <input type="date" id="passaporteDataEmissao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.passaporteDataEmissao || passaporteDataEmissao} onChange={(e) => setPassaporteDataEmissao(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label htmlFor="passaportePaisEmissor" className="block text-sm font-medium text-gray-700">Passaporte (País Emissor)</label>
                  <input type="text" id="passaportePaisEmissor" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.passaportePaisEmissor || passaportePaisEmissor} onChange={(e) => setPassaportePaisEmissor(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
                </div>
              </div>
            </div>
          </div>

          {/* 🏠 Endereço */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Endereço</h3>
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-4">
                <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
                <input type="text" id="cep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.cep || formatCEP(cep)} onChange={(e) => setCep(e.target.value)} maxLength="9" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
                <input type="text" id="rua" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.enderecoLogradouro || rua} onChange={(e) => setRua(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
                <input type="text" id="numero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.enderecoNumero || enderecoNumero} onChange={(e) => setEnderecoNumero(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
                <input type="text" id="complemento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.enderecoComplemento || enderecoComplemento} onChange={(e) => setEnderecoComplemento(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
                <input type="text" id="bairro" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.enderecoBairro || enderecoBairro} onChange={(e) => setEnderecoBairro(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="municipioResidencia" className="block text-sm font-medium text-gray-700">Município <span className="text-red-500">*</span></label>
                <input type="text" id="municipioResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.municipioResidencia || municipioResidencia} onChange={(e) => setMunicipioResidencia(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="paisResidencia" className="block text-sm font-medium text-gray-700">País <span className="text-red-500">*</span></label>
                <input type="text" id="paisResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.paisResidencia || paisResidencia} onChange={(e) => setPaisResidencia(e.target.value.toUpperCase())} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="zonaResidencia" className="block text-sm font-medium text-gray-700">Zona de residência</label>
                <select id="zonaResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.zonaResidencia || zonaResidencia} onChange={(e) => setZonaResidencia(e.target.value)} disabled={!!selectedPessoaId} autoComplete="off">
                  <option value="urbana">Urbana</option> <option value="rural">Rural</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8">
                <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={selectedPessoaData?.localizacaoDiferenciada || localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                  disabled={!!selectedPessoaId}
                  autoComplete="off"
                >
                  <option value="">Selecione</option> <option value="Não está em área de localização diferenciada">Não está em área de localização diferenciada</option> <option value="Área rural">Área rural</option> <option value="Área indígena">Área indígena</option> <option value="Área de assentamento">Área de assentamento</option> <option value="Área quilombola">Área quilombola</option> <option value="Área ribeirinha">Área ribeirinha</option> <option value="Área de comunidade tradicional">Área de comunidade tradicional</option> <option value="Área de difícil acesso">Área de difícil acesso</option> <option value="Área de fronteira">Área de fronteira</option> <option value="Área urbana periférica">Área urbana periférica</option> <option value="Área de zona de conflito">Área de zona de conflito</option> <option value="Área de vulnerabilidade social">Área de vulnerabilidade social</option>
                </select>
              </div>
              <div className="col-span-full">
                <label htmlFor="pontoReferencia" className="block text-sm font-medium text-gray-700">Ponto de Referência</label>
                <input type="text" id="pontoReferencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.pontoReferencia || pontoReferencia} onChange={(e) => setPontoReferencia(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* 📞 Contato */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Contato</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="telefoneResidencial" className="block text-sm font-medium text-gray-700">Telefone residencial</label>
                <input type="tel" id="telefoneResidencial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.telefoneResidencial || formatTelefone(telefoneResidencial)} onChange={(e) => setTelefoneResidencial(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="celular" className="block text-sm font-medium text-gray-700">Celular</label>
                <input type="tel" id="celular" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.celular || formatTelefone(celular)} onChange={(e) => setCelular(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="telefoneAdicional" className="block text-sm font-medium text-gray-700">Telefone adicional</label>
                <input type="tel" id="telefoneAdicional" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.telefoneAdicional || formatTelefone(telefoneAdicional)} onChange={(e) => setTelefoneAdicional(e.target.value)} maxLength="15" disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="emailContato" className="block text-sm font-medium text-gray-700">E-mail <span className="text-red-500">*</span></label>
                <input type="email" id="emailContato" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={selectedPessoaData?.emailContato || emailContato} onChange={(e) => setEmailContato(e.target.value)} required disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* Seção 3: Pessoas Autorizadas a Buscar o Aluno */}
          <div className="md:col-span-2 border p-4 rounded-lg bg-gray-50 mt-4">
            <h3 className="text-lg font-semibold text-gray-700 mb-4">Pessoas Autorizadas a Buscar o Aluno</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mb-4">
              <div className="col-span-full md:col-span-2">
                <label htmlFor="currentPessoaAutorizadaNome" className="block text-sm font-medium text-gray-700">Nome Autorizado</label>
                <input type="text" id="currentPessoaAutorizadaNome" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={currentPessoaAutorizadaNome} onChange={(e) => setCurrentPessoaAutorizadaNome(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="currentPessoaAutorizadaParentesco" className="block text-sm font-medium text-gray-700">Parentesco</label>
                <input type="text" id="currentPessoaAutorizadaParentesco" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={currentPessoaAutorizadaParentesco} onChange={(e) => setCurrentPessoaAutorizadaParentesco(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full">
                  <button
                      type="button"
                      onClick={handleAddPessoaAutorizada}
                      className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition w-full md:w-auto"
                  >
                      Adicionar Autorizado
                  </button>
              </div>
            </div>
            {pessoasAutorizadas.length > 0 && (
              <div className="mt-4 border-t pt-4">
                <h4 className="text-md font-semibold text-gray-700 mb-2">Pessoas Autorizadas:</h4>
                <ul className="space-y-2">
                  {pessoasAutorizadas.map((pessoa, index) => (
                    <li key={index} className="flex justify-between items-center bg-white p-3 rounded-md shadow-sm border border-gray-200">
                      <span>{pessoa.nome} (<span className="font-medium text-blue-700">{pessoa.parentesco}</span>)</span>
                      <button
                        type="button"
                        onClick={() => handleRemovePessoaAutorizada(index)}
                        className="text-red-500 hover:text-red-700 p-1 rounded-full"
                        title="Remover Autorizado"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Seção 6: Dados Complementares */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Complementares</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="religiaoAluno" className="block text-sm font-medium text-gray-700">Religião</label>
                <input type="text" id="religiaoAluno" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={selectedPessoaData?.religiao || religiao} onChange={(e) => setReligiao(e.target.value.toUpperCase())} disabled={!!selectedPessoaId} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="beneficiosSociais" className="block text-sm font-medium text-gray-700">Benefícios Sociais (Ex: Bolsa Família)</label>
                <input type="text" id="beneficiosSociais" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={beneficiosSociais} onChange={(e) => setBeneficiosSociais(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="deficienciasTranstornos" className="block text-sm font-medium text-gray-700">Deficiências ou Transtornos (Escreva)</label>
                <input type="text" id="deficienciasTranstornos" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={deficienciasTranstornos} onChange={(e) => setDeficienciasTranstornos(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="alfabetizado" className="block text-sm font-medium text-gray-700">Alfabetizado?</label>
                <select id="alfabetizado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={alfabetizado} onChange={(e) => setAlfabetizado(e.target.value)} autoComplete="off">
                  <option value="sim">Sim</option> <option value="nao">Não</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="emancipado" className="block text-sm font-medium text-gray-700">Emancipado?</label>
                <select id="emancipado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={emancipado} onChange={(e) => setEmancipado(e.target.value)} autoComplete="off">
                  <option value="sim">Sim</option> <option value="nao">Não</option>
                </select>
              </div>
            </div>
          </div>

          {/* Seção 5: Transporte Escolar */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Transporte Escolar</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="utilizaTransporte" className="block text-sm font-medium text-gray-700">Utiliza Transporte?</label>
                <select id="utilizaTransporte" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={utilizaTransporte} onChange={(e) => setUtilizaTransporte(e.target.value)} autoComplete="off">
                  <option value="nao">Não</option> <option value="sim">Sim</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="veiculoTransporte" className="block text-sm font-medium text-gray-700">Veículo Utilizado</label>
                <input type="text" id="veiculoTransporte" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={veiculoTransporte} onChange={(e) => setVeiculoTransporte(e.target.value.toUpperCase())} disabled={utilizaTransporte === 'nao'} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="rotaTransporte" className="block text-sm font-medium text-gray-700">Rota</label>
                <input type="text" id="rotaTransporte" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rotaTransporte} onChange={(e) => setRotaTransporte(e.target.value.toUpperCase())} disabled={utilizaTransporte === 'nao'} autoComplete="off" />
              </div>
            </div>
          </div>


          {/* Seção 7: Documentação (Uploads) */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Documentação (Uploads)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="documentosDiversos" className="block text-sm font-medium text-gray-700">Documentos Diversos (jpg, png, pdf, gif)</label>
                <input
                  type="file"
                  id="documentosDiversos"
                  className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                  accept="image/jpeg,image/png,image/jpg,application/pdf,image/gif"
                  multiple
                  onChange={(e) => setDocumentosDiversos(Array.from(e.target.files))}
                />
                {documentosDiversos.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">Arquivos selecionados: {documentosDiversos.map(f => f.name).join(', ')}</p>
                )}
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="laudoMedico" className="block text-sm font-medium text-gray-700">Laudo Médico (jpg, png, pdf, gif)</label>
                <input
                  type="file"
                  id="laudoMedico"
                  className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                  accept="image/jpeg,image/png,image/jpg,application/pdf,image/gif"
                  onChange={(e) => setLaudoMedico(e.target.files[0])}
                />
                {laudoMedico && <p className="text-xs text-gray-500 mt-1">Arquivo selecionado: {laudoMedico.name}</p>}
              </div>
              <p className="col-span-full text-xs text-red-500 mt-1">
                (Upload de arquivos requer Firebase Storage e Cloud Functions para segurança e persistência.)
              </p>
            </div>
          </div>

          {/* Seção 8: Observações do Aluno */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Observações do Aluno</h3>
            <textarea
              id="observacoes"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={observacoes}
              onChange={(e) => setObservacoes(e.target.value)}
              maxLength="255"
              rows="3"
            ></textarea>
            <p className="text-sm text-gray-500 text-right mt-1">
              {observacoes.length} / 255 caracteres
            </p>
          </div>

          {/* Botões de Ação */}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            <button
              type="button"
              onClick={resetForm}
              className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded"
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              Cadastrar Matrícula
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default MatriculaAlunoPage;