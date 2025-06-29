// src/components/Layout.js
import React from 'react';

const Layout = ({ children }) => {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-blue-800 text-white p-4 shadow">
        <div className="text-xl font-bold">SIGESC</div>
      </header>
      <main className="flex-1 p-6">{children}</main>
      <footer className="bg-gray-200 text-center py-2 text-sm text-gray-600">
        &copy; {new Date().getFullYear()} SIGESC - Todos os direitos reservados
      </footer>
    </div>
  );
};

export default Layout;


// src/components/StatsPanel.js
import React, { useEffect, useState } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs } from 'firebase/firestore';

const StatsPanel = () => {
  const [stats, setStats] = useState({ users: 0, schools: 0, classes: 0 });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const usersSnap = await getDocs(collection(db, 'users'));
        const schoolsSnap = await getDocs(collection(db, 'schools'));
        const classesSnap = await getDocs(collection(db, 'classes'));

        setStats({
          users: usersSnap.size,
          schools: schoolsSnap.size,
          classes: classesSnap.size,
        });
      } catch (error) {
        console.error('Erro ao buscar estatísticas:', error);
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


// src/components/PrivateRoute.js
import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthState } from 'react-firebase-hooks/auth';
import { auth, db } from '../firebase/config';
import { doc, getDoc } from 'firebase/firestore';

const LoadingScreen = () => (
  <div className="h-screen flex items-center justify-center bg-white">
    <div className="text-gray-600 text-lg">Carregando...</div>
  </div>
);

const PrivateRoute = ({ children, allowedRoles }) => {
  const [user, loading] = useAuthState(auth);
  const [roleAllowed, setRoleAllowed] = useState(null);

  useEffect(() => {
    const checkRole = async () => {
      if (user) {
        const profileRef = doc(db, 'users', user.uid);
        const profileSnap = await getDoc(profileRef);
        const role = profileSnap.data()?.role;
        setRoleAllowed(allowedRoles.includes(role));
      }
    };
    if (user) checkRole();
  }, [user, allowedRoles]);

  if (loading || (user && roleAllowed === null)) return <LoadingScreen />;
  if (!user || roleAllowed === false) return <Navigate to="/login" />;

  return children;
};

export default PrivateRoute;


// src/pages/DashboardPage.js
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { auth, db } from '../firebase/config';
import { signOut } from 'firebase/auth';
import { doc, getDoc } from 'firebase/firestore';
import { FiHome, FiUsers, FiSettings, FiLogOut, FiBookOpen } from 'react-icons/fi';
import Layout from '../components/Layout';
import StatsPanel from '../components/StatsPanel';

const DashboardPage = () => {
  const [userData, setUserData] = useState(null);

  useEffect(() => {
    const fetchUserData = async () => {
      const currentUser = auth.currentUser;
      if (currentUser) {
        const userDoc = await getDoc(doc(db, 'users', currentUser.uid));
        if (userDoc.exists()) {
          setUserData(userDoc.data());
        }
      }
    };
    fetchUserData();
  }, []);

  const handleLogout = async () => {
    await signOut(auth);
    window.location.href = '/';
  };

  return (
    <Layout>
      <div className="flex">
        <aside className="w-64 bg-blue-800 text-white flex flex-col p-6 min-h-screen">
          <div className="mb-10">
            <h1 className="text-2xl font-bold">SIGESC</h1>
            <p className="text-sm">Sistema Integrado de Gestão Escolar</p>
          </div>

          <nav className="flex flex-col gap-4 text-base">
            <Link to="/dashboard" className="flex items-center gap-2 hover:text-blue-300">
              <FiHome /> Início
            </Link>
            <Link to="/usuarios" className="flex items-center gap-2 hover:text-blue-300">
              <FiUsers /> Usuários
            </Link>
            <Link to="/escolas" className="flex items-center gap-2 hover:text-blue-300">
              <FiBookOpen /> Escolas
            </Link>
            <Link to="/configuracoes" className="flex items-center gap-2 hover:text-blue-300">
              <FiSettings /> Configurações
            </Link>
          </nav>

          <button
            onClick={handleLogout}
            className="mt-auto bg-red-600 hover:bg-red-700 text-white p-2 rounded mt-10 flex items-center gap-2"
          >
            <FiLogOut /> Sair
          </button>
        </aside>

        <main className="flex-1 p-8">
          <header className="mb-6">
            <h2 className="text-3xl font-bold text-gray-800">
              Bem-vindo(a){userData?.nome ? `, ${userData.nome}` : ''}!
            </h2>
            <p className="text-gray-600">Painel principal do sistema</p>
          </header>

          <StatsPanel />
        </main>
      </div>
    </Layout>
  );
};

export default DashboardPage;
