import { createContext, useState, useEffect } from "react";
import { getAuth, onAuthStateChanged } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { db, auth } from "../firebase/config";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [usuario, setUsuario] = useState(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    const auth = getAuth();
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        try {
          const docRef = doc(db, "users", user.uid);
          const docSnap = await getDoc(docRef);
          if (docSnap.exists()) {
            const dados = docSnap.data();
            if (dados.ativo) {
              setUsuario({ uid: user.uid, ...dados });
            } else {
              console.warn("Usuário inativo.");
              setUsuario(null);
            }
          } else {
            console.warn("Documento do usuário não encontrado.");
            setUsuario(null);
          }
        } catch (error) {
          console.error("Erro ao buscar dados do usuário:", error);
          setUsuario(null);
        }
      } else {
        setUsuario(null);
      }
      setCarregando(false);
    });

    return () => unsubscribe();
  }, []);

  return (
    <AuthContext.Provider value={{ usuario, carregando }}>
      {children}
    </AuthContext.Provider>
  );
};
