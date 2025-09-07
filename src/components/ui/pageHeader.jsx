import React from "react"

export function PageHeader({ title, subtitle, actions, className = "" }) {
  return (
    <div className={`flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6 ${className}`}>
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        {subtitle && (
          <p className="text-gray-600 text-sm mt-1">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  )
}
