// Configuração CENTRAL das categorias de conexão (Usuários Online).
// Espelha backend/utils/connection_categories.py (CONNECTION_CATEGORIES).
//
// ➜ As CHAVES (`key`) devem bater com as chaves de `by_category` retornadas
//   pelo backend (/api/admin/online-users/login-count).
// ➜ Para alterar rótulo, ícone ou cor de uma categoria, edite SOMENTE aqui.
//
// Obs.: as classes de cor são strings estáticas (não interpoladas) para que o
// Tailwind JIT as gere corretamente.
import { GraduationCap, BookOpen, HeartHandshake, Syringe, Shield } from 'lucide-react';

export const CONNECTION_CATEGORIES = [
  { key: 'professores', label: 'Professores', icon: GraduationCap, iconWrap: 'bg-yellow-50', iconColor: 'text-yellow-600', testId: 'conn-cat-professores' },
  { key: 'alunos', label: 'Alunos', icon: BookOpen, iconWrap: 'bg-indigo-50', iconColor: 'text-indigo-600', testId: 'conn-cat-alunos' },
  { key: 'assistencia_social', label: 'Assistência Social', icon: HeartHandshake, iconWrap: 'bg-pink-50', iconColor: 'text-pink-600', testId: 'conn-cat-assistencia' },
  { key: 'saude', label: 'Saúde', icon: Syringe, iconWrap: 'bg-teal-50', iconColor: 'text-teal-600', testId: 'conn-cat-saude' },
  { key: 'administrativas', label: 'Administrativas', icon: Shield, iconWrap: 'bg-blue-50', iconColor: 'text-blue-600', testId: 'conn-cat-administrativas' },
];
