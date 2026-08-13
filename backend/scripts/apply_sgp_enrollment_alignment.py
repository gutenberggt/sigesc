"""Codemod idempotente para campos SGP que pertencem à entidade Enrollment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 padrão, encontrado {count}")
    return text.replace(old, new, 1)


def in_block(text, start, end, old, new, label):
    a = text.index(start); b = text.index(end, a + len(start)); block = text[a:b]
    if block.count(old) != 1:
        raise RuntimeError(f"{label}: estrutura inesperada")
    return text[:a] + block.replace(old, new, 1) + text[b:]


def patch_models():
    p = ROOT / "backend/models.py"
    text = p.read_text(encoding="utf-8")
    fields = """    enrollment_end_date: Optional[str] = None
    high_school_eja_completion_date: Optional[str] = None
    needs_pedagogical_support: Optional[bool] = None
    sgp_enrollment_id: Optional[str] = None  # ID externo; nunca substitui Enrollment.id
"""
    a = text.index("class EnrollmentBase(BaseModel):"); b = text.index("class EnrollmentCreate(EnrollmentBase):", a)
    if "enrollment_end_date: Optional[str]" not in text[a:b]:
        text = in_block(text, "class EnrollmentBase(BaseModel):", "class EnrollmentCreate(EnrollmentBase):", "    enrollment_number: Optional[str] = None  # Número da matrícula\n", "    enrollment_number: Optional[str] = None  # Número da matrícula\n" + fields, "EnrollmentBase fields")
    a = text.index("class EnrollmentUpdate(BaseModel):"); b = text.index("class Enrollment(EnrollmentBase):", a)
    if "enrollment_end_date: Optional[str]" not in text[a:b]:
        text = in_block(text, "class EnrollmentUpdate(BaseModel):", "class Enrollment(EnrollmentBase):", "    enrollment_number: Optional[str] = None\n", "    enrollment_number: Optional[str] = None\n" + fields, "EnrollmentUpdate fields")
    p.write_text(text, encoding="utf-8")


def patch_frontend():
    p = ROOT / "frontend/src/pages/StudentsComplete.js"
    text = p.read_text(encoding="utf-8")

    if "const initialEnrollmentMetadata" not in text:
        marker = "};\n\n// Função para calcular a idade a partir da data de nascimento\n"
        addition = """};

const initialEnrollmentMetadata = {
  id: '',
  class_id: '',
  enrollment_end_date: '',
  high_school_eja_completion_date: '',
  needs_pedagogical_support: '',
};

