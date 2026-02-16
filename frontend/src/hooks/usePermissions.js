import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { authAPI } from '@/services/api';

/**
 * Hook para gerenciar permissões do usuário
 * 
 * Permissões do Coordenador:
 * - Pode VISUALIZAR tudo da escola onde é lotado
 * - Pode EDITAR apenas: notas, frequência e conteúdos (diário)
 * - NÃO pode editar: alunos, turmas, matrículas, servidores
 */
export const usePermissions = () => {
  const { user } = useAuth();
  const [permissions, setPermissions] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadPermissions = async () => {
      if (!user) {
        setPermissions(null);
        setLoading(false);
        return;
      }

      try {
        const perms = await authAPI.getPermissions();
        setPermissions(perms);
      } catch (error) {
        console.error('Erro ao carregar permissões:', error);
        // Fallback para permissões básicas baseadas no role
        setPermissions(getDefaultPermissions(user.role));
      } finally {
        setLoading(false);
      }
    };

    loadPermissions();
  }, [user]);

  /**
   * Verifica se o usuário pode editar um recurso específico
   */
  const canEdit = useCallback((resource) => {
    if (!permissions || !user) return false;

    // Admin pode tudo
    if (user.role === 'admin') return true;

    // Mapeamento de recursos para permissões
    const resourceMap = {
      'students': permissions.can_edit_students,
      'classes': permissions.can_edit_classes,
      'enrollments': permissions.can_edit_enrollments,
      'staff': permissions.can_edit_staff,
      'grades': permissions.can_edit_grades,
      'attendance': permissions.can_edit_attendance,
      'learning_objects': permissions.can_edit_learning_objects,
      'conteudo': permissions.can_edit_learning_objects
    };

    return resourceMap[resource] ?? false;
  }, [permissions, user]);

  /**
   * Verifica se o usuário pode visualizar um recurso
   */
  const canView = useCallback((resource) => {
    if (!user) return false;
    
    // Todos os usuários logados podem visualizar dados da sua escola
    return true;
  }, [user]);

  /**
   * Verifica se o usuário é coordenador (tem restrições de edição)
   */
  const isCoordinator = useCallback(() => {
    return user?.role === 'coordenador';
  }, [user]);

  /**
   * Verifica se o usuário tem acesso de somente leitura (exceto diário)
   */
  const isReadOnlyExceptDiary = useCallback(() => {
    return permissions?.is_read_only_except_diary ?? false;
  }, [permissions]);

  /**
   * Retorna as school_ids do usuário
   */
  const getUserSchoolIds = useCallback(() => {
    return permissions?.school_ids ?? [];
  }, [permissions]);

  return {
    permissions,
    loading,
    canEdit,
    canView,
    isCoordinator,
    isReadOnlyExceptDiary,
    getUserSchoolIds
  };
};

/**
 * Permissões padrão baseadas no role (fallback)
 */
function getDefaultPermissions(role) {
  const defaults = {
    admin: {
      role: 'admin',
      can_edit_grades: true,
      can_edit_attendance: true,
      can_edit_learning_objects: true,
      can_edit_students: true,
      can_edit_classes: true,
      can_edit_staff: true,
      can_edit_enrollments: true,
      can_view_all_school_data: true,
      is_read_only_except_diary: false,
      school_ids: []
    },
    secretario: {
      role: 'secretario',
      can_edit_grades: true,
      can_edit_attendance: true,
      can_edit_learning_objects: true,
      can_edit_students: true,
      can_edit_classes: true,
      can_edit_staff: true,
      can_edit_enrollments: true,
      can_view_all_school_data: true,
      is_read_only_except_diary: false,
      school_ids: []
    },
    diretor: {
      role: 'diretor',
      can_edit_grades: true,
      can_edit_attendance: true,
      can_edit_learning_objects: true,
      can_edit_students: true,
      can_edit_classes: true,
      can_edit_staff: true,
      can_edit_enrollments: true,
      can_view_all_school_data: true,
      is_read_only_except_diary: false,
      school_ids: []
    },
    coordenador: {
      role: 'coordenador',
      can_edit_grades: false,
      can_edit_attendance: false,
      can_edit_learning_objects: false,
      can_edit_students: false,
      can_edit_classes: false,
      can_edit_staff: false,
      can_edit_enrollments: false,
      can_view_all_school_data: true,
      is_read_only_except_diary: true,
      school_ids: []
    },
    professor: {
      role: 'professor',
      can_edit_grades: true,
      can_edit_attendance: true,
      can_edit_learning_objects: true,
      can_edit_students: false,
      can_edit_classes: false,
      can_edit_staff: false,
      can_edit_enrollments: false,
      can_view_all_school_data: false,
      is_read_only_except_diary: true,
      school_ids: []
    }
  };

  return defaults[role] || defaults.professor;
}

export default usePermissions;
