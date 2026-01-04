/**
 * Hook para gestão de escolas
 * Separado de SchoolsComplete.js para melhor organização
 */
import { useState, useEffect, useCallback } from 'react';
import { schoolsAPI, classesAPI, calendarAPI } from '@/services/api';

export function useSchools(initialYear = new Date().getFullYear()) {
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [calendarioLetivo, setCalendarioLetivo] = useState(null);
  const [selectedYear, setSelectedYear] = useState(initialYear);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadTrigger, setReloadTrigger] = useState(0);

  // Anos disponíveis para seleção (2025 a 2030)
  const anosDisponiveis = [2025, 2026, 2027, 2028, 2029, 2030];

  // Fetch data
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const [schoolsData, classesData, calendarioData] = await Promise.all([
          schoolsAPI.list(),
          classesAPI.list(),
          calendarAPI.get(selectedYear)
        ]);
        
        if (!cancelled) {
          setSchools(schoolsData || []);
          setClasses(classesData || []);
          setCalendarioLetivo(calendarioData);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Erro ao carregar dados:', err);
          setError(err.message || 'Erro ao carregar dados');
          // Fallback para arrays vazios
          setSchools([]);
          setClasses([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [reloadTrigger, selectedYear]);

  // Reload data
  const reloadData = useCallback(() => {
    setReloadTrigger(prev => prev + 1);
  }, []);

  // Create school
  const createSchool = useCallback(async (schoolData) => {
    const newSchool = await schoolsAPI.create(schoolData);
    reloadData();
    return newSchool;
  }, [reloadData]);

  // Update school
  const updateSchool = useCallback(async (schoolId, schoolData) => {
    const updated = await schoolsAPI.update(schoolId, schoolData);
    reloadData();
    return updated;
  }, [reloadData]);

  // Delete school
  const deleteSchool = useCallback(async (schoolId) => {
    await schoolsAPI.delete(schoolId);
    reloadData();
  }, [reloadData]);

  // Get classes by school
  const getClassesBySchool = useCallback((schoolId) => {
    return classes.filter(c => c.school_id === schoolId);
  }, [classes]);

  // Get school by ID
  const getSchoolById = useCallback((schoolId) => {
    return schools.find(s => s.id === schoolId);
  }, [schools]);

  return {
    // State
    schools,
    classes,
    calendarioLetivo,
    selectedYear,
    loading,
    error,
    anosDisponiveis,
    
    // Actions
    setSelectedYear,
    reloadData,
    createSchool,
    updateSchool,
    deleteSchool,
    
    // Helpers
    getClassesBySchool,
    getSchoolById
  };
}

export default useSchools;
