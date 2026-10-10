# Deploy Alex on Render

Alex runs as one Render web service (Docker). GitHub sends PR events to it; it reviews and posts as
`alexreview-ai[bot]`. Add a repo by ticking it in the app's installation settings.

## 1. Create the service

1. Render dashboard: **New > Blueprint**, connect `niihhhall/alex-mvp`, branch `main`.
2. Render reads `render.yaml` and asks for three secret values:

   | Key | Value |
   |---|---|
   | `ALEX_APP_PRIVATE_KEY` | the full contents of the app's `.pem` file, including the BEGIN and END lines |
   | `ALEX_WEBHOOK_SECRET` | the contents of `workspace/secrets/webhook-secret.txt` |
   | `ALEX_LLM_API_KEY` | your Fireworks API key |

3. Click **Apply**. The first build takes a few minutes. When it is live, open
   `https://<service>.onrender.com/healthz`: it should say `ok, queued=0`.

## 2. Point the GitHub App at it

GitHub > Settings > Developer settings > GitHub Apps > alexreview-ai > General > Webhook URL:
`https://<service>.onrender.com/webhook`, then **Save changes**.

Check it under the app's **Advanced** tab: the latest delivery should show a green `200` (the `ping`).

## 3. Add repos

GitHub > Settings > Applications > alexreview-ai > Configure > **Only select repositories** > tick repos > Save.

## Settings (render.yaml)

| Key | Default | Meaning |
|---|---|---|
| `ALEX_ALLOWED_ACCOUNTS` | `niihhhall` | Only installations on these accounts are served |
| `ALEX_TOKEN_BUDGET` | 1,500,000 | Max engine tokens per review |
| `ALEX_MONTHLY_TOKEN_BUDGET` | 200,000,000 | Monthly cap; Alex posts "budget reached" instead of reviewing. Resets on redeploy until a disk is attached |
| `ALEX_WORKERS` | 2 | Reviews running at the same time |
| `ALEX_REVIEW_ON_PUSH` | false | Also review every new push to an open PR |

## Local testing without Render

- `scripts/run-once.ps1 -Repo owner/repo -Pr N` reviews one PR as the app from your machine.
- `python scripts/smoke-server.py <url> workspace/secrets/webhook-secret.txt` checks signature handling.
