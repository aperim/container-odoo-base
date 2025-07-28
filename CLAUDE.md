# CLAUDE.md

Authoritative operating contract for **Claude Code** inside this VS Code **DevContainer** (Ubuntu-based, Docker-enabled, full internet).

> These guidelines override any default Claude Code behavior unless the user explicitly requests otherwise.

---

## 0 · Claude Code Workflow (FOLLOW EVERY SESSION)

1. **Sync workspace state**  
   ```bash
   git fetch --all --prune
   ```

2. **Ensure safe branch**
   - If `git rev-parse --abbrev-ref HEAD` equals `main` (or `master`), create `claude/<topic>-$(date +%Y%m%d%H%M%S)` and switch to it **before** making any edits.
   - Use descriptive branch names that reflect the task being performed.

3. **Apply user instructions with extended thinking**
   - Use extended thinking for complex tasks by adding phrases like "think step by step" or "think harder about edge cases"
   - Make code changes **and** update all referenced documentation *concurrently*
   - Always explain your approach before executing commands

4. **Quality gates** (stop on failure)
   - Run formatter/linter: `just fix`, `npm run lint`, `prettier --write .`, etc.
   - Run test suite: `pytest`, `npm test`, `cargo test`, `go test ./...`
   - For containers: `docker compose build && docker compose up --exit-code-from sut`
   - Check for TypeScript/compilation errors if applicable

5. **Stage & commit with conventional commits**
   ```bash
   git add -A
   git commit -m "<type>(scope): summary

   Longer context explaining the changes

   Closes #123"
   ```
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Keep summary under 50 chars, body wrapped at 72 chars

6. **Push branch**
   ```bash
   git push --set-upstream origin $(git symbolic-ref --short HEAD)
   ```
   - If push fails (new repo), create the remote branch and retry
   - Use `gh repo create` if repository doesn't exist

7. **Confirmation**
   - Print `CLAUDE_COMMIT_DONE_<short-sha>` when complete
   - If no files changed, print `CLAUDE_NO_CHANGE` instead

---

## 1 · Execution Environment

| Capability              | Status                                                                     |
|------------------------|---------------------------------------------------------------------------|
| Internet + DNS + TLS   | **ENABLED** – Full web access via WebFetch and WebSearch tools          |
| GitHub REST/GraphQL    | **ENABLED** – Token via `GITHUB_TOKEN` environment variable             |
| Shell commands         | **UNRESTRICTED** – All bash commands pre-approved in settings           |
| Docker-in-Docker       | **ENABLED** – Full Docker CLI access                                    |
| File operations        | **UNRESTRICTED** – Read, Write, Edit, MultiEdit all pre-approved        |
| Package managers       | **ENABLED** – npm, yarn, pnpm, pip, cargo, go, etc.                    |
| CI/CD tools           | **ENABLED** – gh CLI, docker, kubectl, terraform, etc.                 |

*All permissions are pre-configured in `.claude/settings.json` - no confirmation prompts needed.*

---

## 2 · Documentation & Communication

- **Update docs as you go**, not after
- If code changes affect documentation, update docs in the same commit
- Maintain changelogs (`CHANGELOG.md`) and release notes if they exist
- **Explain your reasoning** before executing complex operations
- Use **extended thinking** for architectural decisions and complex debugging
- When encountering errors, explain what went wrong and your fix strategy

---

## 3 · Git & Branch Strategy

- **Never commit directly to `main`/`master`**
- Use semantic branch names: `claude/feature-name`, `claude/fix-bug-name`
- Prefer atomic commits with clear, descriptive messages
- Use conventional commit format for consistency
- Squash/rebase only if explicitly requested or required by repo policy

---

## 4 · GitHub Integration

- Use `gh` CLI for GitHub operations when available
- **GraphQL v4** preferred for complex operations (batched mutations)
- Common workflows:
  - Create PR: `gh pr create --title "feat: summary" --body "description"`
  - Link issues: Reference `#123` in commit messages
  - Apply labels and assign reviewers as appropriate
- After successful push and tests, offer to create PR unless told otherwise

---

## 5 · Tool Preferences & Commands

| Task                    | Preferred Command(s)                                    |
|------------------------|--------------------------------------------------------|
| Code formatting        | `prettier --write .`, `black .`, `cargo fmt`, `gofmt` |
| Linting               | `eslint --fix`, `ruff check --fix`, `clippy`          |
| Testing               | `npm test`, `pytest -v`, `cargo test`, `go test -v`   |
| Type checking         | `tsc --noEmit`, `mypy .`, `cargo check`               |
| Dependency updates    | `npm audit fix`, `cargo update`, `go mod tidy`        |
| Container operations  | `docker compose up --build`, `docker system prune`   |
| Search/navigation     | `rg`, `fd`, `fzf` (if available)                      |

**Always prefer repo-local scripts** (`just`, `make`, `npm scripts`, `task`) when they exist.

---

## 6 · Claude Code Specific Features

### Extended Thinking
- Use extended thinking for complex problems: "think step by step about..."
- Trigger deeper analysis with: "think harder", "think more", "analyze thoroughly"
- Extended thinking shows as italic gray text - very valuable for debugging

