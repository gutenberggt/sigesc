"""Transformação determinística da feature de alinhamento territorial SGP.
Executar apenas na branch feat/sgp-student-canonical-alignment.
"""
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
    old = "    municipio: Optional[str] = None\n    estado: Optional[str] = None\n"
    new = old + "    codigo_ibge_uf: Optional[str] = None\n    codigo_ibge_municipio: Optional[str] = None\n"

    a = text.index("class MantenedoraBase(BaseModel):")
    b = text.index("class MantenedoraUpdate(BaseModel):", a)
    if "codigo_ibge_municipio" not in text[a:b]:
        text = in_block(text, "class MantenedoraBase(BaseModel):", "class MantenedoraUpdate(BaseModel):", old, new, "MantenedoraBase")

    a = text.index("class MantenedoraUpdate(BaseModel):")
    b = text.index("class Mantenedora(MantenedoraBase):", a)
    if "codigo_ibge_municipio" not in text[a:b]:
        text = in_block(text, "class MantenedoraUpdate(BaseModel):", "class Mantenedora(MantenedoraBase):", old, new, "MantenedoraUpdate")

    model = '''class StudentAddress(BaseModel):
    """Endereço residencial estruturado do estudante."""
    zip_code: Optional[str] = None
    state: Optional[str] = None
    state_ibge_code: Optional[str] = None
    city: Optional[str] = None
    city_ibge_code: Optional[str] = None
    neighborhood: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    geographic_location: Optional[str] = None
    differentiated_location: Optional[str] = None


'''
    if "class StudentAddress(BaseModel):" not in text:
        text = once(text, "class StudentBase(BaseModel):\n", model + "class StudentBase(BaseModel):\n", "StudentAddress")

    a = text.index("class StudentBase(BaseModel):")
    b = text.index("class StudentCreate(StudentBase):", a)
    if "address: Optional[StudentAddress]" not in text[a:b]:
        text = in_block(text, "class StudentBase(BaseModel):", "class StudentCreate(StudentBase):", "    email: Optional[str] = None  # Email do aluno\n", "    email: Optional[str] = None  # Email do aluno\n    address: Optional[StudentAddress] = None\n", "StudentBase.address")

    a = text.index("class StudentUpdate(BaseModel):")
    b = text.index("class Student(StudentBase):", a)
    if "address: Optional[StudentAddress]" not in text[a:b]:
        text = in_block(text, "class StudentUpdate(BaseModel):", "class Student(StudentBase):", "    email: Optional[str] = None  # Email do aluno\n", "    email: Optional[str] = None  # Email do aluno\n    address: Optional[StudentAddress] = None\n", "StudentUpdate.address")

    p.write_text(text, encoding="utf-8")


def patch_router():
    p = ROOT / "backend/routers/mantenedora.py"
    text = p.read_text(encoding="utf-8")
    if '"codigo_ibge_municipio"' not in text:
        text = once(text, '                "estado": "PA",\n', '                "estado": "PA",\n                "codigo_ibge_uf": "",\n                "codigo_ibge_municipio": "",\n', "mantenedora default")
    p.write_text(text, encoding="utf-8")