// Função para calcular a idade a partir da data de nascimento
"""
        text = once(text, marker, addition, "initial enrollment metadata")

    if "const [enrollmentMetadata, setEnrollmentMetadata]" not in text:
        text = once(text, "  const [formData, setFormData] = useState(initialFormData);\n", "  const [formData, setFormData] = useState(initialFormData);\n  const [enrollmentMetadata, setEnrollmentMetadata] = useState(initialEnrollmentMetadata);\n", "enrollment metadata state")

    if "loadCurrentEnrollmentMetadata" not in text:
        marker = "  const handleCreate = () => {\n"
        helpers = '''  const loadCurrentEnrollmentMetadata = async (student) => {
    if (!student?.id) {
      setEnrollmentMetadata(initialEnrollmentMetadata);
      return;
    }
    try {
      const result = await enrollmentsAPI.getAll(student.id, student.class_id || null);
      const enrollments = Array.isArray(result) ? result : (result?.items || []);
      const current = enrollments.find(e => e.class_id === student.class_id && e.status === 'active')
        || enrollments.find(e => e.class_id === student.class_id)
        || enrollments.find(e => e.status === 'active')
        || null;
      setEnrollmentMetadata(current ? {
        id: current.id || '',
        class_id: current.class_id || '',
        enrollment_end_date: current.enrollment_end_date || '',
        high_school_eja_completion_date: current.high_school_eja_completion_date || '',
        needs_pedagogical_support: current.needs_pedagogical_support === true
          ? true
          : current.needs_pedagogical_support === false ? false : '',
      } : initialEnrollmentMetadata);
    } catch (error) {
      console.warn('Não foi possível carregar metadados da matrícula:', error);
      setEnrollmentMetadata(initialEnrollmentMetadata);
    }
  };

  const persistCurrentEnrollmentMetadata = async (student) => {
    if (!student?.id || !student?.class_id) return;
    let enrollmentId = enrollmentMetadata.class_id === student.class_id ? enrollmentMetadata.id : '';
    if (!enrollmentId) {
      const result = await enrollmentsAPI.getAll(student.id, student.class_id);
      const enrollments = Array.isArray(result) ? result : (result?.items || []);
      const current = enrollments.find(e => e.class_id === student.class_id && e.status === 'active')
        || enrollments.find(e => e.class_id === student.class_id);
      enrollmentId = current?.id || '';
    }
    if (!enrollmentId) return;
    await enrollmentsAPI.update(enrollmentId, {
      enrollment_end_date: enrollmentMetadata.enrollment_end_date || null,
      high_school_eja_completion_date: enrollmentMetadata.high_school_eja_completion_date || null,
      needs_pedagogical_support: enrollmentMetadata.needs_pedagogical_support === ''
        ? null
        : enrollmentMetadata.needs_pedagogical_support,
    });
  };

'''
        text = once(text, marker, helpers + marker, "enrollment metadata helpers")

    if "setEnrollmentMetadata(initialEnrollmentMetadata);" not in text[text.index("const handleCreate"):text.index("const handleView")]:
        text = once(text, "    setViewMode(false);\n    setFormData({\n", "    setViewMode(false);\n    setEnrollmentMetadata(initialEnrollmentMetadata);\n    setFormData({\n", "create reset enrollment")

    # Carrega matrícula canônica tanto em visualizar quanto editar.
    view_anchor = "    setFormData(mergedData);\n    setFormTabIndex(0);\n    setIsModalOpen(true);\n"
    if text.count("await loadCurrentEnrollmentMetadata(freshStudent);") < 2:
        # Há duas ocorrências idênticas (view/edit); substituir ambas deliberadamente.
        if text.count(view_anchor) != 2:
            raise RuntimeError(f"load metadata anchors: esperado 2, encontrado {text.count(view_anchor)}")
        text = text.replace(view_anchor, "    setFormData(mergedData);\n    await loadCurrentEnrollmentMetadata(freshStudent);\n    setFormTabIndex(0);\n    setIsModalOpen(true);\n")

    old_submit = """    try {
      if (editingStudent) {
        await studentsAPI.update(editingStudent.id, cleanData);
        showAlert('success', 'Aluno atualizado com sucesso');
      } else {
        await studentsAPI.create(cleanData);
        showAlert('success', 'Aluno cadastrado com sucesso');
      }
"""
    new_submit = """    try {
      if (editingStudent) {
        const updatedStudent = await studentsAPI.update(editingStudent.id, cleanData);
        await persistCurrentEnrollmentMetadata(updatedStudent || { ...editingStudent, ...cleanData });
        showAlert('success', 'Aluno atualizado com sucesso');
      } else {
        const createdStudent = await studentsAPI.create(cleanData);
        await persistCurrentEnrollmentMetadata(createdStudent);
        showAlert('success', 'Aluno cadastrado com sucesso');
      }
"""
    if "await persistCurrentEnrollmentMetadata" not in text[text.index("const handleSubmit"):text.index("const updateFormData")]:
        text = once(text, old_submit, new_submit, "persist enrollment metadata")

    program_anchor = """      {/* Matrícula em Atendimento/Programa. AEE é liberado apenas para o público da Educação Especial. */}
"""
    metadata_ui = """      <div className=\"mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg\">
        <h3 className=\"text-lg font-semibold text-gray-900 mb-1\">Dados Complementares da Matrícula</h3>
        <p className=\"text-xs text-gray-600 mb-4\">Estes dados pertencem à matrícula vigente e são mantidos separadamente do cadastro permanente do estudante.</p>
        <div className=\"grid grid-cols-1 md:grid-cols-3 gap-4\">
          <div>
            <label className=\"block text-sm font-medium text-gray-700 mb-1\">Data final da matrícula</label>
            <input type=\"date\" value={enrollmentMetadata.enrollment_end_date || ''} onChange={(e) => setEnrollmentMetadata(prev => ({ ...prev, enrollment_end_date: e.target.value }))} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" />
          </div>
          <div>
            <label className=\"block text-sm font-medium text-gray-700 mb-1\">Conclusão do Ensino Médio/EJA</label>
            <input type=\"date\" value={enrollmentMetadata.high_school_eja_completion_date || ''} onChange={(e) => setEnrollmentMetadata(prev => ({ ...prev, high_school_eja_completion_date: e.target.value }))} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" />
          </div>
          <div>
            <label className=\"block text-sm font-medium text-gray-700 mb-1\">Necessidade de apoio pedagógico</label>
            <select value={enrollmentMetadata.needs_pedagogical_support === '' ? '' : String(enrollmentMetadata.needs_pedagogical_support)} onChange={(e) => setEnrollmentMetadata(prev => ({ ...prev, needs_pedagogical_support: e.target.value === '' ? '' : e.target.value === 'true' }))} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\">
              <option value=\"\">Não informado</option>
              <option value=\"true\">Sim</option>
              <option value=\"false\">Não</option>
            </select>
          </div>
        </div>
      </div>

"""
    if "Dados Complementares da Matrícula" not in text:
        text = once(text, program_anchor, metadata_ui + program_anchor, "enrollment metadata UI")

    p.write_text(text, encoding="utf-8")


def main():
    patch_models(); patch_frontend(); print("Alinhamento de matrícula aplicado")


if __name__ == "__main__":
    main()
