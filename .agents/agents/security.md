# Security policy

## Secrets

- `AGENTPLATFORM_API_KEY`, DB tokens, passwords — **only in `~/.zshenv` or `.env`** (which is in `.gitignore`).
- The key **never lands** in code, configs, tests, or documentation — always `os.environ["AGENTPLATFORM_API_KEY"]` or substitution via `${AGENTPLATFORM_API_KEY}` in templates.
- In Continue, the key is set via the secret placeholder `${{ secrets.AGENTPLATFORM_API_KEY }}`, not written in directly.
- If a key leaks (into git history, into Slack, into a screenshot) — immediately **disable** it in AgentPlatform Settings → Keys and create a new one.
- Every key gets its own credit limit (the minimum, sized exactly for the task). The default workshop key — $5.

## Bandit

- `bandit` runs on every commit via pre-commit (see Step 5.2).
- If bandit found a problem in someone else's code (not in the current diff) — make a **separate commit** `[manual] fix(security): <description in English>`, then the regular feature commit (tag, scope, and description all in English).
- No `# nosec` without a comment explaining **why** this specific construct is safe in this context.

## pip-audit

- `pip-audit` runs on every commit via pre-commit (see Step 5.2).
- For every CVE in a dependency — a separate commit `[manual] chore(deps): update <package> to X.Y.Z for CVE-XXXX-XXXXX` (tag, scope, and description all in English).
- Do not mix a security fix with a feature in one commit.

## Pre-commit hooks — no bypasses

The list of **forbidden** ways to bypass pre-commit checks. They all produce the same thing — a commit with unverified code. They must not be used under any circumstances:

- `git commit --no-verify` — skips all hooks entirely.
- `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit ...` — skips the hooks when the config is missing. If you see this variable in a command, the config is **lost** (e.g. it was untracked and got swept into `git stash -u`). The response is to **restore the config**, not to bypass.
- `SKIP=hook1,hook2 git commit ...` — skips the listed hooks. Never: a failing hook gets fixed, not switched off.
- `pre-commit uninstall` to "disable temporarily" — removes the hook altogether. Restore via `pre-commit install` after fixing.

If a hook fails on someone else's code unrelated to your task — make a **separate security commit** before your feature (the "one commit per CVE" policy above). Never a bypass.

If `.pre-commit-config.yaml` is physically missing from the project — **stop**, restore the file from git history (`git show HEAD:.pre-commit-config.yaml > .pre-commit-config.yaml`) or from the stash, and only then continue.

## Dangerous constructs — do not use

- `eval` / `exec` on user input.
- `subprocess.run(..., shell=True)` — only an argument list without a shell.
- `yaml.load(...)` without `Loader=yaml.SafeLoader` — only `yaml.safe_load`.
- Hardcoded passwords / API keys / connection strings.
- `pickle.loads` from an untrusted source.

***

## Python security patterns — extended set

These are **applied** patterns: what most often breaks in Python services and how to avoid it. bandit catches some of them, but not all — so the rules are written down explicitly, and the agent references them in code review.

### 1. SSRF (Server-Side Request Forgery)

When a service makes an outbound HTTP request to a URL that the user **partially or fully controls** (link preview, webhook URL, RSS import, OAuth callback, image proxy), it is a potential SSRF.

**Attack:** the user supplies a URL like `http://169.254.169.254/latest/meta-data/...` (AWS metadata), `http://10.0.0.5:6379/` (internal Redis), `http://localhost:9090/` (an internal admin endpoint).

**Rules:**

- Allow-list of schemes (`http`, `https`) — no `file://`, `gopher://`, `ftp://`.
- **DNS resolve → check by IP**, not by hostname (protection against DNS rebinding). Reject `ip.is_private / is_loopback / is_link_local / is_multicast / is_reserved`.
- Disable redirects (`follow_redirects=False`) or validate every intermediate URL against the same rules.
- A strict `httpx.Timeout(connect, read, write, pool)`, a `max_bytes` cap on the response (streamed, not loaded into memory whole).

~~~python
import ipaddress
import socket

