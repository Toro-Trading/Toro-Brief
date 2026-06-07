"""
TORO BRIEF — Daily Market Intelligence Engine
Runs at 9 PM ET weekdays via GitHub Actions.
Delivers to Discord (required) + Gmail + Notion (both optional).
"""

import os
import json
import datetime
import requests
import yfinance as yf
import anthropic
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── CONFIG ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# Optional — only used if secrets are present
GMAIL_USER          = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD")
GMAIL_TO            = os.environ.get("GMAIL_TO")
NOTION_TOKEN        = os.environ.get("NOTION_TOKEN")
NOTION_PAGE_ID      = os.environ.get("NOTION_PAGE_ID")

SOCIAL_SOURCES = [
    "@NoLimitGains (x.com/NoLimitGains)",
    "@InTheAssembly (x.com/InTheAssembly)",
    "@CryptoBullet1 (x.com/CryptoBullet1)",
]
DEFAULT_SOURCES = ["Reuters", "Bloomberg", "WSJ", "Unusual Whales", "Finviz", "CNBC"]

PULSE_TICKERS = ["SPY", "QQQ", "^VIX", "^GSPC"]
PULSE_LABELS  = ["SPY", "QQQ", "VIX", "SPX"]

# ── MARKET DATA ───────────────────────────────────────────────────────────────

def fetch_market_pulse():
    pulse = []
    for ticker, label in zip(PULSE_TICKERS, PULSE_LABELS):
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.last_price
            prev  = info.previous_close
            chg_pct = ((price - prev) / prev) * 100
            pulse.append({
                "ticker": label,
                "price": f"${price:,.2f}" if label not in ("VIX", "SPX") else f"{price:,.2f}",
                "chg": f"{chg_pct:+.2f}%",
                "dir": "up" if chg_pct >= 0 else "down",
                "raw_chg": chg_pct,
            })
        except Exception as e:
            pulse.append({"ticker": label, "price": "N/A", "chg": "N/A", "dir": "flat"})
            print(f"Warning: could not fetch {ticker}: {e}")
    return pulse

# ── AI BRIEF ─────────────────────────────────────────────────────────────────

