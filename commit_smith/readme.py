"""Génération d'un README professionnel à partir d'un dossier de projet."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import llm

IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                ".next", ".pytest_cache", ".idea", ".vscode", "coverage", ".mypy_cache"}
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php",
                 ".c", ".cpp", ".cs", ".swift", ".kt", ".sh"}

SYSTEM = ("Tu es un développeur qui documente proprement ses projets. "
          "Tu écris en français, concis, sans marketing. Tu réponds UNIQUEMENT en JSON.")


def scan_project(root: Path, max_depth: int = 3) -> dict[str, Any]:
    """Inventaire du projet : langages, dépendances, entrée, tests, structure."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            files.append(path)

    suffix_counts: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower()
        if suffix in CODE_SUFFIXES:
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1

    languages = sorted(suffix_counts, key=lambda s: -suffix_counts[s])
    names = {p.name for p in files}
    deps: list[str] = []
    entry = ""
    scripts: dict[str, str] = {}

    if "package.json" in names:
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            deps = list(data.get("dependencies", {}))[:15]
            scripts = dict(data.get("scripts", {}))
            entry = data.get("main") or ""
        except (OSError, json.JSONDecodeError):
            pass
    if "pyproject.toml" in names:
        text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        deps += re.findall(r'^\s*"([\w\-\[\]]+)[<>=!~]', text, re.MULTILINE)[:15]
    if "requirements.txt" in names:
        deps += [line.split("==")[0].split(">=")[0].strip()
                 for line in (root / "requirements.txt").read_text(encoding="utf-8",
                                                                  errors="replace").splitlines()
                 if line.strip() and not line.startswith("#")][:15]

    entry_candidates = ["__main__.py", "cli.py", "main.py", "app.py", "manage.py",
                        "index.js", "index.ts", "server.js"]
    entry = entry or ""
    for candidate in entry_candidates:
        match = next((p for p in files if p.name == candidate), None)
        if match:
            entry = match.relative_to(root).as_posix()
            break

    has_tests = any("test" in p.name.lower() for p in files)
    has_requirements = "requirements.txt" in names
    has_docker = "Dockerfile" in names or "docker-compose.yml" in names
    has_ci = any(".github" in str(p) for p in files)

    structure = []
    for path in files[:40]:
        rel = path.relative_to(root).as_posix()
        if rel.count("/") <= max_depth - 1:
            structure.append(rel)

    return {
        "name": root.name,
        "files": len(files),
        "languages": languages,
        "dependencies": sorted(set(d for d in deps if d))[:15],
        "entry": entry,
        "scripts": scripts,
        "has_tests": has_tests,
        "has_requirements": has_requirements,
        "has_docker": has_docker,
        "has_ci": has_ci,
        "structure": structure,
        "existing_readme": (root / "README.md").read_text(encoding="utf-8", errors="replace")
        if (root / "README.md").exists() else "",
    }


LANG_NAMES = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
              ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
              ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C", ".cpp": "C++",
              ".sh": "Shell", ".swift": "Swift", ".kt": "Kotlin"}


