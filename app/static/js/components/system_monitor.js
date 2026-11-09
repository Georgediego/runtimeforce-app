const $ = (id) => document.getElementById(id);
const fmtRate = (value) => {
    const n = Number(value) || 0;
    if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + "M";
    if (n >= 1024) return (n / 1024).toFixed(1) + "K";
    return Math.round(n) + "B";
};
const level = (value) => value >= 85 ? "high" : value >= 65 ? "medium" : "low";

export const systemMonitor = {
    timer: null,
    async sample() {
        const started = performance.now();
        try {
            const token = (localStorage.getItem("rf_jwt_token") || localStorage.getItem("access_token") || "").replace(/^Bearer /, "");
            const response = await fetch("/api/v1/telemetry/system", {
                headers: token ? { Authorization: "Bearer " + token } : {},
                cache: "no-store",
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const data = await response.json();
            const ping = Math.round(performance.now() - started);
            this.setText("rf-monitor-ping", ping + " ms");
            $("rf-monitor-live")?.classList.remove("is-offline");
            this.setText("rf-monitor-cpu", data.cpu_percent == null ? "—" : Math.round(data.cpu_percent) + "%");
            this.setText("rf-monitor-ram", data.memory_percent == null ? "—" : Math.round(data.memory_percent) + "%");
            const cpu = $("rf-monitor-cpu-gauge");
            if (cpu) {
                cpu.dataset.level = level(data.cpu_percent || 0);
                cpu.style.setProperty("--rf-cpu-progress", (data.cpu_percent == null ? 0 : data.cpu_percent) + "%");
            }
            const ram = $("rf-monitor-ram-bar");
            if (ram) {
                ram.style.width = data.memory_percent == null ? "0%" : data.memory_percent + "%";
                ram.style.background = data.memory_percent >= 85 ? "#f87171" : data.memory_percent >= 65 ? "#facc15" : "#07f77a";
            }
            this.setText("rf-monitor-temp", data.temperature_c == null ? "—" : data.temperature_c + "°");
            this.setText("rf-monitor-up", fmtRate(data.network_up_bps));
            this.setText("rf-monitor-down", fmtRate(data.network_down_bps));
            $("rf-system-monitor")?.classList.remove("is-offline");
        } catch (error) {
            $("rf-monitor-live")?.classList.add("is-offline");
            $("rf-system-monitor")?.classList.add("is-offline");
            this.setText("rf-monitor-ping", "offline");
        }
    },
    setText(id, value) {
        const el = $(id);
        if (el) el.textContent = value;
    },
    init() {
        if (!$("rf-system-monitor") || this.timer) return;
        this.sample();
        this.timer = setInterval(() => this.sample(), 2000);
    },
};
document.addEventListener("DOMContentLoaded", () => systemMonitor.init());
