import { useState } from 'react';
import { FileText, Download, X, GraduationCap, ClipboardCheck, Calendar, User } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { documentsAPI } from '@/services/api';

/**
 * Modal para geração de documentos PDF do aluno
 * - Boletim Escolar
 * - Ficha Individual
 * - Declaração de Matrícula
 * - Declaração de Frequência
 */
export const DocumentGeneratorModal = ({ 
  isOpen, 
  onClose, 
  student,
  academicYear = '2025'
}) => {
  const [loading, setLoading] = useState(null); // 'boletim' | 'ficha' | 'matricula' | 'frequencia' | null
  const [error, setError] = useState(null);

  const handleDownload = async (type) => {
    if (!student?.id) {
      setError('Aluno não selecionado');
      return;
    }

    setLoading(type);
    setError(null);

    try {
      let url;
      let filename;

      switch (type) {
        case 'boletim':
          url = documentsAPI.getBoletimUrl(student.id, academicYear);
          filename = `boletim_${student.full_name?.replace(/\s/g, '_')}_${academicYear}.pdf`;
          break;
        case 'ficha':
          url = documentsAPI.getFichaIndividualUrl(student.id, academicYear);
          filename = `ficha_individual_${student.full_name?.replace(/\s/g, '_')}_${academicYear}.pdf`;
          break;
        case 'matricula':
          url = documentsAPI.getDeclaracaoMatriculaUrl(student.id, academicYear);
          filename = `declaracao_matricula_${student.full_name?.replace(/\s/g, '_')}.pdf`;
          break;
        case 'frequencia':
          url = documentsAPI.getDeclaracaoFrequenciaUrl(student.id, academicYear);
          filename = `declaracao_frequencia_${student.full_name?.replace(/\s/g, '_')}.pdf`;
          break;
        default:
          throw new Error('Tipo de documento inválido');
      }

      // Baixar o PDF
      const blob = await documentsAPI.downloadDocument(url);
      
      // Criar link de download
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

    } catch (err) {
      console.error('Erro ao gerar documento:', err);
      setError(err.response?.data?.detail || 'Erro ao gerar documento. Verifique se o aluno possui matrícula ativa.');
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
    }
  ];

  const colorClasses = {
    blue: {
      bg: 'bg-blue-50 hover:bg-blue-100',
      border: 'border-blue-200 hover:border-blue-400',
      icon: 'text-blue-600',
      button: 'bg-blue-600 hover:bg-blue-700'
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
                    onClick={() => handleDownload(doc.id)}
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
                        <Download size={16} />
                        Baixar PDF
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
