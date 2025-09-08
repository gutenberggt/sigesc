import React from "react";

export function ButtonGroup({ children, className = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>{children}</div>
  );
}
