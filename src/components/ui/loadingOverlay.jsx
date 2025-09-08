import React from "react";
import { LoadingSpinner } from "./loading";

export function LoadingOverlay({ text = "Carregando..." }) {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-white/70 z-50">
      <div className="flex flex-col items-center gap-3">
        <LoadingSpinner size="lg" />
        <p className="text-secondary-700">{text}</p>
      </div>
    </div>
  );
}
