import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthState } from 'react-firebase-hooks/auth';
import { auth } from '../firebase/config';

function PrivateRoute({ children }) {
  const [user, loading] = useAuthState(auth);

  if (loading) return <div className="p-4 text-center">Carregando...</div>;
  if (!user) return <Navigate to="/login" />;

  return children;
}

export default PrivateRoute;
