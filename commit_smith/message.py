"""Génération du message de commit : règles locales + option LLM."""
from __future__ import annotations

from typing import Any

from . import llm
from .diff_parser import (DiffAnalysis, FRAGMENTS, build_message, changed_symbols)

SYSTEM = (
    "Tu es un développeur senior qui écrit des messages de commit conventionnels "
    "(Conventional Commits). Tu réponds UNIQUEMENT en JSON, en français, sans flatterie."
)


def describe_locally(analysis: DiffAnalysis, diff_text: str) -> str:
    """Description courte déduite des fichiers et des symboles touchés."""
    type_name = analysis.commit_types[0] if analysis.commit_types else "chore"
    verb = FRAGMENTS.get(type_name, "modifier")
    symbols = changed_symbols(diff_text)

    if analysis.is_breaking:
        return f"{verb} l'API publique de {analysis.scope or 'projet'}"
    if analysis.new_files and len(analysis.new_files) == len(analysis.files):
        names = ", ".join(f.rsplit("/", 1)[-1] for f in analysis.new_files[:3])
        return f"{verb} {names}"
    if symbols:
        target = ", ".join(symbols[:3])
        return f"{verb} {target}"
    if analysis.files:
        names = ", ".join(f.path.rsplit("/", 1)[-1] for f in analysis.files[:3])
        more = f" (+{len(analysis.files) - 3})" if len(analysis.files) > 3 else ""
        return f"{verb} {names}{more}"
    return "mettre à jour le projet"


def suggest_locally(analysis: DiffAnalysis, diff_text: str) -> dict[str, Any]:
    description = describe_locally(analysis, diff_text)
    body = [f"- {c.path}" for c in analysis.files[:10]]
    if len(analysis.files) > 10:
        body.append(f"- … et {len(analysis.files) - 10} autre(s)")
    message = build_message(analysis, description, body)
    return {"message": message, "description": description, "generated_by": "rules"}


def suggest_with_llm(analysis: DiffAnalysis, diff_text: str,
                     max_chars: int = 72) -> dict[str, Any] | None:
    """Demande un message au LLM. None si indisponible ou réponse invalide."""
    files = "\n".join(f"- {c.path} (+{c.added}/-{c.removed})" for c in analysis.files[:30])
    excerpt = "\n".join(diff_text.splitlines()[:250])
    prompt = f"""Analyse ce diff et propose un message de commit conventionnel.

Fichiers modifiés :
{files}

Diff (extrait) :
```diff
{excerpt}
```

Contraintes :
- sujet de {max_chars} caractères maximum, à l'impératif, en français, sans point final ;
- type parmi feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert ;
- périmètre court entre parenthèses si pertinent ;
- corps optionnel de 1 à 3 puces factuelles.

Réponds uniquement avec ce JSON :
{{"subject": "type(scope): description", "body": ["puce 1", "puce 2"]}}"""

    data = llm.ask_json(prompt, system=SYSTEM, max_tokens=400, temperature=0.2)
    if not isinstance(data, dict):
        return None
    subject = str(data.get("subject", "")).strip()
    if not subject:
        return None
    body = [str(b) for b in (data.get("body") or [])][:5]
    message = subject + ("\n\n" + "\n".join(f"- {b}" for b in body) if body else "")
    if analysis.is_breaking and "BREAKING" not in message:
        message += "\n\nBREAKING CHANGE: " + (body[0] if body else subject)
    return {"message": message, "description": subject, "generated_by": "llm"}


def suggest(analysis: DiffAnalysis, diff_text: str, use_llm: bool = True,
            max_chars: int = 72) -> dict[str, Any]:
    if use_llm and llm.is_available():
        result = suggest_with_llm(analysis, diff_text, max_chars=max_chars)
        if result:
            return result
    return suggest_locally(analysis, diff_text)


def validate(message: str) -> list[str]:
    """Vérifie le respect de Conventional Commits ; retourne les problèmes."""
    problems: list[str] = []
    first = message.splitlines()[0] if message else ""
    if not first:
        return ["message vide"]
    if not __import__("re").match(
            r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
            r"(\([\w\-./]+\))?!?: .+", first):
        problems.append("le sujet ne respecte pas « type(scope): description »")
    if len(first) > 100:
        problems.append(f"sujet trop long ({len(first)} > 100)")
    if first.endswith("."):
        problems.append("le sujet ne doit pas finir par un point")
    return problems