def patch_mantenedora_ui():
    p = ROOT / "frontend/src/pages/Mantenedora.js"
    text = p.read_text(encoding="utf-8")
    if "ibgeCodesFromViaCep" not in text:
        text = once(text, "import { formatCEP, formatPhone, formatCPF, formatCNPJ } from '@/utils/formatters';\n", "import { formatCEP, formatPhone, formatCPF, formatCNPJ } from '@/utils/formatters';\nimport { ibgeCodesFromViaCep } from '@/utils/ibgeAddress';\n", "import ibge")
    if "codigo_ibge_uf: ''" not in text:
        text = once(text, "    municipio: '',\n    estado: '',\n", "    municipio: '',\n    estado: '',\n    codigo_ibge_uf: '',\n    codigo_ibge_municipio: '',\n", "form ibge")
    if "codigo_ibge_uf: data.codigo_ibge_uf" not in text:
        text = once(text, "        municipio: data.municipio || '',\n        estado: data.estado || '',\n", "        municipio: data.municipio || '',\n        estado: data.estado || '',\n        codigo_ibge_uf: data.codigo_ibge_uf || '',\n        codigo_ibge_municipio: data.codigo_ibge_municipio || '',\n", "load ibge")

    old = """    } else if (field === 'cnpj') {
      formattedValue = formatCNPJ(value);
    }
    
    setFormData(prev => ({ ...prev, [field]: formattedValue }));
"""
    new = """    } else if (field === 'cnpj') {
      formattedValue = formatCNPJ(value);
    } else if (field === 'codigo_ibge_uf') {
      formattedValue = String(value || '').replace(/\\D/g, '').slice(0, 2);
    } else if (field === 'codigo_ibge_municipio') {
      formattedValue = String(value || '').replace(/\\D/g, '').slice(0, 7);
    }
    
    setFormData(prev => {
      const next = { ...prev, [field]: formattedValue };
      if (field === 'estado' && formattedValue !== prev.estado) {
        next.codigo_ibge_uf = '';
        next.codigo_ibge_municipio = '';
      } else if (field === 'municipio' && formattedValue !== prev.municipio) {
        next.codigo_ibge_municipio = '';
      }
      return next;
    });
"""
    if "next.codigo_ibge_uf" not in text:
        text = once(text, old, new, "edit codes")

    old = """        if (!data.erro) {
          setFormData(prev => ({
            ...prev,
            logradouro: data.logradouro || prev.logradouro,
            bairro: data.bairro || prev.bairro,
            municipio: data.localidade || prev.municipio,
            estado: data.uf || prev.estado
          }));
        }
"""
    new = """        if (!data.erro) {
          const { cityIbgeCode, stateIbgeCode } = ibgeCodesFromViaCep(data);
          setFormData(prev => ({
            ...prev,
            logradouro: data.logradouro || prev.logradouro,
            bairro: data.bairro || prev.bairro,
            municipio: data.localidade || prev.municipio,
            estado: data.uf || prev.estado,
            codigo_ibge_uf: stateIbgeCode || prev.codigo_ibge_uf,
            codigo_ibge_municipio: cityIbgeCode || prev.codigo_ibge_municipio
          }));
        }
"""
    if "cityIbgeCode, stateIbgeCode" not in text:
        text = once(text, old, new, "viacep codes")

    anchor = """              </div>
            </CardContent>
          </Card>

          {/* Contato */}
"""
    addition = """              </div>
              <div className=\"grid grid-cols-2 gap-4\">
                <div>
                  <Label htmlFor=\"codigo_ibge_uf\">Código IBGE da UF</Label>
                  <Input id=\"codigo_ibge_uf\" value={formData.codigo_ibge_uf} onChange={(e) => handleInputChange('codigo_ibge_uf', e.target.value)} inputMode=\"numeric\" maxLength={2} placeholder=\"Ex: 15\" />
                </div>
                <div>
                  <Label htmlFor=\"codigo_ibge_municipio\">Código IBGE do Município</Label>
                  <Input id=\"codigo_ibge_municipio\" value={formData.codigo_ibge_municipio} onChange={(e) => handleInputChange('codigo_ibge_municipio', e.target.value)} inputMode=\"numeric\" maxLength={7} placeholder=\"7 dígitos\" />
                </div>
              </div>
              <p className=\"text-xs text-gray-500\">Preenchidos automaticamente pelo CEP quando disponíveis e editáveis para conferência.</p>
            </CardContent>
          </Card>

          {/* Contato */}
"""
    if 'htmlFor="codigo_ibge_municipio"' not in text:
        text = once(text, anchor, addition, "ibge UI")
    p.write_text(text, encoding="utf-8")


