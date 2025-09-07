import React from "react"
import { Toaster } from "react-hot-toast"

export function ToastProvider() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        className: "rounded-md shadow-md font-medium",
        duration: 4000,
        style: {
          padding: "12px 16px",
        },
        success: {
          style: {
            background: "#ecfdf5",
            color: "#166534",
            borderLeft: "4px solid #16a34a",
          },
          iconTheme: {
            primary: "#16a34a",
            secondary: "#ecfdf5",
          },
        },
        error: {
          style: {
            background: "#fef2f2",
            color: "#991b1b",
            borderLeft: "4px solid #dc2626",
          },
          iconTheme: {
            primary: "#dc2626",
            secondary: "#fef2f2",
          },
        },
        warning: {
          style: {
            background: "#fffbeb",
            color: "#92400e",
            borderLeft: "4px solid #f59e0b",
          },
          iconTheme: {
            primary: "#f59e0b",
            secondary: "#fffbeb",
          },
        },
        info: {
          style: {
            background: "#eff6ff",
            color: "#1e3a8a",
            borderLeft: "4px solid #3b82f6",
          },
          iconTheme: {
            primary: "#3b82f6",
            secondary: "#eff6ff",
          },
        },
      }}
    />
  )
}
