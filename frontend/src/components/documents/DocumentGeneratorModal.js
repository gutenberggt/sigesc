import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExternalLink, GraduationCap, ClipboardCheck, Calendar, User, Award, ArrowRightLeft, BookOpen } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { documentsAPI, getToken } from '@/services/api';

export const DocumentGeneratorModal = ({ 
  isOpen, 
  onClose, 
  student,
  academicYear = new Date().getFullYear().toString(),
  classInfo = null
}) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);

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
    if (!student?.id) { setError('Aluno não selecionado'); return; }
    setLoading(type);
    setError(null);
    try {
      const urlMap = {
        boletim: documentsAPI.getBoletimUrl(student.id, academicYear),
        ficha: documentsAPI.getFichaIndividualUrl(student.id, academicYear),
        matricula: documentsAPI.getDeclaracaoMatriculaUrl(student.id, academicYear),
        frequencia: documentsAPI.getDeclaracaoFrequenciaUrl(student.id, academicYear),
        transferencia: documentsAPI.getDeclaracaoTransferenciaUrl(student.id, academicYear),
        certificado: documentsAPI.getCertificadoUrl(student.id, academicYear),
      };
      const url = urlMap[type];
      if (!url) throw new Error('Tipo de documento inválido');

      const token = getToken();
      const response = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Erro ao gerar documento');
      }
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const newWindow = window.open(blobUrl, '_blank');
      if (newWindow) { newWindow.onbeforeunload = () => window.URL.revokeObjectURL(blobUrl); }
    } catch (err) {
      console.error('Erro ao gerar documento:', err);
      setError(err.message || 'Erro ao gerar documento.');
    } finally {
      setLoading(null);
    }
  };

  const documents = [
    { id: 'boletim', title: 'Boletim Escolar', icon: GraduationCap, color: 'blue' },
    { id: 'ficha', title: 'Ficha Individual', icon: User, color: 'orange' },
    { id: 'matricula', title: 'Decl. Matrícula', icon: ClipboardCheck, color: 'green' },
    { id: 'frequencia', title: 'Decl. Frequência', icon: Calendar, color: 'purple' },
    { id: 'transferencia', title: 'Decl. Transferência', icon: ArrowRightLeft, color: 'rose' },
    ...(isEligibleForCertificate ? [{ id: 'certificado', title: 'Certificado', icon: Award, color: 'indigo' }] : []),
    { id: 'historico', title: 'Histórico Escolar', icon: BookOpen, color: 'amber', isNavigation: true },
  ];

  const colorMap = {
    blue: { bg: 'bg-blue-50 hover:bg-blue-100', border: 'border-blue-200', icon: 'text-blue-600', btn: 'bg-blue-600 hover:bg-blue-700' },
    orange: { bg: 'bg-orange-50 hover:bg-orange-100', border: 'border-orange-200', icon: 'text-orange-600', btn: 'bg-orange-600 hover:bg-orange-700' },
    green: { bg: 'bg-green-50 hover:bg-green-100', border: 'border-green-200', icon: 'text-green-600', btn: 'bg-green-600 hover:bg-green-700' },
    purple: { bg: 'bg-purple-50 hover:bg-purple-100', border: 'border-purple-200', icon: 'text-purple-600', btn: 'bg-purple-600 hover:bg-purple-700' },
    rose: { bg: 'bg-rose-50 hover:bg-rose-100', border: 'border-rose-200', icon: 'text-rose-600', btn: 'bg-rose-600 hover:bg-rose-700' },
    indigo: { bg: 'bg-indigo-50 hover:bg-indigo-100', border: 'border-indigo-200', icon: 'text-indigo-600', btn: 'bg-indigo-600 hover:bg-indigo-700' },
    amber: { bg: 'bg-amber-50 hover:bg-amber-100', border: 'border-amber-200', icon: 'text-amber-600', btn: 'bg-amber-600 hover:bg-amber-700' },
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Gerar Documentos" size="md">
      <div className="space-y-3">
        {student && (
          <div className="bg-gray-50 rounded-lg px-4 py-3 border border-gray-200 flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
              <span className="text-blue-600 font-semibold text-sm">{student.full_name?.charAt(0)?.toUpperCase()}</span>
            </div>
            <div>
              <p className="font-medium text-gray-900 text-sm">{student.full_name}</p>
              <p className="text-xs text-gray-500">Ano Letivo: {academicYear}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-2 text-red-700 text-sm">{error}</div>
        )}

        <div className="grid grid-cols-2 gap-2">
          {documents.map((doc) => {
            const Icon = doc.icon;
            const c = colorMap[doc.color];
            const isLoading = loading === doc.id;

            return (
              <button
                key={doc.id}
                data-testid={`doc-btn-${doc.id}`}
                onClick={() => {
                  if (doc.isNavigation) { onClose(); navigate(`/admin/students/${student?.id}/historico`); }
                  else { handleOpenPdf(doc.id); }
                }}
                disabled={doc.isNavigation ? !student : (isLoading || !student)}
                className={`border rounded-lg p-3 transition-all text-left flex items-center gap-3 ${c.bg} ${c.border} disabled:opacity-50`}
              >
                <div className={`p-2 rounded-lg bg-white shrink-0 ${c.icon}`}>
                  <Icon size={20} />
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 text-sm leading-tight">{doc.title}</p>
                  <p className={`text-xs mt-0.5 ${isLoading ? 'text-blue-600' : c.icon}`}>
                    {isLoading ? 'Gerando...' : (doc.isNavigation ? 'Acessar' : 'Abrir PDF')}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        <div className="flex justify-end pt-2 border-t">
          <Button variant="outline" size="sm" onClick={onClose}>Fechar</Button>
        </div>
      </div>
    </Modal>
  );
};

export default DocumentGeneratorModal;
