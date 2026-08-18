import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import { useDiaryPrefill } from '@/hooks/useDiaryPrefill';
import {
  fetchAttendanceDvdContext,
  fetchAttendanceDvdDiary,
  getAttendanceDvdLocation,
  setAttendanceDvdAulaNumero,
} from '@/services/attendanceDvdBridge';

export const AttendanceContext = createContext(null);

const errorMessage = (error) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return error?.message || 'Não foi possível carregar o vínculo de frequência.';
};

/**
 * Encaixa o modo DVD na tela já existente, sem criar uma página paralela.
 * O assignment_id vem exclusivamente da navegação de Meus Diários; o backend
 * continua sendo a autoridade de turma, componente, perfil, modo e natureza.
 */
const useDvdBinding = (baseContext) => {
  const { isOnline } = useOffline();
  const locationState = getAttendanceDvdLocation();
  const assignmentId = locationState.assignmentId;
  const [dvdDiary, setDvdDiary] = useState(null);
  const [dvdContext, setDvdContext] = useState(null);
  const [dvdError, setDvdError] = useState(null);
  const [dvdLoading, setDvdLoading] = useState(false);
  const [dvdSessionAula, setDvdSessionAulaState] = useState(locationState.aulaNumero);

  // Fluxo legado: os parâmetros do card apenas pré-selecionam opções que já
  // existem nas listas autorizadas da própria tela. No modo DVD, o vínculo
  // validado pelo backend continua sendo a fonte de verdade do contexto.
  useDiaryPrefill({
    schools: baseContext.schools,
    selectedSchool: baseContext.selectedSchool,
    setSelectedSchool: baseContext.setSelectedSchool,
    classes: baseContext.classes,
    selectedClass: baseContext.selectedClass,
    setSelectedClass: baseContext.setSelectedClass,
    courses: baseContext.courses,
    selectedCourse: baseContext.selectedCourse,
    setSelectedCourse: baseContext.setSelectedCourse,
    enabled: !assignmentId,
  });

  useEffect(() => {
    if (!assignmentId) {
      setDvdDiary(null);
      setDvdContext(null);
      setDvdError(null);
      return;
    }
    let active = true;
    const load = async () => {
      setDvdLoading(true);
      try {
        const diary = await fetchAttendanceDvdDiary(assignmentId, baseContext.academicYear);
        if (!active) return;
        if (!diary) {
          setDvdDiary(null);
          setDvdError('Este vínculo não está disponível em Meus Diários para o ano selecionado.');
          return;
        }
        setDvdDiary(diary);
        setDvdError(null);

        if (diary.academic_year && Number(diary.academic_year) !== Number(baseContext.academicYear)) {
          baseContext.setAcademicYear(Number(diary.academic_year));
        }
        if (diary.school_id && baseContext.selectedSchool !== diary.school_id) {
          baseContext.setSelectedSchool(diary.school_id);
        }
        if (diary.class_id && baseContext.selectedClass !== diary.class_id) {
          baseContext.setSelectedClass(diary.class_id);
        }
        if (diary.component_id && baseContext.selectedCourse !== diary.component_id) {
          baseContext.setSelectedCourse(diary.component_id);
        }
      } catch (error) {
        if (active) setDvdError(errorMessage(error));
      } finally {
        if (active) setDvdLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [
    assignmentId,
    baseContext.academicYear,
    baseContext.selectedSchool,
    baseContext.selectedClass,
    baseContext.selectedCourse,
    baseContext.setAcademicYear,
    baseContext.setSelectedSchool,
    baseContext.setSelectedClass,
    baseContext.setSelectedCourse,
  ]);

  useEffect(() => {
    if (!assignmentId || !baseContext.selectedDate || !isOnline) {
      setDvdContext(null);
      return;
    }
    let active = true;
    fetchAttendanceDvdContext(assignmentId, baseContext.selectedDate)
      .then((data) => {
        if (!active) return;
        setDvdContext(data);
        setDvdError(null);
        const slots = data?.session_slots || [];
        if (data?.attendance_mode === 'assignment_session' && slots.length === 1) {
          const only = slots[0]?.aula_numero ?? null;
          setDvdSessionAulaState(only);
          setAttendanceDvdAulaNumero(only);
        }
      })
      .catch((error) => {
        if (active) {
          setDvdContext(null);
          setDvdError(errorMessage(error));
        }
      });
    return () => { active = false; };
  }, [assignmentId, baseContext.selectedDate, isOnline]);

  const setDvdSessionAula = (value) => {
    const normalized = value === '' || value === null || value === undefined
      ? null
      : Number(value);
    setDvdSessionAulaState(normalized);
    setAttendanceDvdAulaNumero(normalized);
  };

  return useMemo(() => {
    if (!assignmentId) {
      return {
        ...baseContext,
        dvdMode: false,
        dvdAssignmentId: null,
        dvdDiary: null,
        dvdContext: null,
        dvdError: null,
        dvdLoading: false,
        dvdSessionAula: null,
        setDvdSessionAula,
        dvdOnline: isOnline,
      };
    }

    const pseudoClass = dvdDiary ? {
      id: dvdDiary.class_id,
      name: dvdDiary.class_name,
      school_id: dvdDiary.school_id,
      school_name: dvdDiary.school_name,
      academic_year: dvdDiary.academic_year || baseContext.academicYear,
      education_level: dvdDiary.education_level,
      grade_level: dvdDiary.grade_level,
      shift: dvdDiary.shift,
    } : null;
    const pseudoSchool = dvdDiary?.school_id ? [{
      id: dvdDiary.school_id,
      name: dvdDiary.school_name || 'Escola do vínculo',
    }] : baseContext.schools;
    const pseudoCourses = dvdDiary?.component_id ? [{
      id: dvdDiary.component_id,
      name: dvdDiary.component_name || 'Componente do vínculo',
    }] : [];

    return {
      ...baseContext,
      schools: pseudoSchool,
      classes: pseudoClass ? [pseudoClass] : baseContext.classes,
      courses: pseudoCourses,
      selectedClassData: pseudoClass || baseContext.selectedClassData,
      // DVD v1 não inclui Anos Finais; uma sessão do vínculo é lançada por vez.
      isMultiAula: false,
      canEdit: baseContext.canEdit && isOnline && !dvdError,
      dvdMode: true,
      dvdAssignmentId: assignmentId,
      dvdDiary,
      dvdContext,
      dvdError,
      dvdLoading,
      dvdSessionAula,
      setDvdSessionAula,
      dvdOnline: isOnline,
    };
  }, [
    assignmentId,
    baseContext,
    dvdDiary,
    dvdContext,
    dvdError,
    dvdLoading,
    dvdSessionAula,
    isOnline,
  ]);
};

export const useAttendance = () => {
  const ctx = useContext(AttendanceContext);
  if (!ctx) {
    throw new Error('useAttendance must be used inside <AttendanceContext.Provider>');
  }
  return useDvdBinding(ctx);
};
