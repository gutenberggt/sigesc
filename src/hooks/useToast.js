import toast from "react-hot-toast";

/**
 * Hook unificado para exibir notificações.
 * Permite passar ícone customizado, mas já tem presets prontos.
 */
export function useToast() {
  const baseToast = (message, options = {}) => toast(message, options);

  const toastSuccess = (message, options = {}) =>
    toast.success(message, { icon: "✅", ...options });

  const toastError = (message, options = {}) =>
    toast.error(message, { icon: "❌", ...options });

  const toastWarning = (message, options = {}) =>
    baseToast(message, { icon: "⚠️", style: { color: "#b45309" }, ...options });

  const toastInfo = (message, options = {}) =>
    baseToast(message, { icon: "ℹ️", style: { color: "#2563eb" }, ...options });

  return {
    toastSuccess,
    toastError,
    toastWarning,
    toastInfo,
  };
}
