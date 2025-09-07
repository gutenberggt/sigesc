import React from "react"

export function Tabs({ value, onValueChange, children }) {
  return <div>{React.Children.map(children, child =>
    React.cloneElement(child, { value, onValueChange })
  )}</div>
}

export function TabsList({ children }) {
  return (
    <div className="flex border-b border-secondary-200 mb-4 space-x-4">
      {children}
    </div>
  )
}

export function TabsTrigger({ value, activeValue, onValueChange, children }) {
  const isActive = value === activeValue
  return (
    <button
      onClick={() => onValueChange?.(value)}
      className={`
        px-4 py-2 text-sm font-medium transition-colors
        border-b-2 -mb-px
        ${isActive
          ? "border-primary-600 text-primary-700"
          : "border-transparent text-secondary-500 hover:text-secondary-700 hover:border-secondary-300"}
      `}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, activeValue, children }) {
  if (value !== activeValue) return null
  return <div>{children}</div>
}
