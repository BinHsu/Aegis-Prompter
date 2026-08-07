#!/usr/bin/env python3
"""Generates FILEMAP.md: a mechanical inventory of the repo's Python surface.

FILEMAP.md exists so an agent can answer "does this file/class/function exist, and
where?" without grepping the tree. It is GENERATED -- never hand-edit it, because
hand-maintained architecture tables rot the moment code moves.

Uses only the standard library (ast), so it runs without the project venv.

    python tools/gen_filemap.py            # rewrite FILEMAP.md
    python tools/gen_filemap.py --check    # exit 1 if FILEMAP.md is stale (for CI/hooks)
"""

import argparse
import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "FILEMAP.md")

# Directories that are never part of the reviewable source surface.
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".hf_cache", ".pip_cache", "context", "history", "logs", "node_modules",
}

BANNER = (
    "<!-- GENERATED FILE -- DO NOT EDIT.\n"
    "     Regenerate with: python tools/gen_filemap.py\n"
    "     Source of truth is the code itself; this file is derived from it. -->\n"
)


def find_python_files():
    """Walks the repo and yields repo-relative paths to every tracked .py file."""
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                abs_path = os.path.join(dirpath, filename)
                found.append(os.path.relpath(abs_path, REPO_ROOT))
    return sorted(found)


def summarize(rel_path):
    """Extracts the module docstring summary and top-level definitions via ast."""
    abs_path = os.path.join(REPO_ROOT, rel_path)
    with open(abs_path, "r", encoding="utf-8") as handle:
        source = handle.read()

    line_count = source.count("\n") + (0 if source.endswith("\n") or not source else 1)

    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        return {"lines": line_count, "doc": f"(unparseable: {exc.msg})", "symbols": []}

    doc = ast.get_docstring(tree) or ""
    summary = doc.strip().splitlines()[0].strip() if doc.strip() else ""

    symbols = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [
                f"{child.name}()"
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("__")
            ]
            symbols.append({"kind": "class", "name": node.name,
                            "line": node.lineno, "members": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append({"kind": "def", "name": f"{node.name}()",
                            "line": node.lineno, "members": []})

    return {"lines": line_count, "doc": summary, "symbols": symbols}


def render():
    """Builds the full FILEMAP.md text."""
    files = find_python_files()

    out = [BANNER, "\n# File Map\n"]
    out.append(
        "\nMechanical inventory of the Python surface, derived from the AST. Use it to check\n"
        "whether a module, class, or function exists and where it lives. Line numbers are\n"
        "accurate only as of the last regeneration -- if something looks wrong, regenerate\n"
        "rather than trusting this file:\n\n"
        "```bash\npython tools/gen_filemap.py\n```\n"
    )

    out.append(f"\n**{len(files)} Python files.**\n")

    current_dir = None
    for rel_path in files:
        directory = os.path.dirname(rel_path) or "."
        if directory != current_dir:
            current_dir = directory
            out.append(f"\n## `{directory}/`\n")

        info = summarize(rel_path)
        out.append(f"\n### `{rel_path}` — {info['lines']} lines\n")
        if info["doc"]:
            out.append(f"\n{info['doc']}\n")

        if not info["symbols"]:
            out.append("\n*No top-level classes or functions.*\n")
            continue

        out.append("\n")
        for sym in info["symbols"]:
            if sym["kind"] == "class":
                out.append(f"- `class {sym['name']}` (L{sym['line']})\n")
                for member in sym["members"]:
                    out.append(f"  - `{member}`\n")
            else:
                out.append(f"- `{sym['name']}` (L{sym['line']})\n")

    return "".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if FILEMAP.md does not match the code")
    args = parser.parse_args()

    rendered = render()

    if args.check:
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as handle:
                existing = handle.read()
        except FileNotFoundError:
            print("FILEMAP.md is missing. Run: python tools/gen_filemap.py", file=sys.stderr)
            return 1
        if existing != rendered:
            print("FILEMAP.md is stale. Run: python tools/gen_filemap.py", file=sys.stderr)
            return 1
        print("FILEMAP.md is up to date.")
        return 0

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    print(f"Wrote {os.path.relpath(OUTPUT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