def render_readme(info: dict[str, Any], description: str, features: list[str] | None = None,
                  install: str | None = None, usage: str | None = None,
                  extra_sections: dict[str, str] | None = None) -> str:
    langs = [LANG_NAMES.get(s, s.lstrip(".")) for s in info["languages"][:4]]
    badges = " ".join(f"`{lang}`" for lang in langs) or "`—`"
    title = info["name"].replace("_", "-")

    lines = [f"# {title}", "", f"{badges}", "", description.strip(), ""]

    if features:
        lines += ["## Fonctionnalités", ""] + [f"- {f}" for f in features] + [""]

    lines += ["## Installation", ""]
    if install:
        lines += [install.strip(), ""]
    elif "Python" in langs:
        install_cmd = ("pip install -r requirements.txt"
                       if info.get("has_requirements") else "pip install -e .")
        lines += ["```bash", "git clone <url-du-depot>", f"cd {info['name']}",
                  "python -m venv .venv && source .venv/bin/activate",
                  install_cmd, "```", ""]
    elif "JavaScript" in langs or "TypeScript" in langs:
        lines += ["```bash", "git clone <url-du-depot>", f"cd {info['name']}",
                  "npm install", "```", ""]
    else:
        lines += ["```bash", "git clone <url-du-depot>", f"cd {info['name']}", "```", ""]

    lines += ["## Utilisation", ""]
    if usage:
        lines += [usage.strip(), ""]
    elif info["scripts"]:
        lines += ["```bash"] + [f"npm run {name}" for name in list(info["scripts"])[:5]] + ["```", ""]
    elif info["entry"] and info["entry"].endswith("__main__.py"):
        package = info["entry"].rsplit("/", 1)[0] if "/" in info["entry"] else ""
        module = package.replace("/", ".") if package else info["name"].replace("-", "_")
        lines += ["```bash", f"python -m {module}", "```", ""]
    elif info["entry"]:
        runner = "python" if info["entry"].endswith(".py") else "node"
        lines += ["```bash", f"{runner} {info['entry']}", "```", ""]
    else:
        lines += ["Décrivez ici la commande principale.", ""]

    if info["dependencies"]:
        lines += ["## Dépendances principales", ""]
        lines += [f"- `{d}`" for d in info["dependencies"][:10]] + [""]

    lines += ["## Structure", "", "```"]
    lines += info["structure"][:25]
    lines += ["```", ""]

    lines += ["## Tests", "", "```bash",
              "python -m pytest -q" if "Python" in langs else "npm test", "```", ""]

    if info["has_docker"]:
        lines += ["## Docker", "", "```bash", "docker compose up --build", "```", ""]
    if info["has_ci"]:
        lines += ["## Intégration continue", "",
                  "Les workflows GitHub Actions se trouvent dans `.github/workflows/`.", ""]

    for heading, content in (extra_sections or {}).items():
        lines += [f"## {heading}", "", content.strip(), ""]

    lines += ["## Licence", "", "MIT — voir [LICENSE](LICENSE).", ""]
    return "\n".join(lines)


def generate_with_llm(info: dict[str, Any]) -> dict[str, Any] | None:
    prompt = f"""Rédige les éléments d'un README pour ce projet.

Nom : {info['name']}
Fichiers : {info['files']}
Langages : {', '.join(LANG_NAMES.get(s, s) for s in info['languages'][:5]) or 'inconnus'}
Dépendances : {', '.join(info['dependencies']) or 'aucune'}
Scripts : {', '.join(info['scripts']) or 'aucun'}
Tests présents : {info['has_tests']}
Point d'entrée : {info['entry'] or 'inconnu'}
Extrait du README existant : {info['existing_readme'][:600] or 'aucun'}

Réponds uniquement avec ce JSON :
{{"description": "2 phrases décrivant ce que fait le projet",
  "features": ["fonctionnalité 1", "fonctionnalité 2", "fonctionnalité 3"],
  "install": "bloc de commandes d'installation en markdown",
  "usage": "bloc de commandes d'utilisation en markdown"}}"""

    data = llm.ask_json(prompt, system=SYSTEM, max_tokens=800, temperature=0.4)
    return data if isinstance(data, dict) else None


def generate_readme(root: Path, use_llm: bool = True) -> dict[str, Any]:
    info = scan_project(root)
    langs = [LANG_NAMES.get(s, s) for s in info["languages"][:3]]
    description = (f"Projet {info['name']} ({', '.join(langs) or 'multi-langage'}), "
                   f"{info['files']} fichier(s).")
    features: list[str] = []
    install = usage = None
    generated_by = "rules"

    if use_llm and llm.is_available():
        data = generate_with_llm(info)
        if data:
            description = str(data.get("description") or description)
            features = [str(f) for f in (data.get("features") or [])][:6]
            install = data.get("install")
            usage = data.get("usage")
            generated_by = "llm"

    content = render_readme(info, description, features, install, usage)
    return {"content": content, "info": info, "generated_by": generated_by}
