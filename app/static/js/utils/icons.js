export function refreshIcons(root = document.body) {
    if (window.lucide) {
        window.lucide.createIcons({ 
            root,
            nameAttr: 'data-lucide' 
        });
    }
}

export function getFileIcon(filename) {
    const ext = (filename.split(".").pop() || "").toLowerCase();
    const map = {
        py: "file-code", js: "file-code", ts: "file-code", jsx: "file-code", tsx: "file-code",
        html: "file-code", css: "file-code", scss: "file-code", vue: "file-code",
        json: "file-json", md: "file-text", txt: "file-text", yml: "file-text", yaml: "file-text",
        sh: "terminal", bash: "terminal", env: "lock", gitignore: "git-branch",
        jpg: "image", jpeg: "image", png: "image", gif: "image", svg: "image",
    };
    return map[ext] || "file";
}
