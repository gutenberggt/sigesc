import { useNavigate } from 'react-router-dom';
import { GraduationCap, FileText, ArrowRight } from 'lucide-react';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

export default function AlunoDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-6" data-testid="aluno-dashboard">
        {/* Saudação */}
        <Card className="border-2 border-blue-100">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
              <GraduationCap className="w-7 h-7 text-blue-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Olá, {user?.full_name?.split(' ')[0] || 'Aluno(a)'}!</h1>
              <p className="text-sm text-gray-600">Bem-vindo(a) ao seu portal.</p>
            </div>
          </CardContent>
        </Card>

        {/* Ações disponíveis */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            onClick={() => navigate('/aluno/boletim')}
            className="text-left group"
            data-testid="btn-boletim"
          >
            <Card className="hover:border-blue-400 hover:shadow-md transition-all cursor-pointer h-full">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-lg bg-blue-600 flex items-center justify-center">
                      <FileText className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-gray-900">Boletim</h2>
                      <p className="text-xs text-gray-500">Notas, faltas e situação</p>
                    </div>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-blue-600 group-hover:translate-x-1 transition-all" />
                </div>
              </CardContent>
            </Card>
          </button>
        </div>
      </div>
    </Layout>
  );
}
