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

Hostinger Docker Manager pulls images but does not build them, so use
`deploy/compose.hostinger.yml`: it runs public images only (uv/Python, Node,
nginx) and fetches the code from Git on start. The first start takes several
minutes (dependency install + frontend build); restarting the project pulls
the latest commit of `CHATDEV_REF`. Hosts that can build images can use
`deploy/docker-compose.yml` instead (same variables, `CHATDEV_GIT` instead of
`CHATDEV_REPO`/`CHATDEV_REF`).

Create a project named `chatdev` from the contents of
`deploy/compose.hostinger.yml` with this environment:

| Variable | Example | Notes |
|---|---|---|
| `CHATDEV_HOST` | `chatdev.srv1234567.hstgr.cloud` | Main hostname; Let's Encrypt cert via Traefik |
| `CHATDEV_ALT_HOST` | `chatdev.example.com` | Optional second hostname (DNS A record to the VPS IP) |
| `CHATDEV_USER` | `admin` | Login user |
| `CHATDEV_PASSWORD` | (strong random) | Login password, required |
| `BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `API_KEY` | | LLM API key used by the `${API_KEY}` placeholders in workflows |
| `CHATDEV_REPO` | `https://github.com/jowikroon/ChatDev.git` | Git repository |
| `CHATDEV_REF` | `main` | Branch or tag to run |
| `CHATDEV_TUNNEL_NETWORK` | `lab-reverse_default` | Existing docker network of the Cloudflare tunnel container |

Through Traefik the console asks for the basic-auth login. The Cloudflare
tunnel reaches `chatdev-web-1:8080` on `CHATDEV_TUNNEL_NETWORK` instead; that
port has no basic auth because the portal-gate Worker (hans-crafted-stories,
`workers/portal-gate`) authenticates in front of it. Traefik never routes to
8080. The network must exist before the project starts.

## Run locally with the same stack

```bash
CHATDEV_GIT=. CHATDEV_PASSWORD=change-me API_KEY=sk-... \
  docker compose -f deploy/docker-compose.yml up --build
```
Without Traefik there is no published port. For local use, `make dev` is simpler.
