
export function initTerminal() {
    var header = document.getElementById("terminal-header");
    var closeBtn = document.getElementById("close-terminal-btn");
    var panel = document.getElementById("terminal-panel");

    if (header) {
        header.addEventListener("click", function(e) {
            if (e.target.closest("#close-terminal-btn")) return;
            panel.classList.toggle("collapsed");
        });
    }
    if (closeBtn) {
        closeBtn.addEventListener("click", function(e) {
            e.stopPropagation();
            panel.classList.toggle("collapsed");
        });
    }
}
