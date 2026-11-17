# ⚒️ commit-smith

**Générez des messages de commit conventionnels en une commande — et un README pro à
partir de n'importe quel dossier.**

`commit-smith` lit votre `git diff`, en déduit le type (`feat`, `fix`, `docs`, …), le
périmètre et une description claire, puis vous propose le message. Il sait aussi scanner
un projet et écrire un `README.md` complet (titre, description, installation, usage,
structure, tests).

Deux modes :
- **hors ligne** : analyse par règles (aucune clé, aucun appel réseau) ;
- **avec IA** : Claude, OpenAI ou **Ollama en local** pour des messages plus naturels.

---

## Installation

```bash
pip install -e .          # ou : pip install git+https://github.com/<vous>/commit-smith.git
```

Python 3.9+. Zéro dépendance obligatoire.

## Utilisation

```bash
# Message de commit à partir des changements indexés (git add)
commit-smith commit

# Tout ce qui a changé depuis le dernier commit (indexé ou non)
commit-smith commit --all

# Écrire directement le commit (après confirmation)
commit-smith commit --apply

# Comparer deux branches / un commit
commit-smith commit --from main --to feature

# Générer un README pour le dossier courant
commit-smith readme --out README.md

# Vérifier la configuration IA
commit-smith llm
```

Options utiles :

| Option | Effet |
|---|---|
| `--apply` | exécute `git commit -m "…"` après confirmation |
| `--yes` | ne demande pas de confirmation (avec `--apply`) |
| `--no-llm` | force l'analyse par règles |
| `--json` | sortie machine |
| `--max-chars` | longueur maximale du sujet (défaut 72) |

## Convention respectée

```
<type>(<scope>): <description>

<corps optionnel>

<breaking change optionnel>
```

Types : `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore`, `revert`.

## Brancher une IA

```bash
# Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Ollama, 100 % local
export OLLAMA_MODEL="llama3.2"      # ollama serve doit tourner
```

Sans clé, l'outil fonctionne quand même (mode règles). Si l'appel échoue, il retombe
automatiquement sur ce mode.

## Exemple de sortie

```
$ commit-smith commit --all
──────────────────────────────────────────────────────────────
 2 fichier(s), +48 −3   [rules]
──────────────────────────────────────────────────────────────
feat(parser): gérer les flux RSS sans namespace

- src/parser.py
- tests/test_parser.py
──────────────────────────────────────────────────────────────
✔ conforme aux Conventional Commits
```

## Tests

```bash
python -m pytest -q
```

25 tests verts ; les 3 tests qui pilotent un vrai dépôt git sont ignorés si `git` n'est
pas installé sur la machine.

## Licence

MIT — voir [LICENSE](LICENSE).
