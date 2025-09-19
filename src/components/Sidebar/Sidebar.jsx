import React from "react";
import SidebarMenu from "./SidebarMenu.jsx";
import { menus } from "./menuConfig";

function Sidebar({ userRole, openSubmenu, toggleSubmenu, sidebarOpen }) {
  // normaliza role pra minúsculo
  const role = userRole?.toLowerCase();

  const filteredMenus = menus.filter((menu) => menu.roles.includes(role));

  return (
    <aside
      className={`w-64 bg-blue-700 dark:bg-gray-800 text-white flex-shrink-0 p-4 fixed md:relative inset-y-0 left-0 transform ${
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      } md:translate-x-0 transition-transform duration-200 ease-in-out z-30 pt-16 md:pt-4`}
    >
      <nav className="mt-4">
        <ul>
          {filteredMenus.map((menu) => (
            <SidebarMenu
              key={menu.key}
              menu={menu}
              role={role}
              openSubmenu={openSubmenu}
              toggleSubmenu={toggleSubmenu}
            />
          ))}
        </ul>
      </nav>
    </aside>
  );
}

export default Sidebar;
