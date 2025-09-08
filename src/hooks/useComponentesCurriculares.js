import { useEffect, useState } from "react";
import {
  collection,
  getDocs,
  query,
  where,
  doc,
  getDoc,
} from "firebase/firestore";
import { db } from "../firebase/config";

export function useComponentesCurriculares(
  filters,
  showComponenteFilter,
  funcao,
  userData
) {
  const [componentes, setComponentes] = useState([]);

  useEffect(() => {
    const { selectedTurmaId, selectedComponenteId } = filters;

    if (!selectedTurmaId) {
      setComponentes([]);
      return;
    }

    const buscarComponentes = async () => {
      try {
        const turmaRef = doc(db, "turmas", selectedTurmaId);
        const turmaSnap = await getDoc(turmaRef);
        const turma = turmaSnap.exists() ? turmaSnap.data() : null;

        if (!turma || !turma.nivelEnsino || !turma.anoSerie) {
          setComponentes([]);
          return;
        }

        const ref = collection(db, "componentes");
        const q = query(
          ref,
          where("nivelEnsino", "==", turma.nivelEnsino),
          where("serieAno", "==", turma.anoSerie)
        );

        const snapshot = await getDocs(q);
        const lista = snapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        if (showComponenteFilter && selectedComponenteId) {
          const filtrado = lista.filter(
            (comp) =>
              comp.id === selectedComponenteId ||
              comp.codigo === selectedComponenteId
          );
          setComponentes(filtrado);
        } else {
          setComponentes(lista);
        }
      } catch (error) {
        console.error("Erro ao buscar componentes curriculares:", error);
        setComponentes([]);
      }
    };

    buscarComponentes();
  }, [filters, showComponenteFilter]);

  return componentes;
}
