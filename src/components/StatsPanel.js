import React, { useEffect, useState } from "react";
import { db } from "../firebase/config";
import { collection, getDocs } from "firebase/firestore";

const StatsPanel = () => {
  const [stats, setStats] = useState({ users: 0, schools: 0, classes: 0 });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const usersSnap = await getDocs(collection(db, "users"));
        const schoolsSnap = await getDocs(collection(db, "schools"));
        const classesSnap = await getDocs(collection(db, "classes"));

        setStats({
          users: usersSnap.size,
          schools: schoolsSnap.size,
          classes: classesSnap.size,
        });
      } catch (error) {
        console.error("Erro ao buscar estatísticas:", error);
      }
    };
    fetchData();
  }, []);

  return (
    <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div className="bg-white p-6 rounded shadow">
        <h3 className="text-xl font-semibold mb-2">Total de Usuários</h3>
        <p className="text-3xl font-bold text-blue-600">{stats.users}</p>
      </div>
      <div className="bg-white p-6 rounded shadow">
        <h3 className="text-xl font-semibold mb-2">Escolas Cadastradas</h3>
        <p className="text-3xl font-bold text-green-600">{stats.schools}</p>
      </div>
      <div className="bg-white p-6 rounded shadow">
        <h3 className="text-xl font-semibold mb-2">Turmas Ativas</h3>
        <p className="text-3xl font-bold text-purple-600">{stats.classes}</p>
      </div>
    </section>
  );
};

export default StatsPanel;
