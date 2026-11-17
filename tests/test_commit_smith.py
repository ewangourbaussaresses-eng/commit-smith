"""Tests commit-smith — aucun accès réseau, aucun dépôt git requis (sauf test dédié)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commit_smith import llm  # noqa: E402
from commit_smith.cli import main  # noqa: E402
from commit_smith.diff_parser import (build_message, changed_symbols,  # noqa: E402
                                      guess_scope, parse_diff)
from commit_smith.message import suggest, validate  # noqa: E402
from commit_smith.readme import generate_readme, scan_project  # noqa: E402

SAMPLE_DIFF = """diff --git a/src/parser.py b/src/parser.py
index 111..222 100644
--- a/src/parser.py
+++ b/src/parser.py
@@ -1,3 +1,4 @@
 import re
+def parse_feed(xml):
+    return xml
-def old():
-    pass
diff --git a/src/feed.py b/src/feed.py
new file mode 100644
--- a/src/feed.py
+++ b/src/feed.py
@@ -0,0 +1 @@
+FEEDS = []
"""

DOCS_DIFF = """diff --git a/docs/guide.md b/docs/guide.md
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1,2 @@
 # Guide
+Ajout d'une section.
"""


def git_available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except (OSError, FileNotFoundError):
        return False


needs_git = pytest.mark.skipif(not git_available(), reason="git n'est pas installé")


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield


# --------------------------------------------------------------------------- #
# Analyse du diff
# --------------------------------------------------------------------------- #
def test_parse_diff_compte_les_lignes():
    analysis = parse_diff(SAMPLE_DIFF)
    assert len(analysis.files) == 2
    assert analysis.added == 3
    assert analysis.removed == 2


def test_parse_diff_detecte_fichiers_nouveaux():
    analysis = parse_diff(SAMPLE_DIFF)
    assert analysis.new_files == ["src/feed.py"]


def test_parse_diff_type_docs():
    assert parse_diff(DOCS_DIFF).commit_types[0] == "docs"


def test_parse_diff_type_test():
    diff = """diff --git a/tests/test_x.py b/tests/test_x.py
--- a/tests/test_x.py
+++ b/tests/test_x.py
@@ -1 +1,2 @@
+assert True
"""
    assert parse_diff(diff).commit_types[0] == "test"


def test_scope_commun():
    diff = """diff --git a/core/a.py b/core/a.py
--- a/core/a.py
+++ b/core/a.py
@@ -1 +1 @@
-a
+b
diff --git a/core/b.py b/core/b.py
--- a/core/b.py
+++ b/core/b.py
@@ -1 +1 @@
-a
+b
"""
    assert guess_scope(parse_diff(diff)) == "core"


def test_scope_absent_si_dossiers_differents():
    diff = """diff --git a/api/a.py b/api/a.py
--- a/api/a.py
+++ b/api/a.py
@@ -1 +1 @@
-a
+b
diff --git a/web/b.py b/web/b.py
--- a/web/b.py
+++ b/web/b.py
@@ -1 +1 @@
-a
+b
"""
    assert guess_scope(parse_diff(diff)) == ""


def test_breaking_change_detecte():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
+BREAKING CHANGE: API modifiée
"""
    assert parse_diff(diff).is_breaking is True


def test_changed_symbols():
    assert "parse_feed" in changed_symbols(SAMPLE_DIFF)


def test_diff_vide():
    analysis = parse_diff("")
    assert analysis.files == []
    assert analysis.added == 0


# --------------------------------------------------------------------------- #
# Message
# --------------------------------------------------------------------------- #
def test_message_local_conventionnel():
    analysis = parse_diff(DOCS_DIFF)
    result = suggest(analysis, DOCS_DIFF)
    assert result["message"].startswith("docs")
    assert result["generated_by"] == "rules"


def test_message_avec_scope_et_corps():
    analysis = parse_diff(SAMPLE_DIFF)
    message = build_message(analysis, "gérer les flux sans namespace", ["- src/parser.py"])
    assert message.splitlines()[0].startswith(analysis.commit_types[0])
    assert "gérer les flux sans namespace" in message


def test_validate_ok():
    assert validate("feat(api): ajouter un endpoint") == []


def test_validate_signale_point_final():
    assert any("point" in p for p in validate("feat: ajouter un endpoint."))


def test_validate_signale_type_inconnu():
    assert validate("bonjour tout le monde") != []


def test_validate_message_vide():
    assert validate("") == ["message vide"]


def test_message_llm_simule(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "subject": "feat(parser): gérer les flux RSS sans namespace",
        "body": ["ajout de parse_feed", "suppression de old"]})
    result = suggest(parse_diff(SAMPLE_DIFF), SAMPLE_DIFF)
    assert result["generated_by"] == "llm"
    assert result["message"].startswith("feat(parser):")


def test_message_repli_si_llm_renvoie_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: None)
    assert suggest(parse_diff(SAMPLE_DIFF), SAMPLE_DIFF)["generated_by"] == "rules"


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #
@pytest.fixture()
def projet(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_x():\n    assert True\n",
                                                    encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests>=2\npytest\n", encoding="utf-8")
    return tmp_path


def test_scan_projet(projet: Path):
    info = scan_project(projet)
    assert info["languages"][0] == ".py"
    assert info["has_tests"] is True
    assert "requests" in info["dependencies"]


def test_readme_contient_les_sections(projet: Path):
    content = generate_readme(projet, use_llm=False)["content"]
    for heading in ("# ", "## Installation", "## Utilisation", "## Structure",
                    "## Tests", "## Licence"):
        assert heading in content


def test_readme_ignore_dossiers_techniques(projet: Path):
    (projet / "node_modules").mkdir()
    (projet / "node_modules" / "x.js").write_text("", encoding="utf-8")
    info = scan_project(projet)
    assert "node_modules" not in " ".join(info["structure"])


def test_readme_llm_simule(projet: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "description": "Un outil de démonstration.",
        "features": ["scanne", "documente"],
        "install": "```bash\npip install -e .\n```",
        "usage": "```bash\npython -m app\n```"})
    result = generate_readme(projet)
    assert result["generated_by"] == "llm"
    assert "Un outil de démonstration." in result["content"]
    assert "## Fonctionnalités" in result["content"]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_llm(capsys):
    assert main(["llm"]) == 0
    assert "Fournisseur" in capsys.readouterr().out


def test_cli_readme_ecrit_le_fichier(projet: Path, capsys):
    code = main(["readme", str(projet), "--no-llm"])
    assert code == 0
    assert (projet / "README.md").exists()


def test_cli_readme_refuse_ecrasement(projet: Path, capsys):
    (projet / "README.md").write_text("existant", encoding="utf-8")
    assert main(["readme", str(projet), "--no-llm"]) == 1
    assert main(["readme", str(projet), "--no-llm", "--force"]) == 0


def test_cli_readme_json(projet: Path, capsys):
    assert main(["readme", str(projet), "--no-llm", "--json"]) == 0
    import json
    assert json.loads(capsys.readouterr().out)["generated_by"] == "rules"


@needs_git
def test_cli_commit_sur_vrai_depot(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], check=True, capture_output=True)
    assert main(["commit", "--no-llm", "--json"]) == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert payload["message"].startswith(("feat", "chore", "build"))
    assert payload["problems"] == []


@needs_git
def test_cli_commit_sans_changement(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True, capture_output=True)
    assert main(["commit"]) == 1
    assert "aucun changement" in capsys.readouterr().out


@needs_git
def test_cli_commit_hors_depot(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["commit"]) == 2
