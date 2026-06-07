# 🐂 Toro Brief — Setup Guide

Daily market intelligence engine. Runs every weeknight at 9 PM ET via GitHub Actions.
Delivers to Gmail, Discord, and Notion.

---

## What It Does

- Pulls live market data (SPY, QQQ, VIX, SPX) via yfinance
- Calls Claude Sonnet with web search to scan news + social sources
- Generates scored buy/sell plays, thesis plays, overbought flags, macro calendar
- Delivers a formatted brief to your email, Discord channel, and Notion workspace

---

## Setup (One Time — ~15 mins)

### Step 1 — Create the GitHub Repo

1. Go to github.com → New repository → name it `toro-brief`
2. Clone it locally or upload these files directly via the GitHub UI
3. Push all files (src/, .github/, requirements.txt, README.md)

### Step 2 — Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add each of these:

| Secret Name | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `NOTION_TOKEN` | notion.so/profile/integrations → New integration |
| `NOTION_PAGE_ID` | Open target Notion page → copy ID from URL |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Google Account → Security → 2FA → App Passwords |
| `GMAIL_TO` | Email to deliver to (can be same as GMAIL_USER) |
| `DISCORD_WEBHOOK_URL` | Discord channel → Settings → Integrations → Webhooks |

### Step 3 — Gmail App Password
1. Go to myaccount.google.com/security
2. Enable 2-Step Verification (required)
3. Search "App Passwords" → Create one named "Toro Brief"
4. Copy the 16-char password → paste as `GMAIL_APP_PASSWORD` secret

### Step 4 — Discord Webhook
1. Open your Discord server
2. Create a channel called `#toro-brief` (or use any existing channel)
3. Channel Settings → Integrations → Webhooks → New Webhook
4. Copy the webhook URL → paste as `DISCORD_WEBHOOK_URL` secret

### Step 5 — Notion Integration
1. Go to notion.so/profile/integrations → New integration
2. Name it "Toro Brief", select your workspace, copy the secret token
3. Open the Notion page where you want briefs to be created
4. Click ··· → Add connections → select your integration
5. Copy the page ID from the URL (the 32-char string after the last `/`)

### Step 6 — Test Run
1. Go to your GitHub repo → **Actions** tab
2. Click "Toro Brief — Daily Market Analysis"
3. Click **Run workflow** → Run workflow
4. Watch the logs — should complete in ~60–90 seconds

---

## Schedule

Runs automatically at **9:00 PM ET, Monday–Friday**.

To change the time, edit `.github/workflows/toro_brief.yml`:
```yaml
- cron: '0 1 * * 2-6'   # 1:00 AM UTC = 9:00 PM EDT
```
Use crontab.guru to convert times.

---

## Adding More Sources

In `src/toro_brief.py`, update the `SOCIAL_SOURCES` list:
```python
SOCIAL_SOURCES = [
    "@NoLimitGains (x.com/NoLimitGains)",
    "@InTheAssembly (x.com/InTheAssembly)",
    "@CryptoBullet1 (x.com/CryptoBullet1)",
    "@YourNewSource (x.com/YourNewSource)",   # Add here
]
```

---

## Connecting Robinhood Positions

When you're ready to pull live positions:

1. Add secrets: `RH_USERNAME` and `RH_PASSWORD`
2. In `requirements.txt`, add: `robin_stocks>=2.1.3`
3. In `toro_brief.py`, uncomment the robin_stocks block in `fetch_robinhood_positions()`

Note: Robinhood may require MFA — robin_stocks handles this via the `store_session` flag.

---

## Costs

- **GitHub Actions**: Free (2,000 minutes/month on free tier; each run uses ~2 min)
- **Anthropic API**: ~$0.02–0.05 per brief (Sonnet with web search)
- **Everything else**: Free

Monthly cost: ~$1–2 in API calls.
