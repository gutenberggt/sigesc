import React from "react";
import ReactDOM from "react-dom/client";
import "@/utils/silenceLogsInProduction";
import "@/utils/contentCopyErrorNormalizer";
import { installClientTimeContext } from "@/utils/clientTimeContext";
import { installImpersonationOfflineGuard } from "@/utils/impersonationOfflineGuard";
import { installClassPdfDirectDownload } from "@/utils/classPdfDirectDownload";
import "@/index.css";
import App from "@/App";

installClientTimeContext();
installImpersonationOfflineGuard();
installClassPdfDirectDownload();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
