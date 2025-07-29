import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { db } from '../firebase/config';
import { doc, getDoc, updateDoc, deleteDoc, collection, query, where, orderBy, getDocs, limit } from 'firebase/firestore';
import { getStorage, ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { FaUserCircle } from 'react-icons/fa';

function EditarAlunoPage() {
    const { alunoId } = useParams();
    const navigate = useNavigate();
    const storage = getStorage();
    
    // Estados do Formulário
    const [loading, setLoading] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    // ======================= INÍCIO DAS ADIÇÕES PARA FOTO =======================
    const [fotoUpload, setFotoUpload] = useState(null);
    const [fotoPreview, setFotoPreview] = useState('');
    const [matriculaPrincipalId, setMatriculaPrincipalId] = useState(null);
    // ======================== FIM DAS ADIÇÕES PARA FOTO =========================

    // Estados dos Dados Pessoais
    const [cpf, setCpf] = useState('');
    const [nomeCompleto, setNomeCompleto] = useState('');
    const [nomeSocialAfetivo, setNomeSocialAfetivo] = useState('');
    const [sexo, setSexo] = useState('');
    const [estadoCivil, setEstadoCivil] = useState('');
    const [dataNascimento, setDataNascimento] = useState('');
    const [nacionalidade, setNacionalidade] = useState('');
    const [raca, setRaca] = useState('');
    const [povoIndigena, setPovoIndigena] = useState('');
    const [religiao, setReligiao] = useState('');
    const [naturalidadeCidade, setNaturalidadeCidade] = useState('');
    const [naturalidadeEstado, setNaturalidadeEstado] = useState('');

    // Estados das Informações Familiares
    const [pessoaPai, setPessoaPai] = useState('');
    const [telefonePai, setTelefonePai] = useState('');
    const [escolaridadePai, setEscolaridadePai] = useState('');
    const [profissaoPai, setProfissaoPai] = useState('');
    const [pessoaMae, setPessoaMae] = useState('');
    const [telefoneMae, setTelefoneMae] = useState('');
    const [escolaridadeMae, setEscolaridadeMae] = useState('');
    const [profissaoMae, setProfissaoMae] = useState('');

    // Estados da Documentação
    const [rgNumero, setRgNumero] = useState('');
    const [rgDataEmissao, setRgDataEmissao] = useState('');
    const [rgOrgaoEmissor, setRgOrgaoEmissor] = useState('');
    const [rgEstado, setRgEstado] = useState('');
    const [nisPisPasep, setNisPisPasep] = useState('');
    const [carteiraSUS, setCarteiraSUS] = useState('');
    const [certidaoTipo, setCertidaoTipo] = useState('');
    const [certidaoNumero, setCertidaoNumero] = useState('');
    
    // Estados do Endereço
    const [cep, setCep] = useState('');
    const [rua, setRua] = useState('');
    const [enderecoNumero, setEnderecoNumero] = useState('');
    const [enderecoComplemento, setEnderecoComplemento] = useState('');
    const [enderecoBairro, setEnderecoBairro] = useState('');
    const [municipioResidencia, setMunicipioResidencia] = useState('');
    const [paisResidencia, setPaisResidencia] = useState('');
    const [zonaResidencia, setZonaResidencia] = useState('');
    
    // Estados dos Contatos
    const [telefoneResidencial, setTelefoneResidencial] = useState('');
    const [celular, setCelular] = useState('');
    const [telefoneAdicional, setTelefoneAdicional] = useState('');
    const [emailContato, setEmailContato] = useState('');

    // Estados do Transporte Escolar
    const [utilizaTransporte, setUtilizaTransporte] = useState(false);
    const [veiculoTransporte, setVeiculoTransporte] = useState('');
    const [rotaTransporte, setRotaTransporte] = useState('');
    
    const escolaridadeOptions = [ "Não Informado", "Não alfabetizada", "Ensino Fundamental Incompleto", "Ensino Fundamental Completo", "Ensino Médio Incompleto", "Ensino Médio Completo", "Ensino Superior Incompleto", "Ensino Superior Completo" ];
    const formatCPF = (value) => value.replace(/\D/g, '').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2').substring(0, 14);
    const formatTelefone = (value) => { if (!value) return ''; value = value.replace(/\D/g, ''); if (value.length > 11) value = value.substring(0, 11); value = value.replace(/^(\d{2})(\d)/g, '($1) $2'); value = value.replace(/(\d)(\d{4})$/, '$1-$2'); return value; };

    const fetchAndSetAlunoData = useCallback(async () => {
        setLoading(true);
        try {
            const docRef = doc(db, 'pessoas', alunoId);
            const docSnap = await getDoc(docRef);
            if (docSnap.exists()) {
                const data = docSnap.data();
                // Preenche todos os estados com os dados do Firestore
                setNomeCompleto(data.nomeCompleto || '');
                setCpf(data.cpf || '');
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
                setPessoaMae(data.pessoaMae || '');
                setTelefoneMae(data.telefoneMae || '');
                setEscolaridadeMae(data.escolaridadeMae || 'Nao Informado');
                setProfissaoMae(data.profissaoMae || '');
                setPessoaPai(data.pessoaPai || '');
                setTelefonePai(data.telefonePai || '');
                setEscolaridadePai(data.escolaridadePai || 'Nao Informado');
                setProfissaoPai(data.profissaoPai || '');
                setRgNumero(data.rgNumero || '');
                setRgDataEmissao(data.rgDataEmissao || '');
                setRgOrgaoEmissor(data.rgOrgaoEmissor || '');
                setRgEstado(data.rgEstado || '');
                setNisPisPasep(data.nisPisPasep || '');
                setCarteiraSUS(data.carteiraSUS || '');
                setCertidaoTipo(data.certidaoTipo || 'Nascimento');
                setCertidaoNumero(data.certidaoNumero || '');
                setCep(data.cep || '');
                setRua(data.enderecoLogradouro || '');
                setEnderecoNumero(data.enderecoNumero || '');
                setEnderecoComplemento(data.enderecoComplemento || '');
                setEnderecoBairro(data.enderecoBairro || '');
                setMunicipioResidencia(data.municipioResidencia || '');
                setPaisResidencia(data.paisResidencia || '');
                setZonaResidencia(data.zonaResidencia || 'urbana');
                setTelefoneResidencial(data.telefoneResidencial || '');
                setCelular(data.celular || '');
                setTelefoneAdicional(data.telefoneAdicional || '');
                setEmailContato(data.emailContato || '');
                setUtilizaTransporte(data.utilizaTransporte || false);
                setVeiculoTransporte(data.veiculoTransporte || '');
                setRotaTransporte(data.rotaTransporte || '');

                // Busca a matrícula mais recente para obter a foto atual
                const matriculasQuery = query(collection(db, 'matriculas'), where('pessoaId', '==', alunoId), orderBy('dataMatricula', 'desc'), limit(1));
                const matriculasSnapshot = await getDocs(matriculasQuery);
                if (!matriculasSnapshot.empty) {
                    const matriculaPrincipal = matriculasSnapshot.docs[0].data();
                    setMatriculaPrincipalId(matriculasSnapshot.docs[0].id);
                    setFotoPreview(matriculaPrincipal.fotoURL || '');
                }
            } else {
                setError('Aluno não encontrado.');
            }
        } catch (err) {
            setError('Falha ao carregar dados do aluno.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [alunoId]);

    useEffect(() => {
        fetchAndSetAlunoData();
    }, [fetchAndSetAlunoData]);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 2 * 1024 * 1024) {
                setError("O arquivo de imagem não pode exceder 2MB.");
                return;
            }
            setFotoUpload(file);
            setFotoPreview(URL.createObjectURL(file));
        }
    };

    const handleGravar = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        setError('');
        setSuccessMessage('');

        const dataToSave = {
            nomeCompleto: nomeCompleto.toUpperCase(),
            cpf: cpf.replace(/\D/g, ''),
            nomeSocialAfetivo: nomeSocialAfetivo.toUpperCase(),
            sexo, estadoCivil, dataNascimento,
            nacionalidade: nacionalidade.toUpperCase(),
            raca, povoIndigena: povoIndigena.toUpperCase(),
            religiao: religiao.toUpperCase(),
            naturalidadeCidade: naturalidadeCidade.toUpperCase(),
            naturalidadeEstado: naturalidadeEstado.toUpperCase(),
            pessoaMae: pessoaMae.toUpperCase(),
            telefoneMae: telefoneMae.replace(/\D/g, ''),
            escolaridadeMae,
            profissaoMae: profissaoMae.toUpperCase(),
            pessoaPai: pessoaPai.toUpperCase(),
            telefonePai: telefonePai.replace(/\D/g, ''),
            escolaridadePai,
            profissaoPai: profissaoPai.toUpperCase(),
            rgNumero: rgNumero.replace(/\D/g, ''),
            rgDataEmissao,
            rgOrgaoEmissor: rgOrgaoEmissor.toUpperCase(),
            rgEstado: rgEstado.toUpperCase(),
            nisPisPasep: nisPisPasep.replace(/\D/g, ''),
            carteiraSUS: carteiraSUS.replace(/\D/g, ''),
            certidaoTipo, certidaoNumero,
            cep: cep.replace(/\D/g, ''),
            enderecoLogradouro: rua.toUpperCase(),
            enderecoNumero,
            enderecoComplemento: enderecoComplemento.toUpperCase(),
            enderecoBairro: enderecoBairro.toUpperCase(),
            municipioResidencia: municipioResidencia.toUpperCase(),
            paisResidencia: paisResidencia.toUpperCase(),
            zonaResidencia,
            telefoneResidencial: telefoneResidencial.replace(/\D/g, ''),
            celular: celular.replace(/\D/g, ''),
            telefoneAdicional: telefoneAdicional.replace(/\D/g, ''),
            emailContato,
            utilizaTransporte,
            veiculoTransporte: veiculoTransporte.toUpperCase(),
            rotaTransporte: rotaTransporte.toUpperCase(),
            ultimaAtualizacao: new Date(),
        };

        try {
            const alunoDocRef = doc(db, 'pessoas', alunoId);
            await updateDoc(alunoDocRef, dataToSave);

            if (fotoUpload) {
                const storageRef = ref(storage, `fotos_alunos/${alunoId}/${fotoUpload.name}`);
                const snapshot = await uploadBytes(storageRef, fotoUpload);
                const finalFotoURL = await getDownloadURL(snapshot.ref);

                if (finalFotoURL && matriculaPrincipalId) {
                    const matriculaDocRef = doc(db, 'matriculas', matriculaPrincipalId);
                    await updateDoc(matriculaDocRef, { fotoURL: finalFotoURL });
                }
            }

            setSuccessMessage('Dados atualizados com sucesso!');
            setTimeout(() => navigate(`/dashboard/escola/aluno/ficha/${alunoId}`), 2000);
        } catch (err) {
            setError('Falha ao gravar as alterações.');
            console.error(err);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleExcluir = async () => { /* ... */ };
    
    if (loading) return <div className="p-6 text-center">Carregando dados para edição...</div>;
    if (error) return <div className="p-6 text-center text-red-600">{error}</div>;

    return (
        <div className="p-6">
            <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
                <h2 className="text-2xl font-bold mb-6 text-gray-800">Editar Dados do Aluno</h2>
                
                {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}
                {error && <p className="text-red-600 text-sm mb-4 text-center">{error}</p>}

                <form onSubmit={handleGravar}>
                    
                    <div className="mb-8 p-4 border rounded-md bg-gray-50">
                        <h3 className="text-lg font-semibold text-gray-700 mb-4">Foto do Aluno</h3>
                        <div className="flex items-center gap-6">
                            {fotoPreview ? (
                                <img src={fotoPreview} alt="Pré-visualização" className="w-24 h-32 object-cover rounded-md border" />
                            ) : (
                                <div className="w-24 h-32 bg-gray-200 rounded-md flex items-center justify-center border">
                                    <FaUserCircle size={50} className="text-gray-400" />
                                </div>
                            )}
                            <div>
                                <label htmlFor="fotoInput" className="block text-sm font-medium text-gray-700">
                                    Alterar Foto (máx. 2MB)
                                </label>
                                <input 
                                    type="file" 
                                    id="fotoInput"
                                    accept="image/png, image/jpeg"
                                    onChange={handleFileChange}
                                    className="mt-1 text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="mb-8">
                        <h3 className="text-lg font-semibold text-gray-700 mb-4 border-b pb-2">Dados Pessoais</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Nome Completo</label>
                                <input type="text" value={nomeCompleto} onChange={(e) => setNomeCompleto(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">CPF</label>
                                <input type="text" value={formatCPF(cpf)} onChange={(e) => setCpf(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Data de Nascimento</label>
                                <input type="date" value={dataNascimento} onChange={(e) => setDataNascimento(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Sexo</label>
                                <select value={sexo} onChange={(e) => setSexo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md">
                                    <option value="Nao Informado">Não Informado</option>
                                    <option value="MASCULINO">Masculino</option>
                                    <option value="FEMININO">Feminino</option>
                                </select>
                            </div>
                            {/* ... e assim por diante para todos os outros campos ... */}
                        </div>
                    </div>

                    <div className="mb-8">
                        <h3 className="text-lg font-semibold text-gray-700 mb-4 border-b pb-2">Informações Familiares</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-4">
                                <h4>Mãe</h4>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Nome da Mãe</label>
                                    <input type="text" value={pessoaMae} onChange={(e) => setPessoaMae(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Telefone da Mãe</label>
                                    <input type="text" value={formatTelefone(telefoneMae)} onChange={(e) => setTelefoneMae(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                                </div>
                            </div>
                            <div className="space-y-4">
                                <h4>Pai</h4>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Nome do Pai</label>
                                    <input type="text" value={pessoaPai} onChange={(e) => setPessoaPai(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Telefone do Pai</label>
                                    <input type="text" value={formatTelefone(telefonePai)} onChange={(e) => setTelefonePai(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    {/* ... O restante das seções e campos do formulário aqui ... */}

                    <div className="flex justify-end space-x-4 mt-8">
                        <button type="button" onClick={() => navigate(`/dashboard/escola/aluno/ficha/${alunoId}`)} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">Cancelar</button>
                        <button type="button" onClick={handleExcluir} disabled={isSubmitting} className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition disabled:bg-red-300">Excluir</button>
                        <button type="submit" disabled={isSubmitting} className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition disabled:bg-green-300">
                            {isSubmitting ? 'Gravando...' : 'Gravar Alterações'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default EditarAlunoPage;