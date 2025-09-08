import React, { useEffect, useState } from "react"
import {
  collection,
  addDoc,
  updateDoc,
  deleteDoc,
  doc,
  getDocs,
} from "firebase/firestore"
import { db } from "../firebase/config"
import { componentesData } from "../pages/ComponentesPage"

export default function TurmasPage() {
  const [turmas, setTurmas] = useState([])
  const [nomeTurma, setNomeTurma] = useState("")
  const [nivelEnsino, setNivelEnsino] = useState("")
  const [anoSerie, setAnoSerie] = useState("")
  const [turno, setTurno] = useState("")
  const [anoLetivo, setAnoLetivo] = useState("")
  const [professoresIds, setProfessoresIds] = useState([])
  const [limiteVagas, setLimiteVagas] = useState("")
  const [salaAula, setSalaAula] = useState("")
  const [componentesSelecionados, setComponentesSelecionados] = useState([])

  const [editingTurma, setEditingTurma] = useState(null)
  const [isSaving, setIsSaving] = useState(false)

  // 🔎 Buscar turmas no Firestore
  useEffect(() => {
    const fetchTurmas = async () => {
      const querySnapshot = await getDocs(collection(db, "turmas"))
      const lista = querySnapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }))
      setTurmas(lista)
    }
    fetchTurmas()
  }, [])

  // ✅ Alternar seleção de componentes
  const toggleComponente = (nome) => {
    setComponentesSelecionados((prev) =>
      prev.includes(nome)
        ? prev.filter((c) => c !== nome)
        : [...prev, nome]
    )
  }

  // 💾 Salvar turma
  const handleSave = async () => {
    if (!nomeTurma || !nivelEnsino || !anoSerie || !turno || !anoLetivo) {
      alert("Preencha todos os campos obrigatórios.")
      return
    }

    setIsSaving(true)

    try {
      const componentesDaSerie = componentesData[anoSerie] || []

      const turmaData = {
        nomeTurma,
        nivelEnsino,
        anoSerie,
        turno,
        anoLetivo,
        professoresIds,
        limiteVagas,
        salaAula,
        componentes: componentesDaSerie.filter((c) =>
          componentesSelecionados.includes(c.nome)
        ),
      }

      if (editingTurma) {
        const docRef = doc(db, "turmas", editingTurma.id)
        await updateDoc(docRef, turmaData)
        setTurmas(
          turmas.map((t) =>
            t.id === editingTurma.id ? { ...t, ...turmaData } : t
          )
        )
      } else {
        const docRef = await addDoc(collection(db, "turmas"), turmaData)
        setTurmas([...turmas, { id: docRef.id, ...turmaData }])
      }

      resetForm()
    } catch (err) {
      console.error("Erro ao salvar turma:", err)
      alert("Não foi possível salvar a turma.")
    } finally {
      setIsSaving(false)
    }
  }

  // 🗑️ Excluir turma
  const handleDelete = async (id) => {
    if (!window.confirm("Tem certeza que deseja excluir esta turma?")) return
    try {
      await deleteDoc(doc(db, "turmas", id))
      setTurmas(turmas.filter((t) => t.id !== id))
    } catch (err) {
      console.error("Erro ao excluir turma:", err)
      alert("Não foi possível excluir a turma.")
    }
  }

  // ✏️ Editar turma
  const handleEdit = (turma) => {
    setEditingTurma(turma)
    setNomeTurma(turma.nomeTurma)
    setNivelEnsino(turma.nivelEnsino)
    setAnoSerie(turma.anoSerie)
    setTurno(turma.turno)
    setAnoLetivo(turma.anoLetivo)
    setProfessoresIds(turma.professoresIds || [])
    setLimiteVagas(turma.limiteVagas || "")
    setSalaAula(turma.salaAula || "")
    setComponentesSelecionados(
      (turma.componentes || []).map((c) => c.nome)
    )
  }

  // 🔄 Resetar form
  const resetForm = () => {
    setEditingTurma(null)
    setNomeTurma("")
    setNivelEnsino("")
    setAnoSerie("")
    setTurno("")
    setAnoLetivo("")
    setProfessoresIds([])
    setLimiteVagas("")
    setSalaAula("")
    setComponentesSelecionados([])
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-4">Gerenciar Turmas</h1>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <label className="block font-medium mb-1">Nome da Turma</label>
          <input
            value={nomeTurma}
            onChange={(e) => setNomeTurma(e.target.value)}
            className="w-full border p-2 rounded"
          />
        </div>

        <div>
          <label className="block font-medium mb-1">Nível de Ensino</label>
          <select
            value={nivelEnsino}
            onChange={(e) => setNivelEnsino(e.target.value)}
            className="w-full border p-2 rounded"
          >
            <option value="">Selecione</option>
            <option value="ENSINO FUNDAMENTAL - ANOS INICIAIS">
              Ensino Fundamental - Anos Iniciais
            </option>
            <option value="ENSINO FUNDAMENTAL - ANOS FINAIS">
              Ensino Fundamental - Anos Finais
            </option>
            <option value="ENSINO MÉDIO">Ensino Médio</option>
            <option value="EDUCAÇÃO INFANTIL">Educação Infantil</option>
            <option value="EJA">Educação de Jovens e Adultos</option>
          </select>
        </div>

        <div>
          <label className="block font-medium mb-1">Ano/Série</label>
          <select
            value={anoSerie}
            onChange={(e) => {
              setAnoSerie(e.target.value)
              setComponentesSelecionados([])
            }}
            className="w-full border p-2 rounded"
          >
            <option value="">Selecione</option>
            {Object.keys(componentesData).map((serie) => (
              <option key={serie} value={serie}>
                {serie}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block font-medium mb-1">Turno</label>
          <select
            value={turno}
            onChange={(e) => setTurno(e.target.value)}
            className="w-full border p-2 rounded"
          >
            <option value="">Selecione</option>
            <option value="MATUTINO">Matutino</option>
            <option value="VESPERTINO">Vespertino</option>
            <option value="NOTURNO">Noturno</option>
          </select>
        </div>

        <div>
          <label className="block font-medium mb-1">Ano Letivo</label>
          <input
            value={anoLetivo}
            onChange={(e) => setAnoLetivo(e.target.value)}
            className="w-full border p-2 rounded"
          />
        </div>

        <div>
          <label className="block font-medium mb-1">Sala de Aula</label>
          <input
            value={salaAula}
            onChange={(e) => setSalaAula(e.target.value)}
            className="w-full border p-2 rounded"
          />
        </div>

        <div>
          <label className="block font-medium mb-1">Limite de Vagas</label>
          <input
            type="number"
            value={limiteVagas}
            onChange={(e) => setLimiteVagas(e.target.value)}
            className="w-full border p-2 rounded"
          />
        </div>
      </div>

      {/* ✅ Seleção de componentes curriculares */}
      {anoSerie && (
        <div className="mb-6">
          <label className="block font-medium mb-2">
            Componentes Curriculares ({anoSerie})
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {(componentesData[anoSerie] || []).map((comp) => (
              <label key={comp.nome} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={componentesSelecionados.includes(comp.nome)}
                  onChange={() => toggleComponente(comp.nome)}
                />
                {comp.nome}
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-6">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {isSaving ? "Salvando..." : editingTurma ? "Atualizar" : "Adicionar"}
        </button>
        {editingTurma && (
          <button
            onClick={resetForm}
            className="bg-gray-400 text-white px-4 py-2 rounded hover:bg-gray-500"
          >
            Cancelar
          </button>
        )}
      </div>
	  
	  {/* ✅ Seleção de componentes curriculares */}
      {anoSerie && (
        <div className="mb-6">
          <label className="block font-medium mb-2">
            Componentes Curriculares ({anoSerie})
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {(componentesData[anoSerie] || []).map((comp) => (
              <label key={comp.nome} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={componentesSelecionados.includes(comp.nome)}
                  onChange={() => toggleComponente(comp.nome)}
                />
                {comp.nome}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Lista de turmas */}
      <table className="w-full border">
        <thead>
          <tr className="bg-gray-100">
            <th className="border p-2">Nome</th>
            <th className="border p-2">Nível</th>
            <th className="border p-2">Ano/Série</th>
            <th className="border p-2">Turno</th>
            <th className="border p-2">Ano Letivo</th>
            <th className="border p-2">Componentes</th>
            <th className="border p-2">Ações</th>
          </tr>
        </thead>
        <tbody>
          {turmas.map((turma) => (
            <tr key={turma.id}>
              <td className="border p-2">{turma.nomeTurma}</td>
              <td className="border p-2">{turma.nivelEnsino}</td>
              <td className="border p-2">{turma.anoSerie}</td>
              <td className="border p-2">{turma.turno}</td>
              <td className="border p-2">{turma.anoLetivo}</td>
              <td className="border p-2">
                {(turma.componentes || []).map((c) => c.nome).join(", ")}
              </td>
              <td className="border p-2 flex gap-2">
                <button
                  onClick={() => handleEdit(turma)}
                  className="bg-yellow-500 text-white px-2 py-1 rounded hover:bg-yellow-600"
                >
                  Editar
                </button>
                <button
                  onClick={() => handleDelete(turma.id)}
                  className="bg-red-600 text-white px-2 py-1 rounded hover:bg-red-700"
                >
                  Excluir
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}