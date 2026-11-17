"""Analyse d'un diff git : fichiers, lignes ajoutées/supprimées, indices de type."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TYPE_RULES: list[tuple[str, str]] = [
    ("docs", r"(^|/)docs?/|\.md$|\.rst$|README|CHANGELOG"),
    ("test", r"(^|/)tests?/|test_.*\.py$|.*_test\.(go|py)$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$"),
    ("ci", r"\.github/workflows/|\.gitlab-ci|Jenkinsfile|\.circleci/"),
    ("build", r"(^|/)(package\.json|pyproject\.toml|setup\.py|requirements.*\.txt|"
              r"Dockerfile|docker-compose.*|Makefile|\.toml|\.lock)$"),
    ("style", r"\.(css|scss|sass|less)$|\.prettierrc|\.eslintrc"),
    ("perf", r"(^|/)(perf|bench)|benchmark"),
    ("fix", r"(^|/)(fix|bugfix|hotfix)"),
]

SCOPE_ALIASES = {
    "src": "", "lib": "", "app": "", "apps": "", "packages": "",
}

FRAGMENTS = {
    "feat": "ajouter", "fix": "corriger", "docs": "documenter", "test": "tester",
    "refactor": "remanier", "perf": "optimiser", "build": "mettre à jour",
    "ci": "ajuster", "style": "nettoyer", "chore": "maintenir", "revert": "annuler",
}


@dataclass
class FileChange:
    path: str
    added: int = 0
    removed: int = 0
    is_new: bool = False
    is_deleted: bool = False
    added_lines: list[str] = field(default_factory=list)

    @property
    def churn(self) -> int:
        return self.added + self.removed


@dataclass
class DiffAnalysis:
    files: list[FileChange] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    new_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    commit_types: list[str] = field(default_factory=list)
    scope: str = ""
    is_breaking: bool = False

    @property
    def summary_line(self) -> str:
        return f"{len(self.files)} fichier(s), +{self.added} −{self.removed}"


def parse_diff(diff_text: str) -> DiffAnalysis:
    """Analyse un `git diff` unifié."""
    analysis = DiffAnalysis()
    current: FileChange | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            if match:
                current = FileChange(path=match.group(2))
                analysis.files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current.is_new = True
            analysis.new_files.append(current.path)
            continue
        if line.startswith("deleted file mode"):
            current.is_deleted = True
            analysis.deleted_files.append(current.path)
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current.added += 1
            current.added_lines.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            current.removed += 1
        if "BREAKING CHANGE" in line:
            analysis.is_breaking = True

    analysis.added = sum(f.added for f in analysis.files)
    analysis.removed = sum(f.removed for f in analysis.files)
    analysis.scope = guess_scope(analysis)
    analysis.commit_types = guess_types(analysis)
    return analysis


def guess_scope(analysis: DiffAnalysis) -> str:
    """Périmètre = premier dossier significatif commun."""
    dirs = []
    for change in analysis.files:
        parts = change.path.split("/")
        if len(parts) > 1 and parts[0] not in SCOPE_ALIASES:
            dirs.append(parts[0])
    if not dirs:
        return ""
    most_common = max(set(dirs), key=dirs.count)
    return most_common if dirs.count(most_common) == len(dirs) else ""


def guess_types(analysis: DiffAnalysis) -> list[str]:
    """Types probables, du plus probable au moins probable."""
    scores = {"feat": 0, "fix": 0, "docs": 0, "test": 0, "ci": 0,
              "build": 0, "style": 0, "refactor": 0, "perf": 0}

    for change in analysis.files:
        matched = False
        for type_name, pattern in TYPE_RULES:
            if re.search(pattern, change.path, re.IGNORECASE):
                scores[type_name] += 2
                matched = True
                break
        if not matched:
            scores["refactor" if change.removed > change.added * 2 else "feat"] += 1

    if analysis.deleted_files and not analysis.new_files:
        scores["refactor"] += 2

    ordered = [t for t, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s > 0]
    return ordered or ["chore"]


def changed_symbols(diff_text: str, limit: int = 12) -> list[str]:
    """Noms de fonctions/classes touchées, pour enrichir la description."""
    names: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        match = re.match(r"[+-]\s*(?:async\s+)?(?:def|class|function|const|let|export function)\s+"
                         r"([A-Za-z_][\w]*)", line)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names[:limit]


def build_message(analysis: DiffAnalysis, description: str, body_lines: list[str] | None = None,
                  commit_type: str | None = None) -> str:
    """Assemble le message au format conventionnel."""
    type_name = commit_type or (analysis.commit_types[0] if analysis.commit_types else "chore")
    scope = f"({analysis.scope})" if analysis.scope else ""
    bang = "!" if analysis.is_breaking else ""
    subject = f"{type_name}{scope}{bang}: {description}".strip()
    subject = subject[:100]
    parts = [subject]
    if body_lines:
        parts.append("\n" + "\n".join(body_lines))
    if analysis.is_breaking:
        parts.append("\nBREAKING CHANGE: " + (body_lines[0] if body_lines else description))
    return "\n".join(parts)