def patch_student_ui():
    p = ROOT / "frontend/src/pages/StudentsComplete.js"
    text = p.read_text(encoding="utf-8")
    if "buildStudentAddressDefaultsFromMantenedora" not in text:
        marker = "} from '@/utils/specialEducation';\n"
        text = once(text, marker, marker + "import { EMPTY_STUDENT_ADDRESS, buildStudentAddressDefaultsFromMantenedora, ibgeCodesFromViaCep, updateStudentAddressField } from '@/utils/ibgeAddress';\n", "student import")
    if "address: { ...EMPTY_STUDENT_ADDRESS }" not in text:
        text = once(text, "  comunidade_tradicional: 'nao_pertence',\n", "  comunidade_tradicional: 'nao_pertence',\n  address: { ...EMPTY_STUDENT_ADDRESS },\n", "initial address")
    if "buildStudentAddressDefaultsFromMantenedora(mantenedoraConfig)" not in text:
        text = once(text, "      enrollment_number: ''\n", "      enrollment_number: '',\n      address: buildStudentAddressDefaultsFromMantenedora(mantenedoraConfig)\n", "student defaults")

    old = """  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };
"""
    extra = """
  const updateAddressData = (field, value) => {
    setFormData(prev => ({ ...prev, address: updateStudentAddressField(prev.address, field, value) }));
  };

  const handleStudentAddressCEPBlur = async () => {
    const cep = String(formData.address?.zip_code || '').replace(/\\D/g, '');
    if (cep.length !== 8) return;
    try {
      const response = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const data = await response.json();
      if (data.erro) return;
      const { cityIbgeCode, stateIbgeCode } = ibgeCodesFromViaCep(data);
      setFormData(prev => ({ ...prev, address: {
        ...EMPTY_STUDENT_ADDRESS, ...(prev.address || {}), zip_code: cep,
        street: data.logradouro || prev.address?.street || '',
        neighborhood: data.bairro || prev.address?.neighborhood || '',
        city: data.localidade || prev.address?.city || '',
        state: data.uf || prev.address?.state || '',
        state_ibge_code: stateIbgeCode || prev.address?.state_ibge_code || '',
        city_ibge_code: cityIbgeCode || prev.address?.city_ibge_code || ''
      }}));
    } catch (error) {
      console.error('Erro ao buscar CEP do estudante:', error);
    }
  };
"""
    if "handleStudentAddressCEPBlur" not in text:
        text = once(text, old, old + extra, "student address handlers")

    anchor = """      </div>
    </div>
  );

  const tabDocumentos = (
"""
    ui = """      </div>

      <h3 className=\"text-lg font-semibold text-gray-900 border-b pb-2 mt-6\">Endereço do Estudante</h3>
      <p className=\"text-xs text-gray-500 -mt-3\">Em novos cadastros, CEP, Município, UF e códigos IBGE são pré-preenchidos pela Unidade Mantenedora e permanecem editáveis.</p>
      <div className=\"grid grid-cols-1 md:grid-cols-6 gap-4\">
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">CEP</label><input type=\"text\" value={formatCEP(formData.address?.zip_code || '')} onChange={(e) => updateAddressData('zip_code', e.target.value)} onBlur={handleStudentAddressCEPBlur} disabled={viewMode} maxLength={9} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div className=\"md:col-span-3\"><label className=\"block text-sm font-medium text-gray-700 mb-1\">Logradouro</label><input type=\"text\" value={formData.address?.street || ''} onChange={(e) => updateAddressData('street', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">Número</label><input type=\"text\" value={formData.address?.number || ''} onChange={(e) => updateAddressData('number', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">Complemento</label><input type=\"text\" value={formData.address?.complement || ''} onChange={(e) => updateAddressData('complement', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div className=\"md:col-span-2\"><label className=\"block text-sm font-medium text-gray-700 mb-1\">Bairro</label><input type=\"text\" value={formData.address?.neighborhood || ''} onChange={(e) => updateAddressData('neighborhood', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div className=\"md:col-span-2\"><label className=\"block text-sm font-medium text-gray-700 mb-1\">Município</label><input type=\"text\" value={formData.address?.city || ''} onChange={(e) => updateAddressData('city', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">UF</label><select value={formData.address?.state || ''} onChange={(e) => updateAddressData('state', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\"><option value=\"\">UF</option>{STATES.map(state => (<option key={state} value={state}>{state}</option>))}</select></div>
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">Código IBGE da UF</label><input type=\"text\" inputMode=\"numeric\" maxLength={2} value={formData.address?.state_ibge_code || ''} onChange={(e) => updateAddressData('state_ibge_code', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
        <div><label className=\"block text-sm font-medium text-gray-700 mb-1\">Código IBGE do Município</label><input type=\"text\" inputMode=\"numeric\" maxLength={7} value={formData.address?.city_ibge_code || ''} onChange={(e) => updateAddressData('city_ibge_code', e.target.value)} disabled={viewMode} className=\"w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100\" /></div>
      </div>
    </div>
  );

  const tabDocumentos = (
"""
    if "Endereço do Estudante</h3>" not in text:
        text = once(text, anchor, ui, "student address UI")
    p.write_text(text, encoding="utf-8")


def main():
    patch_models()
    patch_router()
    patch_mantenedora_ui()
    patch_student_ui()
    print("Alinhamento territorial aplicado")


if __name__ == "__main__":
    main()
