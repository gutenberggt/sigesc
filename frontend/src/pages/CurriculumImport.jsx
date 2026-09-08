import { useState } from 'react';
import { BookOpen, ListChecks } from 'lucide-react';
import ScopedCurriculumVersions from '@/components/curriculum/ScopedCurriculumVersions';
import CurriculumSkillImportLegacy from '@/pages/CurriculumSkillImportLegacy';

export default function CurriculumImport() {
  const [mode, setMode] = useState('versions');

  if (mode === 'skills') {
    return (
      <div data-testid="curriculum-workspace-skills">
        <div className="px-6 pt-5 max-w-[1400px] mx-auto">
          <div className="inline-flex border rounded-lg p-1 bg-white">
            <button
              type="button"
              onClick={() => setMode('versions')}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm text-gray-600 hover:bg-gray-50"
            >
              <BookOpen className="h-4 w-4" /> Versões Curriculares
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm bg-purple-600 text-white"
            >
              <ListChecks className="h-4 w-4" /> Importar habilidades
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-2">Fluxo legado preservado para alimentar o catálogo de habilidades BNCC/DCM.</p>
        </div>
        <CurriculumSkillImportLegacy />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[1500px] mx-auto space-y-5" data-testid="curriculum-workspace-versions">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-purple-600" />
            <h1 className="text-2xl font-bold text-gray-900">Núcleo Curricular</h1>
          </div>
          <p className="text-sm text-gray-500 mt-1">Fontes oficiais → Versão Curricular por componente/série/bimestre → Plano de Ensino Bimestral.</p>
        </div>
        <div className="inline-flex border rounded-lg p-1 bg-white">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm bg-purple-600 text-white"
          >
            <BookOpen className="h-4 w-4" /> Versões Curriculares
          </button>
          <button
            type="button"
            onClick={() => setMode('skills')}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm text-gray-600 hover:bg-gray-50"
          >
            <ListChecks className="h-4 w-4" /> Importar habilidades
          </button>
        </div>
      </div>

      <ScopedCurriculumVersions onOpenSkillImport={() => setMode('skills')} />
    </div>
  );
}
