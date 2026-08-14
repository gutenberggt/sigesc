"""Transformação idempotente do alinhamento canônico de responsáveis SGP.

Executar apenas na branch feat/sgp-student-canonical-alignment.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "backend/models.py"
UI = ROOT / "frontend/src/pages/Guardians.js"
TEST = ROOT / "backend/tests/test_guardian_links.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Trecho esperado não encontrado: {label}")
    return text.replace(old, new, 1)


models = MODELS.read_text(encoding="utf-8")
models = replace_once(
    models,
    """    phone: Optional[str] = None\n    cell_phone: Optional[str] = None\n    email: Optional[str] = None\n""",
    """    phone: Optional[str] = None\n    cell_phone: Optional[str] = None\n    secondary_cell_phone: Optional[str] = None\n    email: Optional[str] = None\n""",
    "GuardianBase.secondary_cell_phone",
)
models = replace_once(
    models,
    """    relationship: Literal['pai', 'mae', 'avo', 'tio', 'irmao', 'responsavel', 'outro'] = 'responsavel'\n    student_ids: List[str] = []\n    user_id: Optional[str] = None  # Se o responsável tem acesso ao portal\n""",
    """    relationship: Literal['pai', 'mae', 'avo', 'tio', 'irmao', 'responsavel', 'outro'] = 'responsavel'\n    student_ids: List[str] = []\n    primary_student_ids: List[str] = []  # Subconjunto de student_ids: vínculo legal principal\n    user_id: Optional[str] = None  # Se o responsável tem acesso ao portal\n""",
    "GuardianBase.primary_student_ids",
)
models = replace_once(
    models,
    """class GuardianUpdate(BaseModel):\n    full_name: Optional[str] = None\n""",
    """class GuardianUpdate(BaseModel):\n    # Todos os campos editáveis de GuardianBase precisam ser aceitos no PATCH/PUT.\n    # Antes, apenas full_name persistia apesar de a UI permitir editar os demais.\n    full_name: Optional[str] = None\n    cpf: Optional[str] = None\n    rg: Optional[str] = None\n    birth_date: Optional[str] = None\n    phone: Optional[str] = None\n    cell_phone: Optional[str] = None\n    secondary_cell_phone: Optional[str] = None\n    email: Optional[str] = None\n    address: Optional[str] = None\n    address_number: Optional[str] = None\n    address_complement: Optional[str] = None\n    neighborhood: Optional[str] = None\n    city: Optional[str] = None\n    state: Optional[str] = None\n    zip_code: Optional[str] = None\n    occupation: Optional[str] = None\n    workplace: Optional[str] = None\n    work_phone: Optional[str] = None\n    relationship: Optional[Literal['pai', 'mae', 'avo', 'tio', 'irmao', 'responsavel', 'outro']] = None\n    student_ids: Optional[List[str]] = None\n    primary_student_ids: Optional[List[str]] = None\n    user_id: Optional[str] = None\n    status: Optional[Literal['active', 'inactive']] = None\n    observations: Optional[str] = None\n""",
    "GuardianUpdate completo",
)
MODELS.write_text(models, encoding="utf-8")

