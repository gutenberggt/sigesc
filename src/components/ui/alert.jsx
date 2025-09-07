import React from "react"

const variants = {
  success: "bg-success-50 border-success-500 text-success-700",
  warning: "bg-warning-50 border-warning-500 text-warning-700",
  error: "bg-danger-50 border-danger-500 text-danger-700",
  info: "bg-primary-50 border-primary-500 text-primary-700",
}

export function Alert({ variant = "info", title, children }) {
  return (
    <div
      className={`rounded-md border-l-4 p-4 ${variants[variant]}`}
      role="alert"
    >
      <p className="font-bold">{title}</p>
      {children && <p className="mt-1 text-sm">{children}</p>}
    </div>
  )
}
