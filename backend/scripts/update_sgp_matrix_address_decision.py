from pathlib import Path

path = Path(__file__).resolve().parents[2] / "memory/audit/SGP_STUDENT_CANONICAL_MAPPING.md"
text = path.read_text(encoding="utf-8")
old = "O formulário poderá oferecer **“Copiar endereço do responsável principal”**, mas o endereço efetivamente salvo no estudante será a fonte da verdade. Não haverá sincronização automática permanente entre os dois cadastros."
new = "Nos novos cadastros, **CEP, Município, UF e códigos IBGE de UF/município são pré-preenchidos a partir da Unidade Mantenedora**. Esses valores formam apenas uma cópia inicial: permanecem editáveis no cadastro do estudante e não existe sincronização automática posterior. Os demais componentes do endereço pertencem exclusivamente ao estudante."
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("Parágrafo de decisão territorial não encontrado")

anchor = "Os códigos IBGE de UF e município serão armazenados de forma explícita para evitar inferências por texto livre na integração."
addition = anchor + " A Unidade Mantenedora passa a manter `codigo_ibge_uf` e `codigo_ibge_municipio`, usados como defaults territoriais do novo estudante."
if addition not in text:
    if anchor not in text:
        raise RuntimeError("Âncora de códigos IBGE não encontrada")
    text = text.replace(anchor, addition, 1)

path.write_text(text, encoding="utf-8")
print("Matriz territorial atualizada")
