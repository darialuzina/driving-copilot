# Hotfix rules

1. First, minimize the scope of the change.
2. Use a dedicated Jira branch in the format `hotfix/<JIRA-KEY>-<short-description>`.
3. Always add a regression test.
4. Do no extra refactoring inside a hotfix.
5. Record exactly what was fixed and how to roll the change back.

## Additionally

- Change only what is needed to fix the incident.
- Do not mix a hotfix with unrelated cleanup.
- After the fix, always verify that the bug does not recur.
