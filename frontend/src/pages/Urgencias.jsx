import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, Home, Siren, ArrowRight } from 'lucide-react';

export default function Urgencias() {
  const navigate = useNavigate();

  return (
    <Layout>
      <div className="space-y-6" data-testid="urgencias-page">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2 text-gray-500 hover:text-blue-600 transition-colors mb-3"
              data-testid="urgencias-home"
            >
              <Home size={20} />
              <span>Início</span>
            </button>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Siren className="text-red-600" />
              Urgências
            </h1>
            <p className="text-sm text-gray-600 mt-1 max-w-3xl">
              Ferramentas para situações excepcionais que exigem emissão ou tratamento imediato de documentos escolares.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          As ferramentas desta área são de contingência. Cada recurso deve preservar as regras, permissões e fontes oficiais do SIGESC.
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <Card className="border-gray-200 hover:shadow-md transition-shadow" data-testid="urgencias-ficha-individual-card">
            <CardContent className="p-6 space-y-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-red-50 p-3">
                  <FileText className="text-red-600" size={24} />
                </div>
                <div className="min-w-0">
                  <h2 className="font-semibold text-lg text-gray-900">Ficha Individual</h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Gere uma Ficha Individual fiel ao modelo oficial, utilizando os dados cadastrais do SIGESC e notas ou conceitos informados manualmente.
                  </p>
                </div>
              </div>

              <Button
                type="button"
                className="w-full flex items-center justify-center gap-2"
                onClick={() => navigate('/admin/urgencias/ficha-individual')}
                data-testid="urgencias-open-ficha-individual"
              >
                Abrir Ficha Individual
                <ArrowRight size={18} />
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
