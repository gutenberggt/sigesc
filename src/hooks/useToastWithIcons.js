import toast from "react-hot-toast"

export function useToastWithIcons() {
  const toastSuccess = (message) => toast.success(message, { icon: "✅" })
  const toastError = (message) => toast.error(message, { icon: "❌" })
  const toastWarning = (message) => toast.error(message, { icon: "⚠️" })
  const toastInfo = (message) => toast(message, { icon: "ℹ️" })

  return {
    toastSuccess,
    toastError,
    toastWarning,
    toastInfo,
  }
}
