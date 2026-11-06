const el = (id) => document.getElementById(id);
const bytes = (n) => {
    if (!Number.isFinite(n)) return "Unavailable";
    const units=["B","KB","MB","GB","TB"]; let i=0, v=n;
    while(v>=1024 && i<units.length-1){v/=1024;i++;}
    return `${v.toFixed(i?1:0)} ${units[i]}`;
};
const uptime = (n) => {
    if(!Number.isFinite(n)) return "Uptime unavailable";
    const d=Math.floor(n/86400), h=Math.floor(n%86400/3600), m=Math.floor(n%3600/60);
    return `Uptime ${d}d ${h}h ${m}m`;
};
const label=(id,value)=>{const node=el(id);if(node)node.textContent=value;};
const setStatus=(value)=>label("rf-monitor-status",value);
const bar=(id,value)=>{const node=el(id);if(node)node.style.width=Number.isFinite(value)?`${Math.max(0,Math.min(100,value))}%`:"0%";};
async function refresh(){
    try{
        const response=await fetch("/api/v1/system/metrics",{cache:"no-store"});
        if(!response.ok)throw new Error(`HTTP ${response.status}`);
        const data=await response.json(), load=Array.isArray(data.load_average)?data.load_average[0]:null;
        setStatus("LIVE");
        label("rf-monitor-load",load===null?"Unavailable":`${load.toFixed(2)} / ${data.cpu_count||"?"} cores`);
        if(data.memory){label("rf-monitor-memory",`${bytes(data.memory.used_bytes)} / ${bytes(data.memory.total_bytes)} · ${data.memory.percent}%`);bar("rf-monitor-memory-bar",data.memory.percent);}
        else label("rf-monitor-memory","Unavailable");
        if(data.disk){label("rf-monitor-disk",`${bytes(data.disk.used_bytes)} / ${bytes(data.disk.total_bytes)} · ${data.disk.percent}%`);bar("rf-monitor-disk-bar",data.disk.percent);}
        else label("rf-monitor-disk","Unavailable");
        label("rf-monitor-uptime",uptime(data.uptime_seconds));
        label("rf-monitor-updated",`Updated ${new Date().toLocaleTimeString()}`);
    }catch(error){
        setStatus("OFFLINE");
        ["rf-monitor-load","rf-monitor-memory","rf-monitor-disk"].forEach(id=>label(id,"Unavailable"));
        label("rf-monitor-updated","Metrics offline");
    }
}
refresh();
window.setInterval(refresh,15000);
