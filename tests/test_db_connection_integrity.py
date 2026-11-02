import ast
import glob

import pytest


def test_static_ast_no_close_on_shared_connections():
    """
    Connections returned by get_connection() are shared by repositories and
    must not be closed by repository methods.
    """
    repo_files = glob.glob("app/repository/*.py")
    assert repo_files, "No repository files found"

    for filepath in repo_files:
        with open(filepath, "r", encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read(), filename=filepath)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            connection_names = set()
            for subnode in ast.walk(node):
                if not isinstance(subnode, ast.Assign):
                    continue
                calls_get_connection = any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "get_connection"
                    for child in ast.walk(subnode.value)
                )
                if calls_get_connection:
                    connection_names.update(
                        target.id
                        for target in subnode.targets
                        if isinstance(target, ast.Name)
                    )

            for subnode in ast.walk(node):
                if (
                    isinstance(subnode, ast.Call)
                    and isinstance(subnode.func, ast.Attribute)
                    and subnode.func.attr == "close"
                    and isinstance(subnode.func.value, ast.Name)
                    and subnode.func.value.id in connection_names
                ):
                    pytest.fail(
                        "Shared database connection "
                        f"'{subnode.func.value.id}' is closed in "
                        f"{filepath}:{node.name}"
                    )
