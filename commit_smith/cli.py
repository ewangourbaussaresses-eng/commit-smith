"""commit-smith — CLI de génération de commits conventionnels et de README."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__, llm
from .diff_parser import parse_diff
from .message import suggest, validate
from .readme import generate_readme

BANNER = "─" * 62


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"✖ git {' '.join(args)} : {result.stderr.strip()}")
    return result.stdout


def is_git_repo(cwd: Path) -> bool:
    try:
        git("rev-parse", "--is-inside-work-tree", cwd=cwd)
        return True
    except SystemExit:
        return False


def get_diff(args: argparse.Namespace) -> str:
    if args.from_ref:
        return git("diff", args.from_ref, args.to_ref or "HEAD")
    if args.all:
        return git("diff", "HEAD") if is_git_repo(Path.cwd()) else ""
    return git("diff", "--staged")


def command_commit(args: argparse.Namespace) -> int:
    if not is_git_repo(Path.cwd()):
        print("✖ ce dossier n'est pas un dépôt git", file=sys.stderr)
        return 2
    diff_text = get_diff(args)
    if not diff_text.strip():
        hint = "--all" if not args.all else "git add"
        print(f"ℹ aucun changement à analyser (essayez {hint})")
        return 1

    analysis = parse_diff(diff_text)
    result = suggest(analysis, diff_text, use_llm=not args.no_llm, max_chars=args.max_chars)
    message = result["message"]
    problems = validate(message)

    if args.json:
        print(json.dumps({"message": message, "problems": problems,
                          "summary": analysis.summary_line,
                          "generated_by": result["generated_by"],
                          "files": [c.path for c in analysis.files]},
                         ensure_ascii=False, indent=2))
    else:
        print(BANNER)
        print(f" {analysis.summary_line}   [{result['generated_by']}]")
        print(BANNER)
        print(message)
        print(BANNER)
        if problems:
            for problem in problems:
                print(f"⚠ {problem}")
        else:
            print("✔ conforme aux Conventional Commits")

    if not args.apply:
        return 0

    if not args.yes:
        answer = input("Créer ce commit ? [o/N] ").strip().lower()
        if answer not in ("o", "oui", "y", "yes"):
            print("annulé")
            return 1

    try:
        git("commit", "-m", message)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    print("✔ commit créé")
    return 0


def command_readme(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"✖ dossier introuvable : {root}", file=sys.stderr)
        return 2

    result = generate_readme(root, use_llm=not args.no_llm)
    content = result["content"]
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    if args.json:
        print(json.dumps({"path": str(out), "generated_by": result["generated_by"],
                          "content": content}, ensure_ascii=False, indent=2))
        return 0

    if out.exists() and not args.force:
        print(f"⚠ {out} existe déjà — utilisez --force pour l'écraser")
        return 1

    out.write_text(content, encoding="utf-8")
    info = result["info"]
    print(f"✔ README écrit : {out}")
    print(f"  {info['files']} fichier(s), langages : {', '.join(info['languages'][:4]) or '—'}")
    print(f"  moteur : {result['generated_by']}")
    return 0


def command_llm(args: argparse.Namespace) -> int:
    info = llm.status()
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    print(f"Fournisseur : {info['provider']} "
          f"({'connecté' if info['available'] else 'non configuré'})")
    if info["model"]:
        print(f"Modèle      : {info['model']}")
    print(f"Clé Claude  : {'présente' if info['claude_key'] else 'absente (ANTHROPIC_API_KEY)'}")
    print(f"Clé OpenAI  : {'présente' if info['openai_key'] else 'absente (OPENAI_API_KEY)'}")
    if not info["available"]:
        print("→ Sans clé, l'outil fonctionne en mode règles (100 % hors ligne).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="commit-smith",
        description="Génère des messages de commit conventionnels et des README.")
    parser.add_argument("--version", action="version", version=f"commit-smith {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    commit = sub.add_parser("commit", help="proposer un message de commit depuis git diff")
    commit.add_argument("--all", action="store_true", help="inclure les changements non indexés")
    commit.add_argument("--from", dest="from_ref", help="référence de départ (ex. main)")
    commit.add_argument("--to", dest="to_ref", help="référence d'arrivée (défaut HEAD)")
    commit.add_argument("--apply", action="store_true", help="créer le commit après confirmation")
    commit.add_argument("--yes", action="store_true", help="ne pas demander confirmation")
    commit.add_argument("--no-llm", action="store_true", help="forcer l'analyse par règles")
    commit.add_argument("--max-chars", type=int, default=72, help="longueur max du sujet")
    commit.add_argument("--json", action="store_true", help="sortie JSON")
    commit.set_defaults(func=command_commit)

    readme = sub.add_parser("readme", help="générer un README.md pour un dossier")
    readme.add_argument("path", nargs="?", default=".", help="dossier à scanner")
    readme.add_argument("--out", default="README.md", help="fichier de sortie")
    readme.add_argument("--force", action="store_true", help="écraser un README existant")
    readme.add_argument("--no-llm", action="store_true", help="forcer le rendu par règles")
    readme.add_argument("--json", action="store_true", help="sortie JSON")
    readme.set_defaults(func=command_readme)

    llm_cmd = sub.add_parser("llm", help="état du connecteur IA")
    llm_cmd.add_argument("--json", action="store_true")
    llm_cmd.set_defaults(func=command_llm)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
