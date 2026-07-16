from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_FILES = sorted(ROOT.rglob("*.py"))
TEXT_FILES = sorted(
    path
    for pattern in ("*.yml", "*.yaml", "*.md", "*.txt")
    for path in ROOT.rglob(pattern)
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join(relative.parts)


def parsed(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def imports(path: Path) -> set[str]:
    tree = parsed(path)
    if tree is None:
        return set()
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def node_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def class_inventory(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    tree = parsed(path)
    if tree is None:
        return [], []
    classes: list[dict[str, Any]] = []
    top_level_functions: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_functions.append(node.name)
            continue
        if not isinstance(node, ast.ClassDef):
            continue
        methods: list[dict[str, Any]] = []
        class_attributes: list[str] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(
                    {
                        "name": item.name,
                        "async": isinstance(item, ast.AsyncFunctionDef),
                        "decorators": [node_name(value) for value in item.decorator_list],
                        "start_line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "line_count": max(
                            1,
                            getattr(item, "end_lineno", item.lineno) - item.lineno + 1,
                        ),
                    }
                )
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        class_attributes.append(target.id)
        classes.append(
            {
                "name": node.name,
                "bases": [node_name(value) for value in node.bases],
                "methods": methods,
                "method_count": len(methods),
                "class_attributes": sorted(set(class_attributes)),
            }
        )
    return classes, sorted(top_level_functions)


def text_references(name: str) -> list[str]:
    token = name.rsplit(".", 1)[-1]
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
    found: list[str] = []
    for path in PYTHON_FILES + TEXT_FILES:
        if path.name == "cleanup_audit.py":
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if pattern.search(value):
            found.append(rel(path))
    return sorted(set(found))


def main() -> int:
    modules = {module_name(path): path for path in PYTHON_FILES}
    graph: dict[str, list[str]] = {}
    for name, path in modules.items():
        graph[name] = sorted(value for value in imports(path) if value in modules)

    runtime_modules = sorted(
        name
        for name in modules
        if name.rsplit(".", 1)[-1].startswith("admin_panel_runtime_v")
    )
    current = "admin_panel_runtime_v41"
    reachable: set[str] = set()
    stack = [current]
    while stack:
        name = stack.pop()
        if name in reachable:
            continue
        reachable.add(name)
        stack.extend(graph.get(name, []))

    runtime_report: list[dict[str, Any]] = []
    method_index: dict[str, list[str]] = {}
    total_runtime_lines = 0
    for name in runtime_modules:
        path = modules[name]
        refs = text_references(name)
        classes, top_level_functions = class_inventory(path)
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        total_runtime_lines += line_count
        for class_row in classes:
            for method in class_row["methods"]:
                method_index.setdefault(method["name"], []).append(name)
        runtime_report.append(
            {
                "module": name,
                "path": rel(path),
                "line_count": line_count,
                "in_current_import_chain": name in reachable,
                "direct_imports": graph.get(name, []),
                "references": refs,
                "reference_count": len(refs),
                "classes": classes,
                "top_level_functions": top_level_functions,
            }
        )

    chapter_paths = sorted(path for path in ROOT.glob("chapter*.py") if path.is_file())
    chapter_report = [
        {
            "path": rel(path),
            "line_count": len(path.read_text(encoding="utf-8").splitlines()),
            "references": text_references(path.stem),
        }
        for path in chapter_paths
    ]

    unreferenced_python = []
    for name, path in modules.items():
        if rel(path).startswith("tools/") or rel(path).startswith("tests/"):
            continue
        refs = [item for item in text_references(name) if item != rel(path)]
        if not refs and path.name not in {
            "admin_bot.py",
            "monitor.py",
            "bbvg_monitor_main.py",
        }:
            unreferenced_python.append(rel(path))

    report = {
        "current_runtime": current,
        "runtime_file_count": len(runtime_modules),
        "runtime_chain_count": sum(
            1 for row in runtime_report if row["in_current_import_chain"]
        ),
        "runtime_total_lines": total_runtime_lines,
        "runtime_unique_method_count": len(method_index),
        "runtime_method_index": {
            key: value for key, value in sorted(method_index.items())
        },
        "runtime_files": runtime_report,
        "chapter_files": chapter_report,
        "unreferenced_python_candidates": sorted(unreferenced_python),
    }
    output = ROOT / "cleanup_audit.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "runtime_file_count": report["runtime_file_count"],
                "runtime_chain_count": report["runtime_chain_count"],
                "runtime_total_lines": report["runtime_total_lines"],
                "runtime_unique_method_count": report["runtime_unique_method_count"],
                "unreferenced_candidates": len(
                    report["unreferenced_python_candidates"]
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
