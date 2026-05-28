
import { refreshIcons } from "../utils/icons.js";

export function showToast(message, type = "info", duration = 3000) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast " + type;
    const icons = { success: "check-circle", error: "alert-circle", info: "info" };
    const colors = { success: "text-ide-success", error: "text-ide-error", info: "text-ide-accent" };
    toast.innerHTML = "<i data-lucide=\"" + (icons[type] || "info") + "\" class=\"w-4 h-4 " + (colors[type] || colors.info) + "\"></i><span>" + message + "</span>";
    container.appendChild(toast);
    refreshIcons(toast);
    setTimeout(() => {
        toast.classList.add("fade-out");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}
