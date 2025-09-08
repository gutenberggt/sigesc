import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext";

export function useAuthGuard(redirectTo = "/") {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !userData) {
      navigate(redirectTo);
    }
  }, [loading, userData, navigate, redirectTo]);

  return { userData, loading };
}
