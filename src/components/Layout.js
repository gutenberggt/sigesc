import React from "react";

const Layout = ({ children }) => {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-blue-800 text-white p-4 shadow">
        <div className="text-xl font-bold">SIGESC</div>
      </header>
      <main className="flex-1 p-6">{children}</main>
      <footer className="bg-gray-200 text-center py-2 text-sm text-gray-600">
        &copy; {new Date().getFullYear()} SIGESC - Todos os direitos reservados
      </footer>
    </div>
  );
};

export default Layout;
