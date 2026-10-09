# Production deploy (VPS with Traefik)

`deploy/docker-compose.yml` runs ChatDev 2.0 behind the Traefik reverse proxy
of a Hostinger "Ubuntu + Docker + Traefik" VPS (any Traefik with a
`websecure` entrypoint and a `letsencrypt` cert resolver works):

- `backend`: the FastAPI server built from the root `Dockerfile`.
- `web`: the production build of the web console on nginx. It proxies `/api`,
  `/ws` and `/health` to the backend and puts everything behind HTTP basic auth.
  It refuses to start without `CHATDEV_PASSWORD`, because agents execute code
  on the server.

Both images are built straight from Git, so no checkout is needed on the VPS.
Workflow outputs (`WareHouse/`), the workflow database (`data/`) and logs live
in named volumes and survive redeploys.

## Deploy with Hostinger Docker Manager

Create a project named `chatdev` from the contents of `deploy/docker-compose.yml`
with this environment:

| Variable | Example | Notes |
|---|---|---|
| `CHATDEV_HOST` | `chatdev.srv1234567.hstgr.cloud` | Main hostname; Let's Encrypt cert via Traefik |
| `CHATDEV_ALT_HOST` | `chatdev.example.com` | Optional second hostname (DNS A record to the VPS IP) |
| `CHATDEV_USER` | `admin` | Login user |
| `CHATDEV_PASSWORD` | (strong random) | Login password, required |
| `BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `API_KEY` | | LLM API key used by the `${API_KEY}` placeholders in workflows |
| `CHATDEV_GIT` | `https://github.com/jowikroon/ChatDev.git#main` | Git build context (repo#branch) |

Redeploying the project rebuilds from the branch in `CHATDEV_GIT`.

## Run locally with the same stack

```bash
CHATDEV_GIT=. CHATDEV_PASSWORD=change-me API_KEY=sk-... \
  docker compose -f deploy/docker-compose.yml up --build
```
Without Traefik there is no published port. For local use, `make dev` is simpler.
