"""
TORO BRIEF — Daily Market Intelligence Engine
Runs at 9 PM ET on weekdays via GitHub Actions.
Delivers to Gmail + Notion + Discord.
"""

import os
import json
import datetime
import requests
import yfinance as yf
import anthropic
from notion_client import Client as NotionClient
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ─── CONFIG ─────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN        = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID      = os.environ["NOTION_PAGE_ID"]   # Parent page for briefs DB
GMAIL_USER          = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
GMAIL_TO            = os.environ["GMAIL_TO"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# Social/news sources the AI should reference
SOCIAL_SOURCES = [
    "@NoLimitGains (x.com/NoLimitGains)",
    "@InTheAssembly (x.com/InTheAssembly)",
    "@CryptoBullet1 (x.com/CryptoBullet1)",
]
DEFAULT_SOURCES = ["Reuters", "Bloomberg", "WSJ", "Unusual Whales", "Finviz", "CNBC"]

# Tickers to track for market pulse
PULSE_TICKERS = ["SPY", "QQQ", "^VIX", "^GSPC"]
PULSE_LABELS  = ["SPY", "QQQ", "VIX", "SPX"]

# ─── MARKET DATA ─────────────────────────────────────────────────────────────

def fetch_market_pulse():
    """Pull live quotes for core market tickers via yfinance."""
    pulse = []
    for ticker, label in zip(PULSE_TICKERS, PULSE_LABELS):
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.last_price
            prev  = info.previous_close
            chg_pct = ((price - prev) / prev) * 100
            direction = "up" if chg_pct >= 0 else "down"
            pulse.append({
                "ticker": label,
                "price": f"${price:,.2f}" if label != "VIX" else f"{price:.1f}",
                "chg": f"{chg_pct:+.2f}%",
                "dir": direction,
                "raw_price": price,
                "raw_chg": chg_pct,
            })
        except Exception as e:
            pulse.append({"ticker": label, "price": "N/A", "chg": "N/A", "dir": "flat", "error": str(e)})
    return pulse


def fetch_robinhood_positions():
    """
    Placeholder — Robinhood doesn't have an official public API.
    In production, use robin_stocks with your RH credentials stored as secrets.
    Returns a summary string for the AI prompt.
    """
    try:
        # Uncomment and configure when ready:
        # import robin_stocks.robinhood as r
        # r.login(os.environ["RH_USERNAME"], os.environ["RH_PASSWORD"])
        # positions = r.account.build_holdings()
        # return json.dumps(positions, indent=2)
        return "Robinhood positions: not yet connected (add RH_USERNAME/RH_PASSWORD secrets to enable)"
    except Exception as e:
        return f"Robinhood positions unavailable: {e}"


# ─── AI BRIEF GENERATION ─────────────────────────────────────────────────────

def generate_brief(pulse_data: list, rh_positions: str) -> dict:
    """Call Claude Sonnet with web search to generate the full brief."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    pulse_str = "\n".join([
        f"  {p['ticker']}: {p['price']} ({p['chg']})"
        for p in pulse_data
    ])
    all_sources = DEFAULT_SOURCES + SOCIAL_SOURCES

    prompt = f"""You are Toro Brief — a daily market intelligence engine for an active options trader.
Today is {today}. The trader is Pedro — 25 years old, under-$10k account, focus on options (SPX/NDX index options for 1256 tax treatment, single-stock options, ETF options SPY/QQQ). He trades 6:30–8:00 AM PT / 9:30–11 AM ET.

LIVE MARKET DATA (just fetched):
{pulse_str}

ROBINHOOD POSITIONS:
{rh_positions}

SOURCES TO REFERENCE (search and summarize key signals from each):
{chr(10).join(all_sources)}

Generate a complete Toro Brief as a JSON object. Be direct, opinionated, and practical.
For thesis plays, connect REAL WORLD events happening RIGHT NOW to specific tickers (like: AI data center buildout → nuclear energy → CEG; World Cup → consumer brands → BUD/ONON; tariff impact → domestic manufacturers, etc.)
Flag overbought setups aggressively — the SanDisk lesson is always top of mind.

Return ONLY this JSON structure, no markdown, no preamble:

{{
  "biasScore": "X.X/10",
  "biasLabel": "e.g. Cautiously Bearish",
  "techScore": "X.X",
  "flowScore": "X.X",
  "newsScore": "X.X",
  "biasRationale": "2-3 sentence overall market read",
  "pulse": [
    {{"ticker":"SPY","price":"$XXX","chg":"X.X%","dir":"up|down","sub":"Key level note"}}
  ],
  "news": [
    {{"tag":"bullish|bearish|watch","text":"headline summary","source":"source name"}}
  ],
  "upsidePlays": [
    {{
      "ticker":"XXX",
      "score":"X.X",
      "signal":"Strong Buy|Buy",
      "catalyst":"Why now — specific, actionable",
      "option":"e.g. SPY $550C exp 6/20",
      "sizing":"sizing note for sub-$10k account",
      "chips":["RSI note","volume note"]
    }}
  ],
  "downsidePlays": [
    {{
      "ticker":"XXX",
      "score":"X.X",
      "signal":"Strong Sell|Sell",
      "catalyst":"Why bearish — specific",
      "option":"put structure OR null if inverse ETF",
      "sizing":"sizing note",
      "chips":["flags"]
    }}
  ],
  "thesis": [
    {{
      "tier":"CONSERVATIVE|MODERATE|AGGRESSIVE",
      "ticker":"TICKER / Company Name",
      "body":"Real-world connection → market play. Be specific about the catalyst."
    }}
  ],
  "overbought": [
    {{"ticker":"XXX","rsi":"XX","note":"Why it's extended","flag":"Warning label"}}
  ],
  "macro": [
    {{"date":"Day M/D","event":"Event name","impact":"high|med|low"}}
  ],
  "positionFlags": [
    {{"ticker":"XXX","note":"Relevant flag for Pedro's current position"}}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    clean = raw_text.replace("```json", "").replace("```", "").strip()
    json_start = clean.index("{")
    json_end = clean.rindex("}") + 1
    return json.loads(clean[json_start:json_end])


# ─── FORMATTING ──────────────────────────────────────────────────────────────

SIGNAL_EMOJI = {
    "Strong Buy": "🟢", "Buy": "🟩",
    "Strong Sell": "🔴", "Sell": "🟥",
    "Neutral": "⬜"
}
TAG_EMOJI = {"bullish": "🟢", "bearish": "🔴", "watch": "🟡"}
IMPACT_EMOJI = {"high": "🔴", "med": "🟡", "low": "⚪"}
TIER_EMOJI = {"CONSERVATIVE": "🟢", "MODERATE": "🟡", "AGGRESSIVE": "🔴"}


def format_html_email(brief: dict, pulse: list, date_str: str) -> str:
    """Render the brief as a clean HTML email."""

    def pulse_html():
        rows = ""
        for p in pulse:
            color = "#3B6D11" if p.get("dir") == "up" else "#A32D2D"
            rows += f"""
            <td style="padding:8px 12px;background:#f8f8f7;border-radius:6px;text-align:center;min-width:80px;">
              <div style="font-size:13px;font-weight:600;color:#1a1a1a;">{p['ticker']}</div>
              <div style="font-size:16px;font-weight:600;color:#1a1a1a;margin:2px 0;">{p['price']}</div>
              <div style="font-size:12px;font-weight:600;color:{color};">{p['chg']}</div>
              <div style="font-size:11px;color:#888;">{p.get('sub','')}</div>
            </td>"""
        return f"<table style='border-collapse:separate;border-spacing:8px;'><tr>{rows}</tr></table>"

    def news_html():
        tag_colors = {"bullish": ("#EAF3DE","#3B6D11"), "bearish": ("#FCEBEB","#A32D2D"), "watch": ("#FAEEDA","#854F0B")}
        html = ""
        for n in brief.get("news", []):
            bg, fg = tag_colors.get(n["tag"], ("#f0f0f0","#555"))
            html += f"""
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #f0ece4;vertical-align:top;">
                <span style="background:{bg};color:{fg};font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-right:8px;">{n['tag'].upper()}</span>
                <span style="font-size:13px;color:#1a1a1a;">{n['text']}</span>
                <span style="font-size:11px;color:#999;margin-left:6px;">— {n['source']}</span>
              </td>
            </tr>"""
        return f"<table style='width:100%;border-collapse:collapse;'>{html}</table>"

    def plays_html(plays, is_bear=False):
        accent = "#A32D2D" if is_bear else "#3B6D11"
        html = ""
        for p in plays:
            chips = "".join([f"<span style='font-size:11px;padding:2px 8px;border-radius:4px;background:#f0ece4;color:#666;margin-right:4px;'>{c}</span>" for c in p.get("chips",[])])
            opt_chip = f"<span style='font-size:11px;padding:2px 8px;border-radius:4px;background:#E6F1FB;color:#185FA5;margin-right:4px;'>{p['option']}</span>" if p.get("option") else ""
            size_chip = f"<span style='font-size:11px;padding:2px 8px;border-radius:4px;background:#f0ece4;color:#666;margin-right:4px;'>{p['sizing']}</span>" if p.get("sizing") else ""
            html += f"""
            <tr>
              <td style="padding:12px;border-left:3px solid {accent};background:#fafaf8;margin-bottom:8px;border-radius:0 6px 6px 0;display:block;margin:0 0 8px 0;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                  <span style="font-size:16px;font-weight:600;color:#1a1a1a;">{p['ticker']}</span>
                  <span style="font-size:14px;font-weight:600;color:{accent};">{p['score']}/10 — {p['signal']}</span>
                </div>
                <div style="font-size:13px;color:#555;margin-bottom:8px;line-height:1.5;">{p['catalyst']}</div>
                <div>{opt_chip}{size_chip}{chips}</div>
              </td>
            </tr>"""
        return f"<table style='width:100%;border-collapse:collapse;'>{html}</table>"

    def thesis_html():
        tier_styles = {
            "CONSERVATIVE": ("#EAF3DE","#3B6D11"),
            "MODERATE": ("#FAEEDA","#854F0B"),
            "AGGRESSIVE": ("#FCEBEB","#A32D2D")
        }
        html = ""
        for t in brief.get("thesis", []):
            bg, fg = tier_styles.get(t["tier"], ("#f0f0f0","#555"))
            html += f"""
            <div style="padding:12px;background:#fafaf8;border-radius:6px;margin-bottom:8px;">
              <span style="background:{bg};color:{fg};font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;">{t['tier']}</span>
              <div style="font-size:14px;font-weight:600;color:#1a1a1a;margin:6px 0 4px;">{t['ticker']}</div>
              <div style="font-size:13px;color:#555;line-height:1.6;">{t['body']}</div>
            </div>"""
        return html

    score_color = "#3B6D11" if float(brief.get("biasScore","5/10").split("/")[0]) >= 6.0 else "#A32D2D"

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f0e8;margin:0;padding:20px;">
  <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
    
    <div style="background:#1a1a1a;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;">
      <div style="font-size:20px;font-weight:700;color:#fff;letter-spacing:-0.5px;">TORO<span style="color:#E24B4A;">.</span>BRIEF</div>
      <div style="font-size:12px;color:#888;">{date_str}</div>
    </div>

    <div style="padding:20px 24px;background:#f8f5f0;border-bottom:1px solid #ede8df;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-size:32px;font-weight:700;color:{score_color};">{brief.get('biasScore','—')}</div>
          <div style="font-size:14px;color:#555;margin-top:2px;">{brief.get('biasLabel','')}</div>
          <div style="font-size:12px;color:#888;margin-top:6px;max-width:340px;">{brief.get('biasRationale','')}</div>
        </div>
        <div style="display:flex;gap:16px;">
          <div style="text-align:center;"><div style="font-size:18px;font-weight:600;color:#1a1a1a;">{brief.get('techScore','—')}</div><div style="font-size:11px;color:#999;">Technical</div></div>
          <div style="text-align:center;"><div style="font-size:18px;font-weight:600;color:#1a1a1a;">{brief.get('flowScore','—')}</div><div style="font-size:11px;color:#999;">Flow</div></div>
          <div style="text-align:center;"><div style="font-size:18px;font-weight:600;color:#1a1a1a;">{brief.get('newsScore','—')}</div><div style="font-size:11px;color:#999;">News</div></div>
        </div>
      </div>
    </div>

    <div style="padding:20px 24px;">
      <h3 style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#999;margin:0 0 12px;">Market Pulse</h3>
      {pulse_html()}
    </div>

    <div style="padding:20px 24px;border-top:1px solid #f0ece4;">
      <h3 style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#999;margin:0 0 12px;">News & Sentiment</h3>
      {news_html()}
    </div>

    <div style="padding:20px 24px;border-top:1px solid #f0ece4;">
      <h3 style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#999;margin:0 0 12px;">Upside Plays</h3>
      {plays_html(brief.get('upsidePlays',[]))}
    </div>

    <div style="padding:20px 24px;border-top:1px solid #f0ece4;">
      <h3 style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#999;margin:0 0 12px;">Downside Plays</h3>
      {plays_html(brief.get('downsidePlays',[]), is_bear=True)}
    </div>

    <div style="padding:20px 24px;border-top:1px solid #f0ece4;">
      <h3 style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#999;margin:0 0 12px;">Real-World Thesis Plays</h3>
      {thesis_html()}
    </div>

    <div style="padding:16px 24px;background:#1a1a1a;text-align:center;">
      <div style="font-size:11px;color:#555;">Toro Brief · Not financial advice · For informational purposes only</div>
    </div>
  </div>
</body>
</html>"""


def format_discord_embeds(brief: dict, pulse: list, date_str: str) -> list:
    """Format brief as Discord webhook payloads (split into sections)."""
    score_color = 0x3B6D11 if float(brief.get("biasScore","5/10").split("/")[0]) >= 6.0 else 0xA32D2D

    pulse_str = " | ".join([f"**{p['ticker']}** {p['price']} {p['chg']}" for p in pulse])
    news_str = "\n".join([
        f"{TAG_EMOJI.get(n['tag'],'•')} {n['text']} — *{n['source']}*"
        for n in brief.get("news", [])[:5]
    ])

    up_plays = "\n".join([
        f"🟢 **{p['ticker']}** {p['score']}/10 — {p['signal']}\n{p['catalyst'][:120]}..."
        for p in brief.get("upsidePlays", [])
    ])
    dn_plays = "\n".join([
        f"🔴 **{p['ticker']}** {p['score']}/10 — {p['signal']}\n{p['catalyst'][:120]}..."
        for p in brief.get("downsidePlays", [])
    ])
    thesis_str = "\n".join([
        f"{TIER_EMOJI.get(t['tier'],'•')} **[{t['tier']}]** {t['ticker']}\n{t['body'][:150]}..."
        for t in brief.get("thesis", [])
    ])
    macro_str = "\n".join([
        f"{IMPACT_EMOJI.get(m['impact'],'•')} {m['date']} — {m['event']}"
        for m in brief.get("macro", [])
    ])

    payload1 = {
        "embeds": [{
            "title": f"🐂 TORO BRIEF — {date_str}",
            "description": f"**{brief.get('biasScore','—')} — {brief.get('biasLabel','')}**\n{brief.get('biasRationale','')}",
            "color": score_color,
            "fields": [
                {"name": "📊 Market Pulse", "value": pulse_str, "inline": False},
                {"name": f"Technical: {brief.get('techScore','—')}", "value": "", "inline": True},
                {"name": f"Flow: {brief.get('flowScore','—')}", "value": "", "inline": True},
                {"name": f"News: {brief.get('newsScore','—')}", "value": "", "inline": True},
            ]
        }]
    }

    payload2 = {
        "embeds": [{
            "title": "📰 News & Sentiment",
            "description": news_str,
            "color": 0x888780,
        }]
    }

    payload3 = {
        "embeds": [{
            "title": "🟢 Upside Plays",
            "description": up_plays or "No upside plays today.",
            "color": 0x639922,
            "fields": [{"name": "🔴 Downside Plays", "value": dn_plays or "No downside plays today.", "inline": False}]
        }]
    }

    payload4 = {
        "embeds": [{
            "title": "🧠 Real-World Thesis Plays",
            "description": thesis_str or "—",
            "color": 0x378ADD,
            "fields": [{"name": "📅 Macro Calendar", "value": macro_str or "—", "inline": False}]
        }]
    }

    return [payload1, payload2, payload3, payload4]


# ─── DELIVERY ─────────────────────────────────────────────────────────────────

def send_email(html_body: str, date_str: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🐂 Toro Brief — {date_str}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, GMAIL_TO, msg.as_string())
    print("✅ Email sent")


def send_discord(embeds: list):
    for payload in embeds:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        r.raise_for_status()
    print("✅ Discord sent")


def save_to_notion(brief: dict, date_str: str):
    notion = NotionClient(auth=NOTION_TOKEN)

    score_val = float(brief.get("biasScore","5/10").split("/")[0])
    label = brief.get("biasLabel","—")
    rationale = brief.get("biasRationale","")

    news_text = "\n".join([
        f"[{n['tag'].upper()}] {n['text']} — {n['source']}"
        for n in brief.get("news",[])
    ])
    up_text = "\n".join([
        f"{p['ticker']} | {p['score']}/10 | {p['signal']}\n{p['catalyst']}\nPlay: {p.get('option','N/A')} | {p.get('sizing','')}"
        for p in brief.get("upsidePlays",[])
    ])
    dn_text = "\n".join([
        f"{p['ticker']} | {p['score']}/10 | {p['signal']}\n{p['catalyst']}\nPlay: {p.get('option','N/A')} | {p.get('sizing','')}"
        for p in brief.get("downsidePlays",[])
    ])
    thesis_text = "\n".join([
        f"[{t['tier']}] {t['ticker']}\n{t['body']}"
        for t in brief.get("thesis",[])
    ])
    ob_text = "\n".join([
        f"{o['ticker']} — RSI {o['rsi']} — {o['flag']}: {o['note']}"
        for o in brief.get("overbought",[])
    ])
    macro_text = "\n".join([
        f"{m['date']} | {m['impact'].upper()} | {m['event']}"
        for m in brief.get("macro",[])
    ])

    def block(heading, content):
        return [
            {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":heading}}]}},
            {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":content}}]}}
        ]

    children = [
        {"object":"block","type":"callout","callout":{
            "rich_text":[{"type":"text","text":{"content":f"{brief.get('biasScore','—')} — {label}\n{rationale}"}}],
            "icon":{"emoji":"🐂"},
            "color":"gray_background"
        }}
    ]
    children += block("📰 News & Sentiment", news_text)
    children += block("🟢 Upside Plays", up_text)
    children += block("🔴 Downside Plays", dn_text)
    children += block("🧠 Thesis Plays", thesis_text)
    children += block("⚠️ Overbought Flags", ob_text)
    children += block("📅 Macro Calendar", macro_text)

    notion.pages.create(
        parent={"page_id": NOTION_PAGE_ID},
        properties={"title": {"title": [{"type":"text","text":{"content":f"Toro Brief — {date_str}"}}]}},
        children=children
    )
    print("✅ Notion page created")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %-d, %Y")
    print(f"🐂 Toro Brief starting — {date_str}")

    print("📈 Fetching market pulse...")
    pulse = fetch_market_pulse()

    print("📂 Fetching Robinhood positions...")
    rh_positions = fetch_robinhood_positions()

    print("🧠 Generating AI brief (with web search)...")
    brief = generate_brief(pulse, rh_positions)

    print("📧 Sending email...")
    html = format_html_email(brief, pulse, date_str)
    send_email(html, date_str)

    print("💬 Sending Discord...")
    embeds = format_discord_embeds(brief, pulse, date_str)
    send_discord(embeds)

    print("📝 Saving to Notion...")
    save_to_notion(brief, date_str)

    print("✅ All done.")


if __name__ == "__main__":
    main()
