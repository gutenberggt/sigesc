import { useEffect, useState } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, getDoc, doc, query, where } from 'firebase/firestore';

export function useNotasData(filters) {
  const [schools, setSchools] = useState([]);
  const [turmas, setTurmas] = useState([]);
  const [alunos, setAlunos] = useState([]);
  const [notas, setNotas] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getDocs(collection(db, 'schools')).then(snap => {
      setSchools(snap.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    });
  }, []);

  useEffect(() => {
    if (!filters.selectedSchoolId) return;
    const q = query(collection(db, 'turmas'), where('schoolId', '==', filters.selectedSchoolId));
    getDocs(q).then(snap => {
      setTurmas(snap.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    });
  }, [filters.selectedSchoolId]);

  useEffect(() => {
    const fetchData = async () => {
      if (!filters.selectedTurmaId || !filters.selectedYear) return;
      setLoading(true);
      setError('');

      try {
        const alunosSnap = await getDocs(
          query(collection(db, 'matriculas'), where('turmaId', '==', filters.selectedTurmaId))
        );

        const alunosCompletos = await Promise.all(
          alunosSnap.docs.map(async docu => {
            const matricula = { id: docu.id, ...docu.data() };
            const pessoaRef = doc(db, 'pessoas', matricula.pessoaId);
            const pessoaSnap = await getDoc(pessoaRef);
            const pessoaData = pessoaSnap.exists() ? pessoaSnap.data() : {};
            return {
              ...matricula,
              pessoaId: matricula.pessoaId,
              nomeCompleto: pessoaData.nomeCompleto || '—',
              numeroChamada: matricula.numeroChamada || 0
            };
          })
        );

        alunosCompletos.sort((a, b) => a.numeroChamada - b.numeroChamada);
        setAlunos(alunosCompletos);

        let notasQuery = query(
          collection(db, 'notas'),
          where('turmaId', '==', filters.selectedTurmaId),
          where('ano', '==', Number(filters.selectedYear))
        );

        if (filters.selectedComponenteId) {
          notasQuery = query(
            collection(db, 'notas'),
            where('turmaId', '==', filters.selectedTurmaId),
            where('ano', '==', Number(filters.selectedYear)),
            where('componenteId', '==', filters.selectedComponenteId)
          );
        }

        const notasSnap = await getDocs(notasQuery);
        const notasMap = {};

        notasSnap.docs.forEach(docu => {
          const d = docu.data();
          const chave = d.pessoaId || d.alunoId;
          if (chave) notasMap[chave] = d;
        });

        if (Object.keys(notasMap).length === 0) {
          const vazio = {};
          alunosCompletos.forEach(a => {
            vazio[a.pessoaId] = { b1: '', b2: '', r1: '', b3: '', b4: '', r2: '' };
          });
          setNotas(vazio);
        } else {
          setNotas(notasMap);
        }
      } catch (err) {
        console.error(err);
        setError('Erro ao carregar alunos ou notas');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [filters.selectedTurmaId, filters.selectedYear, filters.selectedComponenteId]);

  return { schools, turmas, alunos, notas, setNotas, loading, error };
}
