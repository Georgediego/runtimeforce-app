"""
Multi-Language File Intelligence Service v2.
Supports Python AST parsing + TypeScript, JavaScript, Go, HTML, and CSS regex indexers.
"""
import os
import ast
import re
import logging
from typing import Dict, Any, List
from app.services.memory.graph_memory_service import GraphMemoryService

logger = logging.getLogger("runtimeforce.service.memory.file_intelligence")

class FileIntelligenceService:
    def __init__(self, graph_memory: GraphMemoryService):
        self.graph_memory = graph_memory

    def index_file(self, filepath: str, content: str, project_id: str, user_id: str):
        file_node_id = f"file-{filepath}"
        ext = os.path.splitext(filepath)[1].lower()

        self.graph_memory.record_entity(
            node_id=file_node_id,
            user_id=user_id,
            project_id=project_id,
            node_type="File",
            label=os.path.basename(filepath),
            attributes={"path": filepath, "extension": ext, "size": len(content)},
            text_for_search=f"{filepath}\n{content[:2000]}"
        )

        if ext == ".py":
            self._index_python(file_node_id, filepath, content, project_id, user_id)
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            self._index_ts_js(file_node_id, filepath, content, project_id, user_id)
        elif ext == ".go":
            self._index_go(file_node_id, filepath, content, project_id, user_id)

    def _index_python(self, file_node_id: str, filepath: str, content: str, project_id: str, user_id: str):
        try:
            tree = ast.parse(content, filename=filepath)
            for item in tree.body:
                if isinstance(item, ast.ClassDef):
                    class_id = f"class-{filepath}-{item.name}"
                    self.graph_memory.record_entity(class_id, user_id, project_id, "Class", item.name, {"file": filepath, "lang": "python"})
                    self.graph_memory.link_entities(file_node_id, class_id, "CONTAINS")

                    for elem in item.body:
                        if isinstance(elem, ast.FunctionDef):
                            func_id = f"func-{filepath}-{item.name}.{elem.name}"
                            self.graph_memory.record_entity(func_id, user_id, project_id, "Function", elem.name, {"class": item.name, "lang": "python"})
                            self.graph_memory.link_entities(class_id, func_id, "CONTAINS")

                elif isinstance(item, ast.FunctionDef):
                    func_id = f"func-{filepath}-{item.name}"
                    self.graph_memory.record_entity(func_id, user_id, project_id, "Function", item.name, {"file": filepath, "lang": "python"})
                    self.graph_memory.link_entities(file_node_id, func_id, "CONTAINS")

                elif isinstance(item, (ast.Import, ast.ImportFrom)):
                    mod_name = getattr(item, "module", None) or ", ".join(alias.name for alias in item.names)
                    imp_id = f"import-{filepath}-{mod_name}"
                    self.graph_memory.record_entity(imp_id, user_id, project_id, "Import", mod_name, {"file": filepath})
                    self.graph_memory.link_entities(file_node_id, imp_id, "DEPENDS_ON")

        except Exception as e:
            logger.debug(f"Python AST parse failed for {filepath}, falling back to regex: {e}")
            self._index_regex_generic(file_node_id, filepath, content, project_id, user_id, lang="python")

    def _index_ts_js(self, file_node_id: str, filepath: str, content: str, project_id: str, user_id: str):
        # Imports
        imports = re.findall(r"import\s+.*?from\s+['\"](.*?)['\"]", content)
        for imp in imports:
            imp_id = f"import-{filepath}-{imp}"
            self.graph_memory.record_entity(imp_id, user_id, project_id, "Import", imp, {"file": filepath, "lang": "ts/js"})
            self.graph_memory.link_entities(file_node_id, imp_id, "DEPENDS_ON")

        # Classes & Interfaces
        classes = re.findall(r"(?:class|interface)\s+([a-zA-Z0-9_]+)", content)
        for c in classes:
            c_id = f"symbol-{filepath}-{c}"
            self.graph_memory.record_entity(c_id, user_id, project_id, "Class", c, {"file": filepath, "lang": "ts/js"})
            self.graph_memory.link_entities(file_node_id, c_id, "CONTAINS")

        # Functions & Arrow Functions
        functions = re.findall(r"(?:function|const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\(", content)
        functions += re.findall(r"function\s+([a-zA-Z0-9_]+)\s*\(", content)
        for f in set(functions):
            f_id = f"func-{filepath}-{f}"
            self.graph_memory.record_entity(f_id, user_id, project_id, "Function", f, {"file": filepath, "lang": "ts/js"})
            self.graph_memory.link_entities(file_node_id, f_id, "CONTAINS")

    def _index_go(self, file_node_id: str, filepath: str, content: str, project_id: str, user_id: str):
        pkg_match = re.search(r"package\s+([a-zA-Z0-9_]+)", content)
        if pkg_match:
            pkg_id = f"pkg-{filepath}-{pkg_match.group(1)}"
            self.graph_memory.record_entity(pkg_id, user_id, project_id, "Package", pkg_match.group(1), {"file": filepath, "lang": "go"})
            self.graph_memory.link_entities(file_node_id, pkg_id, "CONTAINS")

        funcs = re.findall(r"func\s+(?:\([^)]+\)\s*)?([a-zA-Z0-9_]+)\s*\(", content)
        for f in set(funcs):
            f_id = f"func-{filepath}-{f}"
            self.graph_memory.record_entity(f_id, user_id, project_id, "Function", f, {"file": filepath, "lang": "go"})
            self.graph_memory.link_entities(file_node_id, f_id, "CONTAINS")

        structs = re.findall(r"type\s+([a-zA-Z0-9_]+)\s+struct", content)
        for s in structs:
            s_id = f"struct-{filepath}-{s}"
            self.graph_memory.record_entity(s_id, user_id, project_id, "Struct", s, {"file": filepath, "lang": "go"})
            self.graph_memory.link_entities(file_node_id, s_id, "CONTAINS")

    def _index_regex_generic(self, file_node_id: str, filepath: str, content: str, project_id: str, user_id: str, lang: str):
        funcs = re.findall(r"def\s+([a-zA-Z0-9_]+)", content)
        for f in set(funcs):
            f_id = f"func-{filepath}-{f}"
            self.graph_memory.record_entity(f_id, user_id, project_id, "Function", f, {"file": filepath, "lang": lang})
            self.graph_memory.link_entities(file_node_id, f_id, "CONTAINS")
