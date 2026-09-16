# uv Workspaces

Local `uv` version at scaffold time: `0.10.2`.

## Pattern used in this repo

Root `pyproject.toml` is a **virtual workspace root** — it declares
members but is not itself an installable package:

```toml
[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*", "apps/server"]

[dependency-groups]
dev = [
    "soft-floyd-core",
    "soft-floyd-server",
    ...
]

[tool.uv.sources]
soft-floyd-core = { workspace = true }
soft-floyd-server = { workspace = true }
```

Each member (`packages/core`, `apps/server`) has its own `pyproject.toml`
with its own `[project.dependencies]` and, for `apps/server`, a
`[project.scripts]` entry point (`soft-floyd = "soft_floyd_server.cli:app"`).

`apps/web` is intentionally **not** a uv workspace member — it's a
separate pnpm-managed package; see `pnpm-workspace.yaml` at the repo
root for the JS side.

## Commands

- `uv sync` from the repo root installs every workspace member plus the
  root's `dev` dependency group into one shared `.venv`.
- `uv run <cmd>` runs against that shared venv regardless of which
  member's directory you're in.
- Adding a new workspace member: create `<path>/pyproject.toml`, add the
  path to `[tool.uv.workspace].members`, and if another member depends on
  it, add a `[tool.uv.sources]` entry with `{ workspace = true }`.
