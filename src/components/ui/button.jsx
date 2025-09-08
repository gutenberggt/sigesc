import React from "react";

const variants = {
  primary: "bg-primary-600 text-white hover:bg-primary-700",
  secondary: "bg-secondary-200 text-secondary-800 hover:bg-secondary-300",
  outline:
    "border border-secondary-300 bg-white text-secondary-700 hover:bg-secondary-100",
  danger: "bg-danger-600 text-white hover:bg-danger-700",
};

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  type = "button",
  disabled = false,
  pressed = false,
  onClick,
  className = "",
  ...props
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      className={`
        inline-flex items-center justify-center rounded-md font-medium transition-colors
        focus:outline-none focus:ring-2 focus:ring-offset-2
        ${variants[variant]}
        ${sizes[size]}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        ${className}
      `}
      {...props}
    >
      {children}
    </button>
  );
}
