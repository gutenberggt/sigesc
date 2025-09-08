import React from "react";
import { roundUp1 } from "../utils/calculoNotas";

export default function NotaInput({ value, onChange, disabled = false }) {
  return (
    <input
      type="number"
      step="0.1"
      min="0"
      max="10"
      value={value === "" || value === null || value === undefined ? "" : value}
      onChange={(e) => {
        const v = e.target.value;
        if (v === "") return onChange("");
        const n = Number(v);
        if (!Number.isNaN(n)) onChange(n);
      }}
      onBlur={(e) => {
        const v = e.target.value;
        if (v === "") return;
        const n = Number(v);
        if (!Number.isNaN(n)) onChange(roundUp1(n));
      }}
      className={`w-20 p-1 border rounded text-center ${disabled ? "bg-gray-100 text-gray-500" : ""}`}
      disabled={disabled}
    />
  );
}
