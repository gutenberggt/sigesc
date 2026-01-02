import { useState } from 'react';
import { FileText, ExternalLink, X, GraduationCap, ClipboardCheck, Calendar, User, Award } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { documentsAPI, getToken } from '@/services/api';

/**
 * Modal para geração de documentos PDF do aluno
 * - Boletim Escolar
 * - Ficha Individual
 * - Declaração de Matrícula
 * - Declaração de Frequência
 * - Certificado (apenas 9º Ano e EJA 4ª Etapa)
 * 
 * Os PDFs abrem em nova aba do navegador para visualização.
 * O usuário pode salvar ou imprimir diretamente do visualizador.
 */
export const DocumentGeneratorModal = ({ 
  isOpen, 
  onClose, 
  student,
  academicYear = '2025',
  classInfo = null  // Informações da turma para verificar elegibilidade do certificado
}) => {
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);

  // Verifica se a turma é elegível para certificado (9º Ano ou EJA 4ª Etapa)
  const isEligibleForCertificate = (() => {
    if (!classInfo) return false;
    const gradeLevel = (classInfo.grade_level || '').toLowerCase();
    const educationLevel = (classInfo.education_level || '').toLowerCase();
    
    const is9ano = gradeLevel.includes('9') && gradeLevel.includes('ano');
    const isEja4etapa = (educationLevel.includes('eja') || gradeLevel.includes('eja')) && 
                        (gradeLevel.includes('4') || gradeLevel.includes('etapa'));
    
    return is9ano || isEja4etapa;
  })();

  const handleOpenPdf = async (type) => {
    if (!student?.id) {
      setError('Aluno não selecionado');
      return;
    }

    setLoading(type);
    setError(null);

    try {
      let url;

      switch (type) {
        case 'boletim':
          url = documentsAPI.getBoletimUrl(student.id, academicYear);
          break;
        case 'ficha':
          url = documentsAPI.getFichaIndividualUrl(student.id, academicYear);
          break;
        case 'matricula':
          url = documentsAPI.getDeclaracaoMatriculaUrl(student.id, academicYear);
          break;
        case 'frequencia':
          url = documentsAPI.getDeclaracaoFrequenciaUrl(student.id, academicYear);
          break;
        case 'certificado':
          url = documentsAPI.getCertificadoUrl(student.id, academicYear);
          break;
        default:
          throw new Error('Tipo de documento inválido');
      }

      // Obter o token de autenticação
      const token = getToken();
      
      // Buscar o PDF como blob para criar uma URL temporária
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Erro ao gerar documento');
      }
      
      const blob = await response.blob();
      
      // Criar URL temporária do blob e abrir em nova aba
      const blobUrl = window.URL.createObjectURL(blob);
      const newWindow = window.open(blobUrl, '_blank');
      
      // Limpar a URL do blob quando a janela for fechada
      // O navegador libera o recurso automaticamente ao fechar a aba
      if (newWindow) {
        newWindow.onbeforeunload = () => {
          window.URL.revokeObjectURL(blobUrl);
        };
      }

    } catch (err) {
      console.error('Erro ao gerar documento:', err);
      setError(err.message || 'Erro ao gerar documento. Verifique se o aluno possui matrícula ativa.');
    } finally {
      setLoading(null);
    }
  };

  const documents = [
    {
      id: 'boletim',
      title: 'Boletim Escolar',
      description: 'Notas e médias do aluno por disciplina',
      icon: GraduationCap,
      color: 'blue'
    },
    {
      id: 'ficha',
      title: 'Ficha Individual',
      description: 'Notas, frequência e dados completos do aluno',
      icon: User,
      color: 'orange'
    },
    {
      id: 'matricula',
      title: 'Declaração de Matrícula',
      description: 'Comprova que o aluno está matriculado',
      icon: ClipboardCheck,
      color: 'green'
    },
    {
      id: 'frequencia',
      title: 'Declaração de Frequência',
      description: 'Percentual de frequência do aluno',
      icon: Calendar,
      color: 'purple'
    },
    // Certificado só aparece se a turma for elegível (9º Ano ou EJA 4ª Etapa)
    ...(isEligibleForCertificate ? [{
      id: 'certificado',
      title: 'Certificado de Conclusão',
      description: 'Certificado de conclusão do Ensino Fundamental',
      icon: Award,
      color: 'indigo'
    }] : [])
  ];

  const colorClasses = {
    blue: {
      bg: 'bg-blue-50 hover:bg-blue-100',
      border: 'border-blue-200 hover:border-blue-400',
      icon: 'text-blue-600',
      button: 'bg-blue-600 hover:bg-blue-700'
    },
    orange: {
      bg: 'bg-orange-50 hover:bg-orange-100',
      border: 'border-orange-200 hover:border-orange-400',
      icon: 'text-orange-600',
      button: 'bg-orange-600 hover:bg-orange-700'
    },
    green: {
      bg: 'bg-green-50 hover:bg-green-100',
      border: 'border-green-200 hover:border-green-400',
      icon: 'text-green-600',
      button: 'bg-green-600 hover:bg-green-700'
    },
    purple: {
      bg: 'bg-purple-50 hover:bg-purple-100',
      border: 'border-purple-200 hover:border-purple-400',
      icon: 'text-purple-600',
      button: 'bg-purple-600 hover:bg-purple-700'
    },
    indigo: {
      bg: 'bg-indigo-50 hover:bg-indigo-100',
      border: 'border-indigo-200 hover:border-indigo-400',
      icon: 'text-indigo-600',
      button: 'bg-indigo-600 hover:bg-indigo-700'
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Gerar Documentos"
      size="md"
    >
      <div className="space-y-4">
        {/* Info do Aluno */}
        {student && (
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <span className="text-blue-600 font-semibold">
                  {student.full_name?.charAt(0)?.toUpperCase()}
                </span>
              </div>
              <div>
                <p className="font-medium text-gray-900">{student.full_name}</p>
                <p className="text-sm text-gray-500">Ano Letivo: {academicYear}</p>
              </div>
            </div>
          </div>
        )}

        {/* Erro */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Lista de Documentos */}
        <div className="space-y-3">
          {documents.map((doc) => {
            const Icon = doc.icon;
            const colors = colorClasses[doc.color];
            const isLoading = loading === doc.id;

            return (
              <div
                key={doc.id}
                className={`border rounded-lg p-4 transition-all ${colors.bg} ${colors.border}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg bg-white ${colors.icon}`}>
                      <Icon size={24} />
                    </div>
                    <div>
                      <h4 className="font-medium text-gray-900">{doc.title}</h4>
                      <p className="text-sm text-gray-500">{doc.description}</p>
                    </div>
                  </div>
                  <Button
                    onClick={() => handleOpenPdf(doc.id)}
                    disabled={isLoading || !student}
                    className={`${colors.button} text-white flex items-center gap-2`}
                  >
                    {isLoading ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                        Gerando...
                      </>
                    ) : (
                      <>
                        <ExternalLink size={16} />
                        Abrir PDF
                      </>
                    )}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Fechar */}
        <div className="flex justify-end pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default DocumentGeneratorModal;
