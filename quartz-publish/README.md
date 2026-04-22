# Quartz Publishing

This folder turns the generated wiki in `research-wiki/wiki/` into a Quartz site
and deploys it to GitHub Pages.

## How it works

- `prepare-build.sh` clones the official Quartz `v4` repo into `.quartz-build/`
  and syncs `research-wiki/wiki/` into Quartz's `content/` folder.
- `quartz.config.ts` and `quartz.layout.ts` override Quartz defaults so the
  published site looks like this project instead of Quartz's demo site.
- `.github/workflows/deploy-quartz-pages.yml` builds and deploys the static site
  to GitHub Pages on every push to `main`.

## Local preview

```bash
cd llm-wiki-mcp
./quartz-publish/preview.sh
```

Quartz serves the site locally on `http://localhost:8080`.

## GitHub Pages setup

1. Push this repo to GitHub.
2. In GitHub, open `Settings -> Pages`.
3. Set `Source` to `GitHub Actions`.
4. Optional: add repository variables under `Settings -> Secrets and variables -> Actions`.

Useful repository variables:

- `QUARTZ_BASE_URL`
  Example: `christian-mcp.github.io/llm-wiki-mcp`
- `QUARTZ_SITE_TITLE`
  Example: `MCP Research Wiki`

If you do not set `QUARTZ_BASE_URL`, the workflow defaults to the standard
project Pages URL for the current repo.

## What gets published

Only the compiled wiki in `research-wiki/wiki/` is published.

Do not publish:

- `research-wiki/raw/`
- `research-wiki/.wiki/`
