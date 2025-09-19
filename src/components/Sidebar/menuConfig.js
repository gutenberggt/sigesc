import {
  FaHome,
  FaCogs,
  FaCalendarAlt,
  FaSchool,
  FaBookOpen,
  FaChartBar,
} from "react-icons/fa";

export const menus = [
  {
    key: "inicio",
    label: "Início",
    icon: FaHome,
    to: "/dashboard",
    roles: [
      "administrador",
      "secretario",
      "professor",
      "diretor",
      "coordenador",
      "aluno",
    ],
  },
  {
    key: "administrativo",
    label: "Administrativo",
    icon: FaCogs,
    roles: ["administrador"],
    children: [
      { label: "Pessoas", to: "/dashboard/escola/pessoas" },
      { label: "Servidores", to: "/dashboard/escola/servidores/busca" },
      { label: "Usuários", to: "/dashboard/gerenciar-usuarios" },
    ],
  },
  {
    key: "calendario",
    label: "Calendário",
    icon: FaCalendarAlt,
    roles: ["administrador", "secretario"],
    children: [
      { label: "Calendário Letivo", to: "/dashboard/calendario/calendario" },
      { label: "Bimestres", to: "/dashboard/calendario/bimestres" },
      { label: "Eventos", to: "/dashboard/calendario/eventos" },
      { label: "Horário de Aulas", to: "/dashboard/calendario/horario" },
    ],
  },
  {
    key: "escola",
    label: "Escola",
    icon: FaSchool,
    roles: [
      "administrador",
      "secretario",
      "diretor",
      "coordenador",
      "professor",
    ],
    children: [
      {
        label: "Escola",
        to: "/dashboard/escola/escola",
        roles: ["administrador", "secretario"],
      },
      {
        label: "Matrícula de Aluno",
        to: "/dashboard/escola/matriculas",
        roles: ["administrador", "secretario"],
      },
      { label: "Busca de Aluno", to: "/dashboard/escola/busca-aluno" },
      {
        label: "Níveis de Ensino",
        to: "/dashboard/escola/cursos",
        roles: [
          "administrador",
          "secretario",
          "diretor",
          "coordenador",
          "professor",
        ],
      },
      {
        label: "Séries/Anos/Etapas",
        to: "/dashboard/escola/series",
        roles: [
          "administrador",
          "secretario",
          "diretor",
          "coordenador",
          "professor",
        ],
      },
      {
        label: "Componentes Curriculares",
        to: "/dashboard/escola/componentes-curriculares",
        roles: [
          "administrador",
          "secretario",
          "diretor",
          "coordenador",
          "professor",
        ],
      },
    ],
  },
  {
    key: "diario",
    label: "Diário",
    icon: FaBookOpen,
    roles: ["administrador", "secretario", "professor"],
    children: [
      { label: "Frequência", to: "/dashboard/diario/frequencia" },
      { label: "Conteúdos", to: "/dashboard/diario/conteudos" },
      { label: "Notas", to: "/dashboard/diario/notas" },
    ],
  },
  {
    key: "relatorios",
    label: "Relatórios e Declarações",
    icon: FaChartBar,
    roles: ["administrador", "secretario"],
    children: [{ label: "Gerar Relatório", to: "/dashboard/relatorios" }],
  },
];
