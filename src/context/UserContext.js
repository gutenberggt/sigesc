import React, { createContext, useState, useEffect, useContext } from 'react';
import { auth, db } from '../firebase/config'; //
import { onAuthStateChanged } from 'firebase/auth';
import { doc, getDoc } from 'firebase/firestore';

export const UserContext = createContext(null);

export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribeAuth = onAuthStateChanged(auth, async (currentUser) => {
      if (currentUser) {
        setUser(currentUser);
        try {
          const userDocRef = doc(db, 'users', currentUser.uid);
          const userDocSnap = await getDoc(userDocRef);

          if (userDocSnap.exists()) {
            setUserData(userDocSnap.data());
          } else {
            console.warn('Documento do usuário não encontrado no Firestore.');
            setUserData(null);
          }
        } catch (error) {
          console.error('Erro ao buscar dados do usuário no Firestore:', error);
          setUserData(null);
        }
      } else {
        setUser(null);
        setUserData(null);
      }
      setLoading(false);
    });

    return () => unsubscribeAuth();
  }, []);

  // Corrija esta linha: adicione 'loading' ao objeto de valor
  return (
    <UserContext.Provider value={{ user, userData, setUserData, loading }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => {
  return useContext(UserContext);
};