import httpx

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_BYTES = 10 * 1024 * 1024


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def fetch_preview(url: str) -> bytes:
    parsed = httpx.URL(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("scheme not allowed")
    infos = socket.getaddrinfo(parsed.host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    ips = {info[4][0] for info in infos}
    if not all(_is_public_ip(ip) for ip in ips):
        raise ValueError("resolved to non-public ip")
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > _MAX_BYTES:
                    raise ValueError("response too large")
            return bytes(buf)
~~~

### 2. Path traversal

When a file path is built from user input (upload, download by name, read template by id) — the attacker passes `../../../../etc/passwd`.

**Rules:**

- Resolve and verify containment in the root directory: `Path.resolve()` + `is_relative_to(root)` (Python 3.9+).
- Allow-list of characters in the name, where possible (`^[a-zA-Z0-9._-]+$`).
- No `..` and no absolute paths in the name — reject immediately.

~~~python
from pathlib import Path

_UPLOADS = Path("/var/uploads").resolve()


def read_user_file(name: str) -> str:
    candidate = (_UPLOADS / name).resolve()
    if not candidate.is_relative_to(_UPLOADS):
        raise ValueError("path traversal attempt")
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate.read_text(encoding="utf-8")
~~~

### 3. Unsafe deserialization

`pickle`, `yaml.load` without `SafeLoader`, `xml.etree` with external entities, `jsonpickle` — they **execute code** on untrusted input.

| Format | Untrusted input | Trusted input |
|---|---|---|
| `pickle` / `marshal` / `shelve` / `dill` | **Never** | Only for your own controlled data |
| `yaml.load()` | **Never** | `yaml.safe_load()` always |
| `xml.etree.ElementTree` / `lxml` without `resolve_entities=False` | **Never** (XXE) | `defusedxml` or explicitly disable external entities |
| `jsonpickle` | **Never** | `pydantic` or `dataclasses_json` |
| `eval` / `exec` on user input | **Never** | `ast.literal_eval()` for a safe subset |

### 4. File upload — hardening

When accepting a file from a user:

- **Check the MIME type by content**, not by the `Content-Type` header (it comes from the client — untrusted). Via `python-magic` / `magic.from_buffer(raw, mime=True)`.
- Cap the size **before** the file lands in memory — streaming read with early reject.
- Sanitize the filename or **generate a new one** (UUID). Never use the raw name for a path on disk.
- Store **outside the webroot**; serve through a controller with authorization.
- For images — re-encode via Pillow (`Image.verify()` + reopen + `convert("RGB")` + `save`). This strips payloads embedded in exif / metadata / polyglot formats.

### 5. TLS verification — never disable

~~~python
# ❌ MITM-vulnerable
httpx.get(url, verify=False)
requests.get(url, verify=False)
~~~

**Acceptable** to disable only: (1) in tests against a local mock server (explicit `# noqa` + comment), (2) for an internal CA — `verify="/path/to/internal-ca.pem"`, **not** `False`.

### 6. Request timeouts — always

`requests.get(url)` without `timeout=` is an anti-pattern. The request can hang forever, the GIL thread stalls; in async — the task never releases the event loop.

~~~python
# ✅ requests
r = requests.get(url, timeout=(2.0, 10.0))  # (connect, read)

# ✅ httpx
timeout = httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)
async with httpx.AsyncClient(timeout=timeout) as client:
    r = await client.get(url)
~~~

### 7. JWT / OAuth

**JWT:**

- **Never trust `alg: none`** — explicit reject.
- On `decode`, specify the **expected** algorithm: `algorithms=["RS256"]`, not a wildcard.
- Verify `exp` / `nbf` / `iat` / `aud` / `iss` — especially in multi-tenant setups.
- Keys in KMS / vault, not in `.env` for prod.
- In the payload — **identifiers only** (sub, aud, iss). No secrets: the payload is base64, not encrypted.

~~~python
import jwt
from jwt.exceptions import InvalidTokenError

try:
    payload = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="my-service",
        issuer="https://auth.example.com/",
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )
except InvalidTokenError as e:
    raise AuthError("invalid token") from e
~~~

**OAuth:**

- **PKCE** is mandatory for public clients (mobile, SPA).
- **`state`** is mandatory (CSRF protection for the authorization request).
- `redirect_uri` — exact match against an allow-list (not a prefix, not a substring).
- `nonce` in the OIDC `id_token`.
- `refresh_token` — **never** in the browser. Public clients: PKCE + short-lived access_token.

### 8. Subprocess sandboxing

- **`shell=False`** always. `subprocess.run([prog, arg1, arg2], ...)`, not a string.
- **Never interpolate user input into a command string** — only into the args list.
- Absolute path to the binary or `which` — don't trust PATH.
- A strict `timeout=`.
- Restrict the environment: `env={"PATH": "/usr/bin"}`, don't pass the whole `os.environ`.

~~~python
# ❌ injection
subprocess.run(f"convert {user_file} out.jpg", shell=True)

# ✅
CONVERT = "/usr/bin/convert"
subprocess.run(
    [CONVERT, str(user_file), str(out)],
    check=True,
    timeout=30,
    capture_output=True,
    env={"PATH": "/usr/bin"},
)
~~~

### 9. Secure temp files

- `tempfile.NamedTemporaryFile` / `TemporaryDirectory()` — context manager, auto-cleanup.
- **Never `tempfile.mktemp()`** — race condition (the name is returned before the file is created).
- No `/tmp/work_{os.getpid()}.txt` — a predictable path = race condition + permission tricks.

### 10. Cryptography

- **Never** write your own crypto. `cryptography` (the standard API); `hazmat` — only with code review.
- **Never `hashlib.md5` / `sha1` for security** (passwords, tokens, signatures). They are for checksums, not for security.
- Passwords: `passlib.hash.bcrypt` or `argon2-cffi`.
- HMAC / secret comparison: `hmac.compare_digest(a, b)` (constant-time), **not** `a == b` (timing attack).
- Randomness for security: `secrets.token_urlsafe(32)` / `secrets.SystemRandom`, **not** `random` (predictable).

~~~python
import hmac
import secrets


def make_token() -> str:
    return secrets.token_urlsafe(32)


def verify_token(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())
~~~

***

## What this file does NOT cover

- **Authorization / authentication at the design level** (RBAC vs ABAC, multi-tenant boundaries) — that is ADR territory (`.agents/agents/docs.md`), not code style.
- **Threat modeling, pentest playbook** — a separate discipline, beyond the scope of the workshop.
- **IaC security** (S3 Block Public Access, IAM wildcards, security groups) — beyond the scope of the project.
