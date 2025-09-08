import React from "react";
import { Link, useLocation } from "react-router-dom";

function SidebarMenu({ menu, role, openSubmenu, toggleSubmenu }) {
  const location = useLocation();
  const Icon = menu.icon;

  // links com restrição interna (ex: matrícula só admin/secretario)
  const children = menu.children?.filter(
    (c) => !c.roles || c.roles.includes(role)
  );

  const isActive = (to) => location.pathname.startsWith(to);

  if (children?.length) {
    const isOpen = openSubmenu === menu.key;

    return (
      <li className="mb-2">
        <button
          onClick={() => toggleSubmenu(menu.key)}
          className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${
            isOpen ? "bg-blue-600 dark:bg-gray-700" : ""
          }`}
        >
          <div className="flex items-center">
            <Icon className="w-5 h-5 mr-2" />
            <span>{menu.label}</span>
          </div>
          <span>{isOpen ? "▲" : "▼"}</span>
        </button>
        {isOpen && (
          <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
            {children.map((child) => (
              <li key={child.to}>
                <Link
                  to={child.to}
                  className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${
                    isActive(child.to) ? "bg-blue-600 dark:bg-gray-600" : ""
                  }`}
                >
                  {child.label}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  }

  // menu simples
  return (
    <li className="mb-2">
      <Link
        to={menu.to}
        className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold ${
          isActive(menu.to) ? "bg-blue-600 dark:bg-gray-600" : ""
        }`}
      >
        <Icon className="w-5 h-5 mr-2" />
        <span>{menu.label}</span>
      </Link>
    </li>
  );
}

export default SidebarMenu;