def generate_brief(pulse_data, rh_positions="Not connected"):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    pulse_str = "\n".join([f"  {p['ticker']}: {p['price']} ({p['chg']})" for p in pulse_data])
    all_sources = DEFAULT_SOURCES + SOCIAL_SOURCES

    prompt = f"""You are Toro Brief — a daily market intelligence engine for an active options trader.
Today is {today}. Trader profile: Pedro, 25, sub-$10k account, options focus (SPX/NDX 1256 tax, single-stock, ETF options SPY/QQQ). Active trading window 6:30–8:00 AM PT.

LIVE MARKET DATA:
{pulse_str}

SOURCES TO REFERENCE (search each for latest signals):
{chr(10).join(all_sources)}

Generate a complete Toro Brief as a JSON object. Be direct and opinionated.
For thesis plays connect REAL WORLD events happening RIGHT NOW to specific tickers.
Flag overbought setups aggressively.

Return ONLY this JSON, no markdown, no preamble:

{{
  "biasScore": "X.X/10",
  "biasLabel": "e.g. Cautiously Bearish",
  "biasRationale": "2-3 sentence market read",
  "techScore": "X.X",
  "flowScore": "X.X",
  "newsScore": "X.X",
  "pulse": [
    {{"ticker":"SPY","price":"$XXX","chg":"X.X%","dir":"up|down","sub":"key level note"}}
  ],
  "news": [
    {{"tag":"bullish|bearish|watch","text":"summary","source":"source name"}}
  ],
  "upsidePlays": [
    {{"ticker":"XXX","score":"X.X","signal":"Strong Buy|Buy","catalyst":"why now","option":"e.g. SPY $550C exp 6/20 or null","sizing":"sizing note","chips":["tag1","tag2"]}}
  ],
  "downsidePlays": [
    {{"ticker":"XXX","score":"X.X","signal":"Strong Sell|Sell","catalyst":"why bearish","option":"put structure or null","sizing":"sizing note","chips":["tag1"]}}
  ],
  "thesis": [
    {{"tier":"CONSERVATIVE|MODERATE|AGGRESSIVE","ticker":"TICKER / Name","body":"real-world catalyst to ticker logic"}}
  ],
  "overbought": [
    {{"ticker":"XXX","rsi":"XX","note":"why extended","flag":"warning label"}}
  ],
  "macro": [
    {{"date":"Day M/D","event":"event name","impact":"high|med|low"}}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    raw = ""
    for block in response.content:
        if block.type == "text":
            raw += block.text

    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean[clean.index("{"):clean.rindex("}")+1])

# ── DISCORD DELIVERY ──────────────────────────────────────────────────────────

TAG_EMOJI    = {"bullish": "[BULLISH]", "bearish": "[BEARISH]", "watch": "[WATCH]"}
IMPACT_EMOJI = {"high": "🔴", "med": "🟡", "low": "⚪"}
TIER_LABEL   = {"CONSERVATIVE": "[CONSERVATIVE]", "MODERATE": "[MODERATE]", "AGGRESSIVE": "[AGGRESSIVE]"}

def score_color(score_str):
    try:
        s = float(score_str.split("/")[0])
        if s >= 6:   return 0x3B6D11
        if s >= 5:   return 0xBA7517
        return 0xE24B4A
    except:
        return 0x888780

def send_discord(brief, pulse, date_str):
    base_color = score_color(brief.get("biasScore", "5/10"))

    pulse_val = "  ".join([
        f"**{p['ticker']}** {p['price']} {'▲' if p['dir']=='up' else '▼'}{p['chg']}"
        for p in pulse
    ])

    # Embed 1 — Bias + Pulse
    embed1 = {
        "title": f"🐂  TORO BRIEF — {date_str}",
        "description": f"**{brief.get('biasScore','—')} — {brief.get('biasLabel','')}**\n{brief.get('biasRationale','')}",
        "color": base_color,
        "fields": [
            {"name": "Technical", "value": brief.get('techScore','—'), "inline": True},
            {"name": "Flow",      "value": brief.get('flowScore','—'), "inline": True},
            {"name": "News",      "value": brief.get('newsScore','—'), "inline": True},
            {"name": "Market Pulse", "value": pulse_val, "inline": False},
        ],
        "footer": {"text": "Score guide: 0–2.9 Crisis  |  3–4.9 Bearish  |  5–5.9 Neutral  |  6–7.9 Bullish  |  8–10 Strong Bull"}
    }

    # Embed 2 — News
    news_lines = []
    for n in brief.get("news", [])[:6]:
        tag = TAG_EMOJI.get(n["tag"], "[WATCH]")
        news_lines.append(f"{tag} {n['text']} — *{n['source']}*")
    embed2 = {
        "title": "📰  News & Sentiment",
        "description": "\n\n".join(news_lines) or "No news flagged.",
        "color": 0x5F5E5A,
        "footer": {"text": "Sources: Reuters · Bloomberg · WSJ · Unusual Whales · @NoLimitGains · @InTheAssembly · @CryptoBullet1"}
    }

    # Embed 3 — Upside plays
    up_lines = []
    for p in brief.get("upsidePlays", []):
        chips = "  ".join([f"`{c}`" for c in p.get("chips", [])])
        opt = f"\n`{p['option']}`" if p.get("option") else ""
        size = f"  `{p['sizing']}`" if p.get("sizing") else ""
        up_lines.append(f"**{p['ticker']}** · {p['score']}/10 — {p['signal']}\n{p['catalyst']}{opt}{size}\n{chips}")
    embed3 = {
        "title": "🟢  Upside Plays",
        "description": "\n\n".join(up_lines) or "No upside plays today.",
        "color": 0x3B6D11,
    }

    # Embed 4 — Downside plays
    dn_lines = []
    for p in brief.get("downsidePlays", []):
        chips = "  ".join([f"`{c}`" for c in p.get("chips", [])])
        opt = f"\n`{p['option']}`" if p.get("option") else ""
        size = f"  `{p['sizing']}`" if p.get("sizing") else ""
        dn_lines.append(f"**{p['ticker']}** · {p['score']}/10 — {p['signal']}\n{p['catalyst']}{opt}{size}\n{chips}")
    embed4 = {
        "title": "🔴  Downside Plays",
        "description": "\n\n".join(dn_lines) or "No downside plays today.",
        "color": 0xE24B4A,
    }

    # Embed 5 — Thesis + OB flags + Macro
    thesis_lines = []
    for t in brief.get("thesis", []):
        thesis_lines.append(f"**{TIER_LABEL.get(t['tier'], t['tier'])} {t['ticker']}**\n{t['body']}")

    ob_lines = []
    for o in brief.get("overbought", []):
        ob_lines.append(f"**{o['ticker']}** RSI {o['rsi']} — {o['flag']}: {o['note']}")

    macro_lines = []
    for m in brief.get("macro", []):
        macro_lines.append(f"{IMPACT_EMOJI.get(m['impact'],'•')} **{m['date']}** — {m['event']}")

    desc5 = ""
    if thesis_lines:
        desc5 += "**── Thesis Plays ──**\n\n" + "\n\n".join(thesis_lines)
    if ob_lines:
        desc5 += "\n\n**── Overbought Flags ──**\n\n" + "\n".join(ob_lines)
    if macro_lines:
        desc5 += "\n\n**── Macro Calendar ──**\n\n" + "\n".join(macro_lines)

    embed5 = {
        "title": "🧠  Thesis · Flags · Macro",
        "description": desc5 or "—",
        "color": 0x378ADD,
        "footer": {"text": "Not financial advice · Toro Brief runs nightly at 9 PM ET"}
    }

    # Send all 5 as one payload (Discord supports up to 10 embeds per message)
    payload = {"embeds": [embed1, embed2, embed3, embed4, embed5]}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    r.raise_for_status()
    print("✅ Discord delivered")

# ── EMAIL DELIVERY (OPTIONAL) ─────────────────────────────────────────────────

def send_email(brief, pulse, date_str):
    if not all([GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_TO]):
        print("⏭️  Gmail not configured — skipping")
        return

    score_color_hex = "#A32D2D" if float(brief.get("biasScore","5/10").split("/")[0]) < 5 else "#3B6D11"

    pulse_html = "".join([
        f'<td style="padding:8px 12px;background:#f8f8f7;border-radius:6px;text-align:center;min-width:80px;">'
        f'<div style="font-size:13px;font-weight:600;color:#1a1a1a;">{p["ticker"]}</div>'
        f'<div style="font-size:16px;font-weight:600;color:#1a1a1a;margin:2px 0;">{p["price"]}</div>'
        f'<div style="font-size:12px;font-weight:600;color:{"#3B6D11" if p["dir"]=="up" else "#A32D2D"};">{p["chg"]}</div>'
        f'</td>'
        for p in pulse
    ])

    body = f"""<html><body style="font-family:-apple-system,sans-serif;background:#f5f0e8;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
  <div style="background:#1a1a1a;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;">
    <span style="font-size:18px;font-weight:700;color:#fff;">TORO<span style="color:#E24B4A;">.</span>BRIEF</span>
    <span style="font-size:12px;color:#888;">{date_str}</span>
  </div>
  <div style="padding:20px 24px;background:#f8f5f0;">
    <div style="font-size:30px;font-weight:700;color:{score_color_hex};">{brief.get('biasScore','—')}</div>
    <div style="font-size:14px;color:#555;margin-top:2px;">{brief.get('biasLabel','')}</div>
    <div style="font-size:12px;color:#888;margin-top:6px;">{brief.get('biasRationale','')}</div>
    <table style="border-collapse:separate;border-spacing:8px;margin-top:12px;"><tr>{pulse_html}</tr></table>
  </div>
  <div style="padding:16px 24px;text-align:center;background:#1a1a1a;">
    <span style="font-size:11px;color:#555;">Toro Brief · Not financial advice</span>
  </div>
