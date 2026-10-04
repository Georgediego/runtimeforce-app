
export function formatSessionTime(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso.endsWith("Z") ? iso : iso.replace(" ", "T") + "Z");
        const diff = (Date.now() - d) / 1000;
        if (isNaN(diff) || diff < 0) return "";
        if (diff < 60) return "только что";
        if (diff < 3600) return Math.floor(diff / 60) + " мин назад";
        if (diff < 86400) return Math.floor(diff / 3600) + " ч назад";
        if (diff < 604800) return Math.floor(diff / 86400) + " дн назад";
        return d.toLocaleDateString("ru-RU");
    } catch {
        return "";
    }
}

export function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
