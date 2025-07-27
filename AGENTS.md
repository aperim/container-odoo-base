<!--
╔══════════════════════════════════════════════════════════════════╗
║  FULL‑FILE READ REQUIREMENT                                      ║
║                                                                  ║
║  Before doing ANY work Codex MUST:                                ║
║    1. Count the exact number of lines in *this* file             ║
║       (blank lines included, this block included).               ║
║    2. Print ONE line to stdout in this form—                     ║
║                                                                  ║
║           AGENTS_LINES_<TOTAL>                                   ║
║                                                                  ║
║       where <TOTAL> is the line count it just computed.          ║
║    3. Abort with a non‑zero exit code if that line is absent     ║
║       or the count is wrong.                                     ║
╚══════════════════════════════════════════════════════════════════╝
-->

# AGENTS.md
Purpose‑built instructions for OpenAI Codex when running **inside this VS Code DevContainer**.  
These rules **override** any broader‐scope `AGENTS.md` files but are still subordinate to an
explicit user prompt.

---

## 1. Execution Environment

| Capability                | Status in this container |
| ------------------------- | ------------------------ |
| Internet / DNS / TLS      | **Enabled** – outbound and inbound allowed. |
| GitHub API (REST & GQL)   | **Enabled** – authenticate with `CODEX_GITHUB_TOKEN` or, if absent, `GITHUB_TOKEN`. |
| Shell & process exec      | **Enabled** – unrestricted by Seatbelt/Landlock. |
| File‑system write         | **Enabled** in the repo working tree. |
| Docker                    | **Enabled** use `docker` commands for container management. |
| GPU                       | Available. |

> **Implication:** *Do **not** assume `CODEX_SANDBOX_NETWORK_DISABLED=1`; the variable will not be set here. Skip any network‑avoidance fall‑backs.*

---

## 2. Branch‑safety Rules

1. **Never commit to `main`.**  
   *If the current HEAD is `main`, first create*  
   `codex/<keyword>-<YYYYMMDD>-<slug>`  
   before touching files or running generators.

2. If you are already on a non‑main branch, continue work there.

3. Every change set **must be committed** (and pushed if credentials permit)
   **before** the agent yields control at the end of its run.  
   Follow the conventional commit template:

```

<type>(scope): concise summary

Longer description explaining *why* rather than *what*,
followed by any BREAKING CHANGE or issue/PR references.

````

---

## 3. Documentation Synchronisation

* **Live‑update docs.** When a code/file change alters behaviour, update the
relevant Markdown, code headers, or GitHub Issue/PR description **in the
same task**, not afterwards.
* Respect any `--doc-path` or “update the spec in #123” instructions that the
user supplies.
* Run spell‑check/linters on docs if the repo provides them.

---

## 4. GitHub Workflow Automation

* Use the **GraphQL API** for:
* creating / updating Issues & PRs,
* adding comments, labels, reviewers,
* checking build‑status queries.
* Prefer batched GraphQL mutations for speed.
* Authenticate with:
```bash
export GH_TOKEN="${CODEX_GITHUB_TOKEN:-$GITHUB_TOKEN}"
````

* Push branches with `--set-upstream origin <branch>` so subsequent runs know
  where to commit.

---

## 5. Tooling Guidance for Codex

* You **can** run linters, tests, package managers (Yarn, Cargo, etc.).
* Feel free to download dependencies or call external APIs; bandwidth is not
  sandboxed.
* Honour repo‑local config: `.editorconfig`, `justfile`, `pre‑commit`, etc.
* Do **not** add or modify any code that special‑cases
  `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`; it is **irrelevant** here.

---

## 6. Quality Gates

1. **All tests green** (`cargo test`, `pytest`, `npm test`…)
   Commit fails should abort the run.
2. **Static checks** (`just fix`, `just fmt`, `eslint --fix`, etc.) must pass.
3. Use the repo’s CI config (if any) as the source‑of‑truth – run it locally when practical.

---

## 7. Etiquette & Precedence

* Obey direct user instructions first.
  If unclear, ask a clarifying question **once** before proceeding.
* If multiple `AGENTS.md` files conflict, the *closest one in the directory
  tree wins* (per upstream spec).
  This file is at repo root, so only nested files may override it.
