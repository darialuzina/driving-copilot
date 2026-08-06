# Prompts for common task types

Each file contains **two path variants**:

| Variant | When to use | Path example |
|---------|-------------------|-------------|
| **A — submodule in a project** | ai-sdlc-rules is included as `.agents/` | `.agents/AGENTS.md` |
| **B — running from ai-sdlc-rules** | the agent runs directly in the ai-sdlc-rules folder | `AGENTS.md` |

## Full development cycle

| File | Task |
|------|--------|
| `architecture.md` | Write an architecture document before implementation |
| `feature.md` | Implement a new feature |
| `bugfix.md` | Fix a bug |
| `hotfix.md` | Urgent fix to production |
| `refactoring.md` | Refactoring without behavior changes |
| `tests-unit.md` | Write unit tests |
| `tests-integration.md` | Write integration tests |
| `code-review.md` | Perform a code review |
| `mr.md` | Prepare a Merge Request description |
| `commit.md` | Make a commit following the rules |
| `orchestrate.md` | Orchestrate Coder→Reviewer→Summarizer |