### Slash Commands
- Available custom commands in `.claude/commands/` directory
- Type `/` to see available project-specific commands
- Create reusable workflows as markdown files with `$ARGUMENTS` placeholders

### Memory & Context
- This CLAUDE.md file provides persistent context across sessions
- Reference project-specific patterns and conventions established here
- When resuming work, use `--continue` to maintain conversation context

### MCP Integration
- If MCP servers are configured, use them for specialized tasks
- GitHub MCP server for advanced repository operations
- Filesystem MCP for file operations outside current directory

---

## 7 · Error Handling & Recovery

- **Always explain errors** before attempting fixes
- For permission errors: Check if tool is in allowed list in `.claude/settings.json`
- For git conflicts: Explain strategy before resolving
- For test failures: Analyze output and explain fix approach
- For dependency issues: Show dependency tree and explain resolution

---

## 8 · Precedence & Guidelines

1. **User instructions > This CLAUDE.md > Claude Code defaults**
2. **Later sections in this file supersede earlier ones**
3. **When uncertain, explain your reasoning and ask for clarification**
4. **Safety first**: Even with broad permissions, explain destructive operations
5. **Transparency**: Always show what commands you're running and why

---

## 9 · Type Safety Requirements

**MANDATORY**: If the language supports static typing, **TYPE EVERYTHING** with maximum detail.

### TypeScript/JavaScript
- **NO `any` types** - Use specific types, unions, or `unknown` if truly necessary
- Define interfaces for all objects, even small ones
- Use generic constraints: `<T extends string>` not just `<T>`
- Prefer `as const` assertions for literal types
- Example of good typing:
```typescript
interface UserPreferences {
  readonly theme: 'light' | 'dark' | 'auto';
  readonly notifications: {
    email: boolean;
    push: boolean;
    frequency: 'immediate' | 'daily' | 'weekly';
  };
}

function updatePreferences<K extends keyof UserPreferences>(
  key: K, 
  value: UserPreferences[K]
): Promise<UserPreferences> { /* ... */ }
```

### Python
- Use type hints for **everything**: functions, variables, class attributes
- Import from `typing` extensively: `Union`, `Optional`, `Literal`, `TypedDict`
- Use `dataclasses` or `pydantic` for structured data
- Example:
```python
from typing import Protocol, TypeVar, Generic, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    ssl_mode: Literal['require', 'prefer', 'disable']

T = TypeVar('T', bound='Serializable')

class Serializable(Protocol):
    def to_dict(self) -> dict[str, Any]: ...
```

### Other Languages
- **Rust**: Use specific types, avoid `Box<dyn Any>`
- **Go**: Define structs for all data, use interfaces properly
- **C#/Java**: Full generic constraints, no `Object` parameters
- **Swift**: Use optionals properly, avoid `Any`

**Rule**: If you find yourself reaching for `any`/`Any`/`object`, stop and define proper types.

---

## 10 · Ephemeral Services & Docker

**You have FULL permission** to spin up any services needed for development/testing using Docker.

### Common Ephemeral Services
```bash
# Redis for caching/sessions
docker run --rm -d -p 6379:6379 --name temp-redis redis:alpine

# PostgreSQL for database testing
docker run --rm -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=dev \
  -e POSTGRES_DB=testdb \
  --name temp-postgres postgres:15-alpine

# MongoDB for document storage
docker run --rm -d -p 27017:27017 --name temp-mongo mongo:7

# MySQL for relational testing
docker run --rm -d -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=dev \
  -e MYSQL_DATABASE=testdb \
  --name temp-mysql mysql:8

# Elasticsearch for search testing
docker run --rm -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  --name temp-elasticsearch elasticsearch:8.11.0

# MinIO for S3-compatible storage
docker run --rm -d -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  --name temp-minio minio/minio server /data --console-address ":9001"
```

### Service Management Protocol
1. **Always use `--rm`** - containers auto-cleanup when stopped
2. **Use `temp-` prefix** for container names to indicate ephemeral nature
3. **Document connection details** in commit message or comments
4. **Clean up explicitly** when done:
   ```bash
   docker stop temp-redis temp-postgres temp-mongo
   # --rm handles deletion automatically
   ```

### Testing Workflows with Services
- Spin up services **before** running tests that need them
- Use health checks to ensure readiness:
   ```bash
   # Wait for PostgreSQL to be ready
   until docker exec temp-postgres pg_isready; do sleep 1; done
   ```
- Include service setup in test scripts when appropriate
- **Never assume services exist** - always create them fresh

### Docker Compose for Complex Setups
For multi-service scenarios, create temporary `docker-compose.test.yml`:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: testdb
    ports: ["5432:5432"]
  redis:
    image: redis:alpine
    ports: ["6379:6379"]
```

Then: `docker compose -f docker-compose.test.yml up -d`

**Remember**: Full Docker access is available - use it liberally for isolated testing!

---

## 11 · Development Environment Notes

- **Shell**: Using zsh (not bash) with full alias/function support
- **Container**: DevContainer with full Docker access and Docker-in-Docker
- **Permissions**: Pre-approved for all common development operations
- **Network**: Full internet access for documentation, packages, APIs
- **IDE**: VS Code with extensions and settings available
- **Services**: Can spin up any ephemeral Docker services as needed
- **Typing**: Mandatory comprehensive typing for all typed languages