ui = UI.read_text(encoding="utf-8")
ui = replace_once(
    ui,
    """  phone: '',\n  cell_phone: '',\n  email: '',\n""",
    """  phone: '',\n  cell_phone: '',\n  secondary_cell_phone: '',\n  email: '',\n""",
    "UI secondary_cell_phone",
)
ui = replace_once(
    ui,
    """  relationship: 'responsavel',\n  student_ids: [],\n  user_id: null,\n""",
    """  relationship: 'responsavel',\n  student_ids: [],\n  primary_student_ids: [],\n  user_id: null,\n""",
    "UI primary_student_ids",
)
ui = replace_once(
    ui,
    """  const handleStudentToggle = (studentId) => {\n    setFormData(prev => {\n      const currentIds = prev.student_ids || [];\n      if (currentIds.includes(studentId)) {\n        return { ...prev, student_ids: currentIds.filter(id => id !== studentId) };\n      } else {\n        return { ...prev, student_ids: [...currentIds, studentId] };\n      }\n    });\n  };\n""",
    """  const handleStudentToggle = (studentId) => {\n    setFormData(prev => {\n      const currentIds = prev.student_ids || [];\n      const currentPrimaryIds = prev.primary_student_ids || [];\n      if (currentIds.includes(studentId)) {\n        return {\n          ...prev,\n          student_ids: currentIds.filter(id => id !== studentId),\n          primary_student_ids: currentPrimaryIds.filter(id => id !== studentId)\n        };\n      }\n      return { ...prev, student_ids: [...currentIds, studentId] };\n    });\n  };\n\n  const handlePrimaryStudentToggle = (studentId, checked) => {\n    setFormData(prev => {\n      const linked = prev.student_ids || [];\n      const primary = prev.primary_student_ids || [];\n      if (checked) {\n        return {\n          ...prev,\n          student_ids: linked.includes(studentId) ? linked : [...linked, studentId],\n          primary_student_ids: primary.includes(studentId) ? primary : [...primary, studentId]\n        };\n      }\n      return { ...prev, primary_student_ids: primary.filter(id => id !== studentId) };\n    });\n  };\n""",
    "UI handlers de vínculo",
)
ui = replace_once(
    ui,
    """      <div className=\"grid grid-cols-1 md:grid-cols-3 gap-4\">\n        <div>\n          <label className=\"block text-sm font-medium text-gray-700 mb-1\">Telefone Fixo</label>\n""",
    """      <div className=\"grid grid-cols-1 md:grid-cols-4 gap-4\">\n        <div>\n          <label className=\"block text-sm font-medium text-gray-700 mb-1\">Telefone Fixo</label>\n""",
    "grid contato",
)
ui = replace_once(
    ui,
    """        <div>\n          <label className=\"block text-sm font-medium text-gray-700 mb-1\">E-mail</label>\n          <input\n            type=\"email\"\n            value={formData.email}\n""",
    """        <div>\n          <label className=\"block text-sm font-medium text-gray-700 mb-1\">Celular 2</label>\n          <input\n            type=\"text\"\n            value={formatPhone(formData.secondary_cell_phone || '')}\n            onChange={(e) => updateFormData('secondary_cell_phone', e.target.value.replace(/\\D/g, '').slice(0, 11))}\n            disabled={viewMode}\n            maxLength={14}\n            className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\"\n            placeholder=\"(00)00000-0000\"\n          />\n        </div>\n        <div>\n          <label className=\"block text-sm font-medium text-gray-700 mb-1\">E-mail</label>\n          <input\n            type=\"email\"\n            value={formData.email}\n""",
    "campo celular 2",
)
old_cards = """          {students.map(student => (\n            <label\n              key={student.id}\n              className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${\n                formData.student_ids?.includes(student.id)\n                  ? 'border-blue-500 bg-blue-50'\n                  : 'border-gray-200 hover:border-gray-300'\n              } ${viewMode ? 'cursor-default' : ''}`}\n            >\n              <input\n                type=\"checkbox\"\n                checked={formData.student_ids?.includes(student.id) || false}\n                onChange={() => !viewMode && handleStudentToggle(student.id)}\n                disabled={viewMode}\n                className=\"h-4 w-4 text-blue-600 rounded mr-3\"\n              />\n              <div>\n                <p className=\"font-medium text-gray-900\">{student.full_name || 'Sem nome'}</p>\n                <p className=\"text-xs text-gray-500\">Matrícula: {student.enrollment_number}</p>\n              </div>\n            </label>\n          ))}\n"""
new_cards = """          {students.map(student => {\n            const isLinked = formData.student_ids?.includes(student.id) || false;\n            const isPrimary = formData.primary_student_ids?.includes(student.id) || false;\n            return (\n              <div\n                key={student.id}\n                className={`p-3 border rounded-lg transition-colors ${\n                  isLinked ? 'border-blue-500 bg-blue-50' : 'border-gray-200'\n                }`}\n              >\n                <label className={`flex items-center ${viewMode ? 'cursor-default' : 'cursor-pointer'}`}>\n                  <input\n                    type=\"checkbox\"\n                    checked={isLinked}\n                    onChange={() => !viewMode && handleStudentToggle(student.id)}\n                    disabled={viewMode}\n                    className=\"h-4 w-4 text-blue-600 rounded mr-3\"\n                  />\n                  <div>\n                    <p className=\"font-medium text-gray-900\">{student.full_name || 'Sem nome'}</p>\n                    <p className=\"text-xs text-gray-500\">Matrícula: {student.enrollment_number}</p>\n                  </div>\n                </label>\n                <label className={`mt-3 flex items-center gap-2 text-xs ${isLinked ? 'text-gray-700' : 'text-gray-400'} ${viewMode || !isLinked ? 'cursor-default' : 'cursor-pointer'}`}>\n                  <input\n                    type=\"checkbox\"\n                    checked={isPrimary}\n                    onChange={(e) => handlePrimaryStudentToggle(student.id, e.target.checked)}\n                    disabled={viewMode || !isLinked}\n                    className=\"h-4 w-4 text-blue-600 rounded\"\n                  />\n                  Responsável legal principal deste estudante\n                </label>\n              </div>\n            );\n          })}\n"""
ui = replace_once(ui, old_cards, new_cards, "cards de vínculo principal")
ui = replace_once(
    ui,
    """          <strong>Total selecionado:</strong> {formData.student_ids?.length || 0} aluno(s)\n""",
    """          <strong>Total selecionado:</strong> {formData.student_ids?.length || 0} aluno(s) · <strong>Principal para:</strong> {formData.primary_student_ids?.length || 0}\n""",
    "resumo de vínculo",
)
UI.write_text(ui, encoding="utf-8")

TEST.parent.mkdir(parents=True, exist_ok=True)
TEST.write_text(
    '''import sys\nimport unittest\nfrom pathlib import Path\n\nBACKEND_DIR = Path(__file__).resolve().parents[1]\nif str(BACKEND_DIR) not in sys.path:\n    sys.path.insert(0, str(BACKEND_DIR))\n\nfrom utils.guardian_links import normalize_guardian_student_links\n\n\nclass GuardianLinksTests(unittest.TestCase):\n    def test_deduplicates_preserving_order(self):\n        linked, primary = normalize_guardian_student_links(["a", "b", "a", ""], ["b", "b"])\n        self.assertEqual(linked, ["a", "b"])\n        self.assertEqual(primary, ["b"])\n\n    def test_primary_must_be_linked(self):\n        with self.assertRaises(ValueError):\n            normalize_guardian_student_links(["a"], ["b"])\n\n    def test_empty_legacy_values_are_compatible(self):\n        linked, primary = normalize_guardian_student_links(None, None)\n        self.assertEqual(linked, [])\n        self.assertEqual(primary, [])\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)
