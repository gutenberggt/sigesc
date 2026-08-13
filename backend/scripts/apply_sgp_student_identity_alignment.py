"""Codemod idempotente: Nome Social + opção de sexo do SGP."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 padrão, encontrado {count}")
    return text.replace(old, new, 1)


def in_block(text, start, end, old, new, label):
    a = text.index(start)
    b = text.index(end, a + len(start))
    block = text[a:b]
    if block.count(old) != 1:
        raise RuntimeError(f"{label}: estrutura inesperada")
    return text[:a] + block.replace(old, new, 1) + text[b:]


def patch_models():
    p = ROOT / "backend/models.py"
    text = p.read_text(encoding="utf-8")
    for start, end, label in [
        ("class StudentBase(BaseModel):", "class StudentCreate(StudentBase):", "StudentBase"),
        ("class StudentUpdate(BaseModel):", "class Student(StudentBase):", "StudentUpdate"),
    ]:
        a = text.index(start); b = text.index(end, a); block = text[a:b]
        if "social_name: Optional[str]" not in block:
            text = in_block(text, start, end, "    full_name: Optional[str] = None\n", "    full_name: Optional[str] = None\n    social_name: Optional[str] = None  # Nome social, distinto do nome civil\n", f"{label}.social_name")
        a = text.index(start); b = text.index(end, a); block = text[a:b]
        if "'prefere_nao_informar'" not in block:
            text = in_block(text, start, end, "    sex: Optional[Literal['masculino', 'feminino']] = None\n", "    sex: Optional[Literal['masculino', 'feminino', 'prefere_nao_informar']] = None\n", f"{label}.sex")
    p.write_text(text, encoding="utf-8")


def patch_frontend():
    p = ROOT / "frontend/src/pages/StudentsComplete.js"
    text = p.read_text(encoding="utf-8")
    if "  social_name: '',\n" not in text:
        text = once(text, "  full_name: '',\n", "  full_name: '',\n  social_name: '',\n", "initial social_name")

    full_name_block = """          <div className=\"md:col-span-2\">
            <label className=\"block text-sm font-medium text-gray-700 mb-1\">Nome Completo *</label>
            <input
              type=\"text\"
              value={formData.full_name}
              onChange={(e) => updateFormData('full_name', e.target.value)}
              required
              disabled={viewMode}
              className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\"
            />
          </div>
"""
    social_block = full_name_block + """          <div className=\"md:col-span-2\">
            <label className=\"block text-sm font-medium text-gray-700 mb-1\">Nome Social</label>
            <input
              type=\"text\"
              value={formData.social_name || ''}
              onChange={(e) => updateFormData('social_name', e.target.value)}
              disabled={viewMode}
              placeholder=\"Preencha quando houver solicitação de uso do nome social\"
              className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\"
            />
            <p className=\"text-xs text-gray-500 mt-1\">O nome civil permanece preservado no cadastro.</p>
          </div>
"""
    if "value={formData.social_name" not in text:
        text = once(text, full_name_block, social_block, "Nome Social UI")
    if '<option value="prefere_nao_informar">Prefere não informar</option>' not in text:
        text = once(text, '            <option value="feminino">Feminino</option>\n', '            <option value="feminino">Feminino</option>\n            <option value="prefere_nao_informar">Prefere não informar</option>\n', "sexo opção")
    p.write_text(text, encoding="utf-8")


def main():
    patch_models(); patch_frontend(); print("Alinhamento de identidade aplicado")


if __name__ == "__main__":
    main()
