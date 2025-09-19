import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css"; // importa Tailwind + fontes Inter
import App from "./App";
import { ToastProvider } from "./components/ui/toastProvider.jsx"; // ✅ importado

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
    <ToastProvider /> {/* ✅ agora todos os toasts funcionam */}
  </React.StrictMode>
);
