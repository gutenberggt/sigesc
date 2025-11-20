Set-Content -Path "README.md" -Value @"
# SIGESC - Sistema Integrado de Gestão Escolar

SIGESC é uma aplicação web de gestão escolar construída em **React 18**, estilizada com **Tailwind CSS** e empacotada com **Vite**. O projeto utiliza **Firebase** para autenticação e persistência de dados, e pode ser facilmente hospedado em **Vercel**.

---

## 🏗️ Estrutura do Projeto

- **src/pages**: Páginas da aplicação (Dashboard, Login, etc.)
- **src/components**: Componentes React reutilizáveis
- **src/context**: Contextos (ex.: UserContext, ThemeContext)
- **src/firebase**: Configuração do Firebase e serviços
- **src/services**: Serviços para consumir Firestore
- **src/assets**: Imagens, ícones e outros recursos estáticos

---

## 🚀 Tecnologias

- React 18
- Vite
- Tailwind CSS
- Firebase (Auth + Firestore)
- React Router DOM
- ESLint / Prettier

---

## 💻 Instalação

```bash
git clone https://github.com/gutenberggt/sigesc.git
cd sigesc
npm install
npm run dev
