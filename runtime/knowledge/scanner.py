"""Deterministic, text-only repository scanner."""

from __future__ import annotations

import ast
import fnmatch
import json
import re
from pathlib import Path

from runtime.knowledge.models import *

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".md": "Markdown", ".toml": "TOML",
    ".txt": "Text",
}
ALWAYS_IGNORE = {".git", ".hg", ".svn", "__pycache__", "node_modules",
                 ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build"}


class RepositoryScanner:
    def scan(self, repository_id: str, root: str | Path) -> RepositoryKnowledge:
        root = Path(root).resolve()
        patterns = _ignore_patterns(root)
        files = []
        directories = set()
        for path in sorted(root.rglob("*"), key=lambda x: x.as_posix().casefold()):
            relative = path.relative_to(root).as_posix()
            if _ignored(relative, path, patterns):
                continue
            if path.is_dir():
                directories.add(relative)
                continue
            if not path.is_file() or _binary(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            node = _file(relative, path, text)
            files.append(node)
            parent = path.parent
            while parent != root:
                directories.add(parent.relative_to(root).as_posix())
                parent = parent.parent
        sorted_files = tuple(sorted(files, key=lambda x: x.path))
        deps = tuple(sorted(
            (DependencyEdge(item.path, ref.module) for item in sorted_files for ref in item.imports),
            key=lambda x: (x.source, x.target, x.kind)))
        directory_nodes = tuple(DirectoryNode(path, sum(
            f.path.startswith(path + "/") for f in sorted_files)) for path in sorted(directories))
        return RepositoryKnowledge(repository_id, str(root), directory_nodes, sorted_files, deps)


def _ignore_patterns(root):
    path = root / ".gitignore"
    if not path.is_file():
        return ()
    return tuple(line.strip().lstrip("/") for line in path.read_text(
        encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith("!"))


def _ignored(relative, path, patterns):
    if any(part in ALWAYS_IGNORE for part in path.parts):
        return True
    return any(fnmatch.fnmatch(relative, pattern) or
               fnmatch.fnmatch(relative, pattern.rstrip("/") + "/**") for pattern in patterns)


def _binary(path):
    try:
        return b"\x00" in path.read_bytes()[:4096]
    except OSError:
        return True


def _file(relative, path, text):
    name = path.name
    language = ("Dockerfile" if name.lower().startswith("dockerfile") else
                "Requirements" if name.lower().startswith("requirements") and path.suffix == ".txt"
                else LANGUAGES.get(path.suffix.lower(), "Other"))
    category = _category(relative, name)
    symbols, imports, exports, malformed = (), (), (), False
    module = None
    if language == "Python":
        module = relative[:-3].replace("/", ".")
        symbols, imports, exports, malformed = _python(text, module)
    elif language in {"JavaScript", "TypeScript"}:
        symbols, imports, exports = _javascript(text, relative)
    elif language == "JSON":
        try:
            payload = json.loads(text)
            if name.lower() == "package.json" and isinstance(payload, dict):
                packages = {}
                for key in ("dependencies", "devDependencies", "peerDependencies"):
                    if isinstance(payload.get(key), dict):
                        packages.update(payload[key])
                imports = tuple(ImportReference(value) for value in sorted(packages))
        except json.JSONDecodeError: malformed = True
    elif language == "Requirements":
        imports = tuple(ImportReference(line.split(";")[0].split("==")[0].split(">=")[0].strip())
                        for line in text.splitlines()
                        if line.strip() and not line.lstrip().startswith(("#", "-")))
    return FileNode(relative, name, language, len(text.encode()), len(text.splitlines()),
                    category, module, symbols, imports, exports, malformed)


def _category(path, name):
    lower, filename = path.lower(), name.lower()
    if "test" in filename or "/tests/" in "/" + lower: return "test"
    if filename.startswith("readme") or lower.endswith((".md", ".rst")): return "documentation"
    if filename in {"package.json", "pyproject.toml", "setup.py", "setup.cfg"} or \
            filename.startswith(("requirements", "dockerfile")) or \
            lower.startswith((".github/", ".gitlab-ci")): return "configuration"
    if "migration" in lower: return "migration"
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico")): return "asset"
    if lower.endswith((".env", ".env.example")): return "environment"
    return "source"


def _python(text, module):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return (), (), (), True
    symbols, imports, exports = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = tuple(alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                for name in names: imports.append(ImportReference(name, (), node.lineno))
            else: imports.append(ImportReference(node.module or "", names, node.lineno))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            parent = _parent_name(tree, node)
            kind = "class" if isinstance(node, ast.ClassDef) else ("method" if parent else "function")
            qualified = ".".join(x for x in (module, parent, node.name) if x)
            symbols.append(Symbol(node.name, kind, qualified, node.lineno,
                getattr(node, "end_lineno", None), parent,
                tuple(_decorator(x) for x in node.decorator_list), ast.get_docstring(node),
                not node.name.startswith("_")))
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and getattr(node, "col_offset", 1) == 0:
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(Symbol(target.id, "constant", f"{module}.{target.id}", node.lineno))
    return tuple(sorted(symbols, key=lambda x: (x.line, x.name))), \
        tuple(sorted(imports, key=lambda x: (x.line or 0, x.module, x.names))), \
        tuple(exports), False


def _parent_name(tree, target):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and target in node.body:
            return node.name
    return None


def _decorator(node):
    try: return ast.unparse(node)
    except Exception: return type(node).__name__


def _javascript(text, module):
    imports = [ImportReference(match.group(1), (), index)
               for index, line in enumerate(text.splitlines(), 1)
               if (match := re.search(r"(?:from\s+|require\()['\"]([^'\"]+)", line))]
    exports = [ExportReference(match.group(1), index)
               for index, line in enumerate(text.splitlines(), 1)
               if (match := re.search(r"export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)", line))]
    symbols = []
    for index, line in enumerate(text.splitlines(), 1):
        match = re.search(r"\b(class|function)\s+(\w+)", line)
        if match:
            symbols.append(Symbol(match.group(2), match.group(1),
                                  f"{module}:{match.group(2)}", index))
    return tuple(symbols), tuple(imports), tuple(exports)
