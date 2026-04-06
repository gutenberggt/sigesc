/**
 * Hook centralizado de permissões do SIGESC.
 * 
 * Papéis:
 * - admin/admin_teste: Acesso total
 * - secretario: Acesso total à escola vinculada
 * - diretor: Visualização + aprovações na escola vinculada
 * - coordenador/apoio_pedagogico/auxiliar_secretaria: Visualização (somente leitura)
 * - professor: Edita apenas notas, frequência e conteúdos das suas turmas
 * - semed/semed1/semed2/semed3: SEMED com níveis de acesso crescente
 * - ass_social: Serviço social
 */
import { useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';

export const usePermissions = () => {
  const { user } = useAuth();

  return useMemo(() => {
    const role = (user?.role || '').toLowerCase();

    // ===== Checks de role =====
    const isAdmin = role === 'admin' || role === 'admin_teste';
    const isSecretario = role === 'secretario';
    const isDiretor = role === 'diretor';
    const isCoordenador = role === 'coordenador' || role === 'apoio_pedagogico' || role === 'auxiliar_secretaria';
    const isProfessor = role === 'professor';
    const isSemed = ['semed', 'semed1', 'semed2', 'semed3'].includes(role);
    const isSemedFull = role === 'semed3';
    const isAssistenteSocial = role === 'ass_social';

    // ===== Grupos =====
    const isSchoolStaff = isSecretario || isDiretor || isCoordenador;
    const isGlobal = isAdmin || isSemed;
    const isAdminOrSecretary = isAdmin || isSecretario;

    // ===== Permissões por recurso =====
    const canEditAttendance = isAdmin || isSecretario || isProfessor;
    const canEditGrades = !isSemed && !isCoordenador;
    const canEditLearningObjects = isAdmin || isSecretario || isDiretor || isProfessor;
    const canEditEvents = isAdminOrSecretary;
    const canEditEnrollments = !isSemed;
    const canDeleteEnrollments = !isSemed;
    const canDeleteStudents = isAdmin;
    const canEditStudents = !isSemed && !isCoordenador;
    const canRegisterCertificates = isAdminOrSecretary;
    const canDeleteCertificates = isAdminOrSecretary;
    const canConfigSettings = isAdminOrSecretary;

    // Escola do usuário
    const userSchoolIds = user?.school_ids || [];

    /** Verifica se o role está na lista fornecida */
    const hasRole = (...roles) => roles.includes(role);

    /** Verifica se o usuário está lotado na escola */
    const isLinkedToSchool = (schoolId) => isAdmin || userSchoolIds.includes(schoolId);

    /** Verifica permissão genérica por recurso */
    const canEdit = (resource) => {
      if (isAdmin) return true;
      const map = {
        students: canEditStudents,
        classes: isAdminOrSecretary,
        enrollments: canEditEnrollments,
        staff: isAdminOrSecretary,
        grades: canEditGrades,
        attendance: canEditAttendance,
        learning_objects: canEditLearningObjects,
        conteudo: canEditLearningObjects,
        events: canEditEvents,
      };
      return map[resource] ?? false;
    };

    return {
      // Role
      role,
      isAdmin,
      isSecretario,
      isDiretor,
      isCoordenador,
      isProfessor,
      isSemed,
      isSemedFull,
      isAssistenteSocial,
      isSchoolStaff,
      isGlobal,
      isAdminOrSecretary,

      // Permissões
      canEditAttendance,
      canEditGrades,
      canEditLearningObjects,
      canEditEvents,
      canEditEnrollments,
      canDeleteEnrollments,
      canDeleteStudents,
      canEditStudents,
      canRegisterCertificates,
      canDeleteCertificates,
      canConfigSettings,

      // Utilitários
      userSchoolIds,
      hasRole,
      isLinkedToSchool,
      canEdit,
    };
  }, [user?.role, user?.school_ids]);
};

export default usePermissions;
