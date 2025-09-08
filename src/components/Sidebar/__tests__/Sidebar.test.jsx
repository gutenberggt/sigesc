import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Sidebar from "../Sidebar";
import { menus } from "../menuConfig";

function renderSidebar(role, props = {}) {
  return render(
    <MemoryRouter>
      <Sidebar
        userRole={role}
        openSubmenu={props.openSubmenu || null}
        toggleSubmenu={props.toggleSubmenu || jest.fn()}
        sidebarOpen={true}
      />
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  test("Administrador deve ver todos os menus", () => {
    renderSidebar("administrador");

    menus.forEach((menu) => {
      expect(screen.getByText(menu.label)).toBeInTheDocument();
    });
  });

  test("Professor não deve ver menu de Configurações", () => {
    renderSidebar("professor");

    expect(screen.queryByText("Configurações")).not.toBeInTheDocument();
    expect(screen.getByText("Notas")).toBeInTheDocument();
  });

  test("Secretário deve ver menu Escola", () => {
    renderSidebar("secretario");

    expect(screen.getByText("Escola")).toBeInTheDocument();
  });

  test("Clicar em menu com submenu expande itens", () => {
    const toggleMock = jest.fn();
    renderSidebar("administrador", { toggleSubmenu: toggleMock });

    fireEvent.click(screen.getByText("Escola"));
    expect(toggleMock).toHaveBeenCalledWith("escola");
  });

  test("Menus filhos aparecem quando submenu está aberto", () => {
    renderSidebar("administrador", { openSubmenu: "escola" });

    expect(screen.getByText("Busca de Aluno")).toBeInTheDocument();
    expect(screen.getByText("Relatório Frequência")).toBeInTheDocument();
  });
});
