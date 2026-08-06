# Skill: Docs

## Documentation algorithm within a task

### 1. Before implementation
- Determine whether the task touches the public API (new endpoint, service method, ENV, dependency).
- Determine whether the decision is architectural (multiple modules, a new tool, a change of approach).
- If it is architectural — **create an ADR before writing code**: it forces you to articulate Context and Decision before drowning in the implementation.

### 2. During implementation
- Write the docstring together with the function signature, before the body. This aligns names, parameters, and expectations.
- Format:

```python
async def create_link(target_url: str) -> Link:
    """Create a short link with an auto-generated code.

    Args:
        target_url: Target URL. Must be a syntactically valid http/https URL.

    Returns:
        A new Link entity with a unique short code.

    Raises:
        InvalidUrlError: If target_url is empty or not a valid http/https URL.
    """
```

### 3. After implementation
- Update `CHANGELOG.md` under `[Unreleased]`: pick the section (Added / Changed / Fixed / Removed / Security) and write one line in user-facing style. Example: `- Fixed 500 on POST /links with url > 2048 chars (PROJ-202)`.
- If any of these changed: an ENV variable, the launch command, a dependency, the endpoint list — **update the corresponding section of README.md**.
- If an ADR was created — add a link to it from README (in the Architecture section).

### 4. ADR template

```markdown
# NNNN — <short decision title>

## Status

Accepted

## Context

<What is the problem? What constraints, requirements, and forces pushed on the decision?>

## Decision

<What exactly was decided. One or two crisp sentences.>

## Consequences

<What gets better? What gets worse? Which risks remain accepted?>

## Alternatives considered

- <Alternative 1>: why it was not chosen.
- <Alternative 2>: why it was not chosen.
```