</div></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🐂 Toro Brief — {date_str}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_TO
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, GMAIL_TO, msg.as_string())
    print("✅ Email delivered")

# ── NOTION DELIVERY (OPTIONAL) ────────────────────────────────────────────────

def save_to_notion(brief, date_str):
    if not all([NOTION_TOKEN, NOTION_PAGE_ID]):
        print("⏭️  Notion not configured — skipping")
        return

    try:
        from notion_client import Client
        notion = Client(auth=NOTION_TOKEN)

        def block(heading, content):
            return [
                {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":heading}}]}},
                {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":content}}]}}
            ]

        news_text  = "\n".join([f"[{n['tag'].upper()}] {n['text']} — {n['source']}" for n in brief.get("news",[])])
        up_text    = "\n\n".join([f"{p['ticker']} | {p['score']}/10 | {p['signal']}\n{p['catalyst']}" for p in brief.get("upsidePlays",[])])
        dn_text    = "\n\n".join([f"{p['ticker']} | {p['score']}/10 | {p['signal']}\n{p['catalyst']}" for p in brief.get("downsidePlays",[])])
        th_text    = "\n\n".join([f"[{t['tier']}] {t['ticker']}\n{t['body']}" for t in brief.get("thesis",[])])
        macro_text = "\n".join([f"{m['date']} | {m['impact'].upper()} | {m['event']}" for m in brief.get("macro",[])])

        children = [
            {"object":"block","type":"callout","callout":{
                "rich_text":[{"type":"text","text":{"content":f"{brief.get('biasScore','—')} — {brief.get('biasLabel','')}\n{brief.get('biasRationale','')}"}}],
                "icon":{"emoji":"🐂"},"color":"gray_background"
            }}
        ]
        children += block("📰 News", news_text)
        children += block("🟢 Upside", up_text)
        children += block("🔴 Downside", dn_text)
        children += block("🧠 Thesis", th_text)
        children += block("📅 Macro", macro_text)

        notion.pages.create(
            parent={"page_id": NOTION_PAGE_ID},
            properties={"title":{"title":[{"type":"text","text":{"content":f"Toro Brief — {date_str}"}}]}},
            children=children
        )
        print("✅ Notion delivered")
    except Exception as e:
        print(f"⚠️  Notion failed: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    date_str = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    print(f"🐂 Toro Brief starting — {date_str}")

    print("📈 Fetching market pulse...")
    pulse = fetch_market_pulse()
    print(f"   Pulse: {[p['ticker']+' '+p['chg'] for p in pulse]}")

    print("🧠 Generating AI brief...")
    brief = generate_brief(pulse)
    print(f"   Bias: {brief.get('biasScore')} — {brief.get('biasLabel')}")

    print("💬 Sending to Discord...")
    send_discord(brief, pulse, date_str)

    print("📧 Sending email...")
    send_email(brief, pulse, date_str)

    print("📝 Saving to Notion...")
    save_to_notion(brief, date_str)

    print("✅ All done.")

if __name__ == "__main__":
    main()
