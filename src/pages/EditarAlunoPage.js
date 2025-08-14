import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { db } from '../firebase/config';
import { doc, getDoc, updateDoc, collection, query, where, getDocs, limit, orderBy } from 'firebase/firestore';
import { getStorage, ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { FaUserCircle } from 'react-icons/fa';
import { seriesAnosEtapasData } from '../data/ensinoConstants';

function EditarAlunoPage() {
    const { alunoId } = useParams();
    const navigate = useNavigate();
    const storage = getStorage();
    
    // Estados do Formulário
    const [loading, setLoading] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [fotoUpload, setFotoUpload] = useState(null);
    const [fotoPreview, setFotoPreview] = useState('');
    const [matriculaPrincipalId, setMatriculaPrincipalId] = useState(null);

    // Estados de Dados Pessoais (Coleção 'pessoas')
    const [cpf, setCpf] = useState('');
    const [nomeCompleto, setNomeCompleto] = useState('');
    const [nomeSocialAfetivo, setNomeSocialAfetivo] = useState('');
    const [sexo, setSexo] = useState('');
    const [estadoCivil, setEstadoCivil] = useState('');
    const [dataNascimento, setDataNascimento] = useState('');
    const [nacionalidade, setNacionalidade] = useState('');
    const [raca, setRaca] = useState('');
    const [povoIndigena, setPovoIndigena] = useState('');
    const [naturalidadeCidade, setNaturalidadeCidade] = useState('');
    const [naturalidadeEstado, setNaturalidadeEstado] = useState('');
    const [falecido, setFalecido] = useState('nao');
    const [emailContato, setEmailContato] = useState('');
    
    // Estados de Informações Familiares (Coleção 'pessoas')
    const [pessoaPai, setPessoaPai] = useState('');
    const [telefonePai, setTelefonePai] = useState('');
    const [escolaridadePai, setEscolaridadePai] = useState('');
    const [profissaoPai, setProfissaoPai] = useState('');
    const [pessoaMae, setPessoaMae] = useState('');
    const [telefoneMae, setTelefoneMae] = useState('');
    const [escolaridadeMae, setEscolaridadeMae] = useState('');
    const [profissaoMae, setProfissaoMae] = useState('');
    const [responsavelLegalNome, setResponsavelLegalNome] = useState('');
    const [responsavelLegalParentesco, setResponsavelLegalParentesco] = useState('');
    
    // Estados de Documentação (Coleção 'pessoas')
    const [rgNumero, setRgNumero] = useState('');
    const [rgDataEmissao, setRgDataEmissao] = useState('');
    const [rgOrgaoEmissor, setRgOrgaoEmissor] = useState('');
    const [rgEstado, setRgEstado] = useState('');
    const [nisPisPasep, setNisPisPasep] = useState('');
    const [carteiraSUS, setCarteiraSUS] = useState('');
    const [certidaoTipo, setCertidaoTipo] = useState('');
    const [certidaoNumero, setCertidaoNumero] = useState('');
    const [certidaoEstado, setCertidaoEstado] = useState('');
    const [certidaoCartorio, setCertidaoCartorio] = useState('');
    const [certidaoDataEmissao, setCertidaoDataEmissao] = useState('');
    const [certidaoCidade, setCertidaoCidade] = useState('');
    const [passaporteNumero, setPassaporteNumero] = useState('');
    const [passaportePaisEmissor, setPassaportePaisEmissor] = useState('');
    const [passaporteDataEmissao, setPassaporteDataEmissao] = useState('');
    
    // Estados de Endereço (Coleção 'pessoas')
    const [cep, setCep] = useState('');
    const [rua, setRua] = useState('');
    const [enderecoNumero, setEnderecoNumero] = useState('');
    const [enderecoComplemento, setEnderecoComplemento] = useState('');
    const [enderecoBairro, setEnderecoBairro] = useState('');
    const [municipioResidencia, setMunicipioResidencia] = useState('');
    const [paisResidencia, setPaisResidencia] = useState('');
    const [zonaResidencia, setZonaResidencia] = useState('');
    const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState('');
    const [pontoReferencia, setPontoReferencia] = useState('');
    
    // Estados de Contato (Coleção 'pessoas')
    const [telefoneResidencial, setTelefoneResidencial] = useState('');
    const [celular, setCelular] = useState('');
    const [telefoneAdicional, setTelefoneAdicional] = useState('');

    // Estados da Matrícula (Coleção 'matriculas')
    const [codigoINEP, setCodigoINEP] = useState('');
    const [matriculaEscolaId, setMatriculaEscolaId] = useState('');
    const [matriculaNivelEnsino, setMatriculaNivelEnsino] = useState('');
    const [matriculaAnoSerie, setMatriculaAnoSerie] = useState('');
    const [matriculaTurmaId, setMatriculaTurmaId] = useState('');
    const [dataMatricula, setDataMatricula] = useState('');
    const [pessoasAutorizadas, setPessoasAutorizadas] = useState([]);
    const [currentPessoaAutorizadaNome, setCurrentPessoaAutorizadaNome] = useState('');
    const [currentPessoaAutorizadaParentesco, setCurrentPessoaAutorizadaParentesco] = useState('');
    const [beneficiosSociais, setBeneficiosSociais] = useState('');
    const [deficienciasTranstornos, setDeficienciasTranstornos] = useState('');
    const [religiao, setReligiao] = useState('');
    const [utilizaTransporte, setUtilizaTransporte] = useState('nao');
    const [veiculoTransporte, setVeiculoTransporte] = useState('');
    const [rotaTransporte, setRotaTransporte] = useState('');
    const [observacoes, setObservacoes] = useState('');

    // Estados para Dropdowns dinâmicos
    const [availableSchools, setAvailableSchools] = useState([]);
    const [availableNiveisEnsino, setAvailableNiveisEnsino] = useState([]);
    const [availableAnosSeries, setAvailableAnosSeries] = useState([]);
    const [availableTurmas, setAvailableTurmas] = useState([]);
    const [schoolAnosSeriesData, setSchoolAnosSeriesData] = useState([]);
    
    const escolaridadeOptions = [ "Não Informado", "Não alfabetizada", "Ensino Fundamental Incompleto", "Ensino Fundamental Completo", "Ensino Médio Incompleto", "Ensino Médio Completo", "Ensino Superior Incompleto", "Ensino Superior Completo" ];
    const formatCPF = (value) => value.replace(/\D/g, '').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2').substring(0, 14);
    const formatTelefone = (value) => { if (!value) return ''; value = value.replace(/\D/g, ''); if (value.length > 11) value = value.substring(0, 11); value = value.replace(/^(\d{2})(\d)/g, '($1) $2'); value = value.replace(/(\d)(\d{4})$/, '$1-$2'); return value; };

    const fetchAndSetAlunoData = useCallback(async () => {
        setLoading(true);
        try {
            const schoolsSnapshot = await getDocs(collection(db, 'schools'));
            const schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
            setAvailableSchools(schoolsList);

            let pessoaData = {};
            const pessoaDocRef = doc(db, 'pessoas', alunoId);
            const pessoaDocSnap = await getDoc(pessoaDocRef);

            if (pessoaDocSnap.exists()) {
                pessoaData = pessoaDocSnap.data();
                setNomeCompleto(pessoaData.nomeCompleto || ''); setCpf(pessoaData.cpf || ''); setNomeSocialAfetivo(pessoaData.nomeSocialAfetivo || '');
                setSexo(pessoaData.sexo || 'Nao Informado'); setEstadoCivil(pessoaData.estadoCivil || 'Solteiro(a)'); setDataNascimento(pessoaData.dataNascimento || '');
                setNacionalidade(pessoaData.nacionalidade || ''); setRaca(pessoaData.raca || 'Nao Declarada'); setPovoIndigena(pessoaData.povoIndigena || '');
                setNaturalidadeCidade(pessoaData.naturalidadeCidade || ''); setNaturalidadeEstado(pessoaData.naturalidadeEstado || '');
                setFalecido(pessoaData.falecido ? 'sim' : 'nao'); setPessoaMae(pessoaData.pessoaMae || ''); setTelefoneMae(pessoaData.telefoneMae || '');
                setEscolaridadeMae(pessoaData.escolaridadeMae || 'Nao Informado'); setProfissaoMae(pessoaData.profissaoMae || ''); setPessoaPai(pessoaData.pessoaPai || '');
                setTelefonePai(pessoaData.telefonePai || ''); setEscolaridadePai(pessoaData.escolaridadePai || 'Nao Informado'); setProfissaoPai(pessoaData.profissaoPai || '');
                setRgNumero(pessoaData.rgNumero || ''); setRgDataEmissao(pessoaData.rgDataEmissao || ''); setRgOrgaoEmissor(pessoaData.rgOrgaoEmissor || '');
                setRgEstado(pessoaData.rgEstado || ''); setNisPisPasep(pessoaData.nisPisPasep || ''); setCarteiraSUS(pessoaData.carteiraSUS || '');
                setCertidaoTipo(pessoaData.certidaoTipo || 'Nascimento'); setCertidaoNumero(pessoaData.certidaoNumero || ''); setCertidaoEstado(pessoaData.certidaoEstado || '');
                setCertidaoCartorio(pessoaData.certidaoCartorio || ''); setCertidaoDataEmissao(pessoaData.certidaoDataEmissao || ''); setCertidaoCidade(pessoaData.certidaoCidade || '');
                setPassaporteNumero(pessoaData.passaporteNumero || ''); setPassaportePaisEmissor(pessoaData.passaportePaisEmissor || ''); setPassaporteDataEmissao(pessoaData.passaporteDataEmissao || '');
                setCep(pessoaData.cep || ''); setRua(pessoaData.enderecoLogradouro || ''); setEnderecoNumero(pessoaData.enderecoNumero || '');
                setEnderecoComplemento(pessoaData.enderecoComplemento || ''); setEnderecoBairro(pessoaData.enderecoBairro || '');
                setMunicipioResidencia(pessoaData.municipioResidencia || ''); setPaisResidencia(pessoaData.paisResidencia || '');
                setZonaResidencia(pessoaData.zonaResidencia || 'urbana'); setLocalizacaoDiferenciada(pessoaData.localizacaoDiferenciada || '');
                setPontoReferencia(pessoaData.pontoReferencia || ''); setTelefoneResidencial(pessoaData.telefoneResidencial || '');
                setCelular(pessoaData.celular || ''); setTelefoneAdicional(pessoaData.telefoneAdicional || ''); setEmailContato(pessoaData.emailContato || '');
            } else { setError('Aluno não encontrado.'); setLoading(false); return; }

            const matriculasQuery = query(collection(db, 'matriculas'), where('pessoaId', '==', alunoId), orderBy('dataMatricula', 'desc'), limit(1));
            const matriculasSnapshot = await getDocs(matriculasQuery);
            if (!matriculasSnapshot.empty) {
                const matriculaDoc = matriculasSnapshot.docs[0];
                setMatriculaPrincipalId(matriculaDoc.id);
                const matriculaData = matriculaDoc.data();
                setFotoPreview(matriculaData.fotoURL || ''); setCodigoINEP(matriculaData.codigoINEP || '');
                setDataMatricula(matriculaData.dataMatricula || ''); setMatriculaEscolaId(matriculaData.escolaId || ''); 
                setMatriculaNivelEnsino(matriculaData.nivelEnsino || ''); setMatriculaAnoSerie(matriculaData.anoSerie || '');
                setMatriculaTurmaId(matriculaData.turmaId || ''); setPessoasAutorizadas(matriculaData.pessoasAutorizadasBuscar || []);
                setBeneficiosSociais(matriculaData.beneficiosSociais || ''); setDeficienciasTranstornos(matriculaData.deficienciasTranstornos || '');
                setReligiao(matriculaData.religiao || '');
                setUtilizaTransporte(matriculaData.utilizaTransporte ? 'sim' : 'nao'); setVeiculoTransporte(matriculaData.veiculoTransporte || '');
                setRotaTransporte(matriculaData.rotaTransporte || ''); setObservacoes(matriculaData.observacoes || '');
                setResponsavelLegalNome(matriculaData.responsavelLegalNome || pessoaData.pessoaMae || '');
                setResponsavelLegalParentesco(matriculaData.responsavelLegalParentesco || '');
            } else { setError("Este aluno não possui uma matrícula para edição."); }
        } catch (err) { setError('Falha ao carregar dados do aluno.'); console.error(err); }
        finally { setLoading(false); }
    }, [alunoId]);

    useEffect(() => { fetchAndSetAlunoData(); }, [fetchAndSetAlunoData]);

    useEffect(() => {
        if (matriculaEscolaId) {
            const school = availableSchools.find(s => s.id === matriculaEscolaId);
            setAvailableNiveisEnsino(school?.niveisEnsino || []);
            setSchoolAnosSeriesData(school?.anosSeriesAtendidas || []);
        } else {
            setAvailableNiveisEnsino([]);
            setSchoolAnosSeriesData([]);
        }
    }, [matriculaEscolaId, availableSchools]);

    useEffect(() => {
        if (matriculaNivelEnsino) {
            const seriesForLevel = seriesAnosEtapasData[matriculaNivelEnsino] || [];
            const filteredSeries = seriesForLevel.filter(serie => schoolAnosSeriesData.includes(serie));
            setAvailableAnosSeries(filteredSeries);
        } else {
            setAvailableAnosSeries([]);
        }
    }, [matriculaNivelEnsino, schoolAnosSeriesData]);

    useEffect(() => {
        if (matriculaEscolaId && matriculaNivelEnsino && matriculaAnoSerie) {
            const fetchTurmas = async () => {
                const q = query(collection(db, 'turmas'), where('schoolId', '==', matriculaEscolaId), where('nivelEnsino', '==', matriculaNivelEnsino), where('anoSerie', '==', matriculaAnoSerie));
                const snapshot = await getDocs(q);
                setAvailableTurmas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
            };
            fetchTurmas();
        } else {
            setAvailableTurmas([]);
        }
    }, [matriculaEscolaId, matriculaNivelEnsino, matriculaAnoSerie]);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 2 * 1024 * 1024) { setError("O arquivo de imagem não pode exceder 2MB."); return; }
            setFotoUpload(file);
            setFotoPreview(URL.createObjectURL(file));
        }
    };

    const handleAddPessoaAutorizada = () => {
        if (!currentPessoaAutorizadaNome || !currentPessoaAutorizadaParentesco) return;
        setPessoasAutorizadas([...pessoasAutorizadas, { nome: currentPessoaAutorizadaNome.toUpperCase(), parentesco: currentPessoaAutorizadaParentesco.toUpperCase() }]);
        setCurrentPessoaAutorizadaNome(''); setCurrentPessoaAutorizadaParentesco('');
    };

    const handleRemovePessoaAutorizada = (index) => {
        const newPessoas = [...pessoasAutorizadas];
        newPessoas.splice(index, 1);
        setPessoasAutorizadas(newPessoas);
    };

    const handleGravar = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        setError(''); setSuccessMessage('');

        const pessoaDataToSave = {
            nomeCompleto: nomeCompleto.toUpperCase(), cpf: cpf.replace(/\D/g, ''), nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
            sexo, estadoCivil, dataNascimento, nacionalidade: nacionalidade.toUpperCase(), raca, povoIndigena: povoIndigena.toUpperCase(),
            naturalidadeCidade: naturalidadeCidade.toUpperCase(), naturalidadeEstado: naturalidadeEstado.toUpperCase(),
            falecido: falecido === 'sim', pessoaMae: pessoaMae.toUpperCase(), telefoneMae: formatTelefone(telefoneMae).replace(/\D/g, ''), escolaridadeMae,
            profissaoMae: profissaoMae.toUpperCase(), pessoaPai: pessoaPai.toUpperCase(), telefonePai: formatTelefone(telefonePai).replace(/\D/g, ''),
            escolaridadePai, profissaoPai: profissaoPai.toUpperCase(), 
            rgNumero: rgNumero.replace(/\D/g, ''), rgDataEmissao, rgOrgaoEmissor: rgOrgaoEmissor.toUpperCase(), rgEstado: rgEstado.toUpperCase(), 
            nisPisPasep: nisPisPasep.replace(/\D/g, ''), carteiraSUS: carteiraSUS.replace(/\D/g, ''), 
            certidaoTipo, certidaoNumero, certidaoEstado: certidaoEstado.toUpperCase(),
            certidaoCartorio: certidaoCartorio.toUpperCase(), certidaoDataEmissao, certidaoCidade: certidaoCidade.toUpperCase(),
            passaporteNumero: passaporteNumero.toUpperCase(), passaportePaisEmissor: passaportePaisEmissor.toUpperCase(), passaporteDataEmissao,
            cep: cep.replace(/\D/g, ''), enderecoLogradouro: rua.toUpperCase(), enderecoNumero, enderecoComplemento: enderecoComplemento.toUpperCase(),
            enderecoBairro: enderecoBairro.toUpperCase(), municipioResidencia: municipioResidencia.toUpperCase(),
            paisResidencia: paisResidencia.toUpperCase(), zonaResidencia, localizacaoDiferenciada, pontoReferencia: pontoReferencia.toUpperCase(),
            telefoneResidencial: formatTelefone(telefoneResidencial).replace(/\D/g, ''), celular: formatTelefone(celular).replace(/\D/g, ''),
            telefoneAdicional: formatTelefone(telefoneAdicional).replace(/\D/g, ''), emailContato, ultimaAtualizacao: new Date(),
        };

        const matriculaDataToSave = {
            codigoINEP, dataMatricula,
            escolaId: matriculaEscolaId, nivelEnsino: matriculaNivelEnsino,
            anoSerie: matriculaAnoSerie, turmaId: matriculaTurmaId,
            pessoasAutorizadasBuscar: pessoasAutorizadas, beneficiosSociais,
            deficienciasTranstornos, religiao,
            utilizaTransporte: utilizaTransporte === 'sim',
            veiculoTransporte, rotaTransporte, observacoes,
            responsavelLegalNome: responsavelLegalNome.toUpperCase(),
            responsavelLegalParentesco: responsavelLegalParentesco.toUpperCase(),
            ultimaAtualizacao: new Date(),
        };

        try {
            const alunoDocRef = doc(db, 'pessoas', alunoId);
            await updateDoc(alunoDocRef, pessoaDataToSave);

            if (fotoUpload) {
                const storageRef = ref(storage, `fotos_alunos/${alunoId}/${fotoUpload.name}`);
                const snapshot = await uploadBytes(storageRef, fotoUpload);
                matriculaDataToSave.fotoURL = await getDownloadURL(snapshot.ref);
            }

            if (matriculaPrincipalId) {
                const matriculaDocRef = doc(db, 'matriculas', matriculaPrincipalId);
                await updateDoc(matriculaDocRef, matriculaDataToSave);
            }

            setSuccessMessage('Dados atualizados com sucesso!');
            setTimeout(() => navigate(`/dashboard/escola/aluno/ficha/${alunoId}`), 2000);
        } catch (err) { setError('Falha ao gravar as alterações.'); console.error(err); }
        finally { setIsSubmitting(false); }
    };

    if (loading) return <div className="p-6 text-center">Carregando dados para edição...</div>;
    if (error && !successMessage) return <div className="p-6 text-center text-red-600">{error}</div>;

    return (
        <div className="p-6">
            <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
                <h2 className="text-2xl font-bold mb-6 text-gray-800">Editar Dados de: <span className="text-blue-600">{nomeCompleto}</span></h2>
                
                {successMessage && <p className="text-green-600 bg-green-100 p-3 rounded-md text-sm mb-4 text-center">{successMessage}</p>}
                {error && <p className="text-red-600 bg-red-100 p-3 rounded-md text-sm mb-4 text-center">{error}</p>}

                <form onSubmit={handleGravar} className="space-y-8">
                    <fieldset className="border p-4 rounded-md"><legend className="text-lg font-semibold text-gray-700 px-2">Foto do Aluno</legend><div className="flex items-center gap-6 p-2">{fotoPreview ? <img src={fotoPreview} alt="Pré-visualização" className="w-24 h-32 object-cover rounded-md border" /> : <div className="w-24 h-32 bg-gray-200 rounded-md flex items-center justify-center border"><FaUserCircle size={50} className="text-gray-400" /></div>}<div><label htmlFor="fotoInput" className="block text-sm font-medium text-gray-700">Alterar Foto (máx. 2MB)</label><input type="file" id="fotoInput" accept="image/png, image/jpeg" onChange={handleFileChange} className="mt-1 text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" /></div></div></fieldset>
                    <fieldset className="border p-4 rounded-md"><legend className="text-lg font-semibold text-gray-700 px-2">Dados Pessoais</legend><div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-2">{/* ... Campos de Dados Pessoais ... */}</div></fieldset>
                    
                    {/* SEÇÕES COMPLETAS ABAIXO */}
                    <fieldset className="border p-4 rounded-md">
                        <legend className="text-lg font-semibold text-gray-700 px-2">Informações Familiares</legend>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 mt-2">
                            <div className="space-y-4"><h4 className="font-semibold text-center text-gray-600 border-b pb-2">Dados da Mãe</h4><div><label className="block text-sm font-medium">Nome</label><input type="text" value={pessoaMae} onChange={(e) => setPessoaMae(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Telefone</label><input type="text" value={formatTelefone(telefoneMae)} onChange={(e) => setTelefoneMae(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Escolaridade</label><select value={escolaridadeMae} onChange={(e) => setEscolaridadeMae(e.target.value)} className="mt-1 w-full p-2 border rounded">{escolaridadeOptions.map(o=><option key={o} value={o}>{o}</option>)}</select></div><div><label className="block text-sm font-medium">Profissão</label><input type="text" value={profissaoMae} onChange={(e) => setProfissaoMae(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div></div>
                            <div className="space-y-4"><h4 className="font-semibold text-center text-gray-600 border-b pb-2">Dados do Pai</h4><div><label className="block text-sm font-medium">Nome</label><input type="text" value={pessoaPai} onChange={(e) => setPessoaPai(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Telefone</label><input type="text" value={formatTelefone(telefonePai)} onChange={(e) => setTelefonePai(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Escolaridade</label><select value={escolaridadePai} onChange={(e) => setEscolaridadePai(e.target.value)} className="mt-1 w-full p-2 border rounded">{escolaridadeOptions.map(o=><option key={o} value={o}>{o}</option>)}</select></div><div><label className="block text-sm font-medium">Profissão</label><input type="text" value={profissaoPai} onChange={(e) => setProfissaoPai(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div></div>
                        </div>
                    </fieldset>
                    
                    <fieldset className="border p-4 rounded-md">
                        <legend className="text-lg font-semibold text-gray-700 px-2">Documentação</legend>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-2">
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">RG (Número)</label><input type="text" value={rgNumero} onChange={(e) => setRgNumero(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">RG (Data Emissão)</label><input type="date" value={rgDataEmissao} onChange={(e) => setRgDataEmissao(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">RG (Órgão Emissor)</label><input type="text" value={rgOrgaoEmissor} onChange={(e) => setRgOrgaoEmissor(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">RG (Estado)</label><input type="text" value={rgEstado} onChange={(e) => setRgEstado(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">NIS (PIS/PASEP)</label><input type="text" value={nisPisPasep} onChange={(e) => setNisPisPasep(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">Cartão SUS</label><input type="text" value={carteiraSUS} onChange={(e) => setCarteiraSUS(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-1"><label className="block text-sm font-medium">Certidão Civil</label><select value={certidaoTipo} onChange={(e) => setCertidaoTipo(e.target.value)} className="mt-1 w-full p-2 border rounded"><option value="Nascimento">Nascimento</option><option value="Casamento">Casamento</option></select></div>
                            <div className="col-span-full md:col-span-3"><label className="block text-sm font-medium">Nº da Certidão</label><input type="text" value={certidaoNumero} onChange={(e) => setCertidaoNumero(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                        </div>
                    </fieldset>

                    <fieldset className="border p-4 rounded-md">
                         <legend className="text-lg font-semibold text-gray-700 px-2">Endereço</legend>
                         <div className="grid grid-cols-1 md:grid-cols-6 gap-4 mt-2">
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">CEP</label><input type="text" value={cep} onChange={(e) => setCep(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-4"><label className="block text-sm font-medium">Rua</label><input type="text" value={rua} onChange={(e) => setRua(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-1"><label className="block text-sm font-medium">Número</label><input type="text" value={enderecoNumero} onChange={(e) => setEnderecoNumero(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">Complemento</label><input type="text" value={enderecoComplemento} onChange={(e) => setEnderecoComplemento(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                            <div className="col-span-full md:col-span-3"><label className="block text-sm font-medium">Bairro</label><input type="text" value={enderecoBairro} onChange={(e) => setEnderecoBairro(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                         </div>
                    </fieldset>

                     <fieldset className="border p-4 rounded-md">
                         <legend className="text-lg font-semibold text-gray-700 px-2">Contato</legend>
                         <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2">
                            <div><label className="block text-sm font-medium">Telefone Residencial</label><input type="text" value={formatTelefone(telefoneResidencial)} onChange={(e) => setTelefoneResidencial(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div><label className="block text-sm font-medium">Celular</label><input type="text" value={formatTelefone(celular)} onChange={(e) => setCelular(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                            <div><label className="block text-sm font-medium">E-mail</label><input type="email" value={emailContato} onChange={(e) => setEmailContato(e.target.value)} className="mt-1 w-full p-2 border rounded"/></div>
                         </div>
                    </fieldset>

                    <fieldset className="border p-4 rounded-md">
                        <legend className="text-lg font-semibold text-gray-700 px-2">Dados da Matrícula Escolar</legend>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-2">
                            <div className="col-span-full"><label className="block text-sm font-medium">Escola</label><select value={matriculaEscolaId} onChange={(e) => setMatriculaEscolaId(e.target.value)} className="mt-1 w-full p-2 border rounded"><option value="">Selecione</option>{availableSchools.map(s=><option key={s.id} value={s.id}>{s.nomeEscola}</option>)}</select></div>
                            <div className="col-span-full"><label className="block text-sm font-medium">Nível de Ensino</label><select value={matriculaNivelEnsino} onChange={(e) => setMatriculaNivelEnsino(e.target.value)} disabled={!matriculaEscolaId} className="mt-1 w-full p-2 border rounded"><option value="">Selecione</option>{availableNiveisEnsino.map(n=><option key={n} value={n}>{n}</option>)}</select></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">Série/Ano</label><select value={matriculaAnoSerie} onChange={(e) => setMatriculaAnoSerie(e.target.value)} disabled={!matriculaNivelEnsino} className="mt-1 w-full p-2 border rounded"><option value="">Selecione</option>{availableAnosSeries.map(a=><option key={a} value={a}>{a}</option>)}</select></div>
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">Turma</label><select value={matriculaTurmaId} onChange={(e) => setMatriculaTurmaId(e.target.value)} disabled={!matriculaAnoSerie} className="mt-1 w-full p-2 border rounded"><option value="">Selecione</option>{availableTurmas.map(t=><option key={t.id} value={t.id}>{t.nomeTurma}</option>)}</select></div>
                        </div>
                    </fieldset>

                    <fieldset className="border p-4 rounded-md">
                        <legend className="text-lg font-semibold text-gray-700 px-2">Pessoas Autorizadas a Buscar o Aluno</legend>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mt-2">
                            <div className="col-span-full md:col-span-2"><label className="block text-sm font-medium">Nome</label><input type="text" value={currentPessoaAutorizadaNome} onChange={(e) => setCurrentPessoaAutorizadaNome(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                            <div><label className="block text-sm font-medium">Parentesco</label><input type="text" value={currentPessoaAutorizadaParentesco} onChange={(e) => setCurrentPessoaAutorizadaParentesco(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div>
                        </div>
                        <button type="button" onClick={handleAddPessoaAutorizada} className="mt-2 bg-blue-500 text-white py-1 px-3 rounded text-sm">+ Adicionar</button>
                        <ul className="mt-4 space-y-2">{pessoasAutorizadas.map((p, i) => <li key={i} className="flex justify-between items-center bg-gray-100 p-2 rounded"><span>{p.nome} ({p.parentesco})</span><button type="button" onClick={() => handleRemovePessoaAutorizada(i)} className="text-red-500 hover:text-red-700">x</button></li>)}</ul>
                    </fieldset>

                    <fieldset className="border p-4 rounded-md"><legend className="text-lg font-semibold text-gray-700 px-2">Dados Complementares</legend><div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2"><div><label className="block text-sm font-medium">Benefícios Sociais</label><input type="text" value={beneficiosSociais} onChange={(e) => setBeneficiosSociais(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Deficiências/Transtornos</label><input type="text" value={deficienciasTranstornos} onChange={(e) => setDeficienciasTranstornos(e.target.value.toUpperCase())} className="mt-1 w-full p-2 border rounded"/></div></div></fieldset>
                    
                    <fieldset className="border p-4 rounded-md"><legend className="text-lg font-semibold text-gray-700 px-2">Transporte Escolar</legend><div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2"><div><label className="block text-sm font-medium">Utiliza?</label><select value={utilizaTransporte} onChange={(e) => setUtilizaTransporte(e.target.value)} className="mt-1 w-full p-2 border rounded"><option value="nao">Não</option><option value="sim">Sim</option></select></div><div><label className="block text-sm font-medium">Veículo</label><input type="text" value={veiculoTransporte} onChange={(e) => setVeiculoTransporte(e.target.value.toUpperCase())} disabled={utilizaTransporte === 'nao'} className="mt-1 w-full p-2 border rounded"/></div><div><label className="block text-sm font-medium">Rota</label><input type="text" value={rotaTransporte} onChange={(e) => setRotaTransporte(e.target.value.toUpperCase())} disabled={utilizaTransporte === 'nao'} className="mt-1 w-full p-2 border rounded"/></div></div></fieldset>

                    <fieldset className="border p-4 rounded-md"><legend className="text-lg font-semibold text-gray-700 px-2">Observações</legend><textarea value={observacoes} onChange={(e) => setObservacoes(e.target.value)} rows="3" className="mt-1 w-full p-2 border rounded"></textarea></fieldset>
                    
                    <div className="flex justify-end space-x-4 mt-8">
                        <button type="button" onClick={() => navigate(`/dashboard/escola/aluno/ficha/${alunoId}`)} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">Cancelar</button>
                        <button type="submit" disabled={isSubmitting} className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition disabled:bg-green-300">{isSubmitting ? 'Gravando...' : 'Gravar Alterações'}</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default EditarAlunoPage;