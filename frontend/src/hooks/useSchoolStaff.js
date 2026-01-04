/**
 * Hook para gestão de staff (servidores) da escola
 * Separado para melhor organização do código
 */
import { useState, useCallback } from 'react';
import { schoolAssignmentAPI, staffAPI } from '@/services/api';

export function useSchoolStaff() {
  const [schoolStaff, setSchoolStaff] = useState([]);
  const [loadingStaff, setLoadingStaff] = useState(false);
  const [error, setError] = useState(null);

  // Load staff for a specific school
  const loadSchoolStaff = useCallback(async (schoolId) => {
    if (!schoolId) {
      setSchoolStaff([]);
      return;
    }

    setLoadingStaff(true);
    setError(null);

    try {
      const assignments = await schoolAssignmentAPI.list({ 
        school_id: schoolId, 
        status: 'ativo' 
      });
      
      // Fetch details for each staff member
      const staffDetails = await Promise.all(
        (assignments || []).map(async (assignment) => {
          try {
            const staff = await staffAPI.get(assignment.staff_id);
            return {
              ...staff,
              funcao: assignment.funcao,
              carga_horaria: assignment.carga_horaria,
              assignment_id: assignment.id
            };
          } catch (err) {
            console.error(`Erro ao buscar servidor ${assignment.staff_id}:`, err);
            return null;
          }
        })
      );
      
      // Filter out failed fetches
      setSchoolStaff(staffDetails.filter(Boolean));
    } catch (err) {
      console.error('Erro ao carregar servidores:', err);
      setError(err.message || 'Erro ao carregar servidores');
      setSchoolStaff([]);
    } finally {
      setLoadingStaff(false);
    }
  }, []);

  // Clear staff list
  const clearStaff = useCallback(() => {
    setSchoolStaff([]);
    setError(null);
  }, []);

  return {
    schoolStaff,
    loadingStaff,
    error,
    loadSchoolStaff,
    clearStaff
  };
}

export default useSchoolStaff;
