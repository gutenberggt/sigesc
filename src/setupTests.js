// Habilita matchers adicionais (ex.: toBeInTheDocument, toHaveClass etc.)
import "@testing-library/jest-dom";

// ✅ Mocks específicos para o ambiente de testes (Jest + jsdom)
if (process.env.NODE_ENV === "test") {
  // Mock jsPDF
  jest.mock("jspdf", () => {
    return function () {
      return {
        text: jest.fn(),
        save: jest.fn(),
        addImage: jest.fn(),
        setFontSize: jest.fn(),
        setFont: jest.fn(),
        setTextColor: jest.fn(),
        rect: jest.fn(),
      };
    };
  });

  // Mock html2canvas
  jest.mock("html2canvas", () => {
    return jest.fn().mockResolvedValue({
      toDataURL: () => "data:image/png;base64,MOCK",
    });
  });
}
