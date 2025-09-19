import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuthState } from "react-firebase-hooks/auth";
import { auth, db } from "../firebase/config";
import { doc, getDoc } from "firebase/firestore";

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
        const profileRef = doc(db, "users", user.uid);
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
