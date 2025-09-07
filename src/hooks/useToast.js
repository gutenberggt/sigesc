import toast from "react-hot-toast"

export function useToast() {
  return {
    toastSuccess: (msg) => toast.success(msg),
    toastError: (msg) => toast.error(msg),
    toastWarning: (msg) => toast(msg, { icon: "⚠️", type: "warning" }),
    toastInfo: (msg) => toast(msg, { icon: "ℹ️", type: "info" }),
  }
}
