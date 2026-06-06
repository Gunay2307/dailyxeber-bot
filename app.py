import streamlit as st
import feedparser
import requests
import json
import hashlib
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="DailyXeber Bot", page_icon="📰", layout="wide")

# Storage
def load_json(path, default):
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()

def is_duplicate(url):
    sent = load_json("sent.json", [])
    return any(a.get("hash") == url_hash(url) for a in sent)

def add_sent(article):
    sent = load_json("sent.json", [])
    sent.insert(0, article)
    save_json("sent.json", sent[:300])

# Gemini
def summarize(title, body, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""Bu xəbəri iki dildə xülasə et.
Başlıq: {title}
Mətn: {body}

YALNIZ bu formatda cavab ver:
🇦🇿 AZ:
[2-3 cümlə Azərbaycan dilində]

🇬🇧 EN:
[2-3 sentence in English]"""
    return model.generate_content(prompt).text.strip()

# Telegram
def send_telegram(token, chat_id, text):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10
    )
    return r.ok, r.json()

# RSS
def fetch_rss(url, limit=5):
    try:
        feed = feedparser.parse(url)
        return [{"title": e.get("title",""), "url": e.get("link",""),
                 "body": e.get("summary",""), "source": feed.feed.get("title", url)}
                for e in feed.entries[:limit]], None
    except Exception as e:
        return [], str(e)

# ── SIDEBAR ──
with st.sidebar:
    st.title("⚙️ Parametrlər")
    gemini_key = st.text_input("Gemini API Key", type="password")
    bot_token  = st.text_input("Telegram Bot Token", type="password")
    chat_id    = st.text_input("Telegram Chat ID", placeholder="@dailyxeber")
    st.divider()
    st.markdown("### 📡 RSS Mənbələri")
    rss_sources = load_json("rss.json", [
        {"name":"Trend Az","url":"https://az.trend.az/rss"},
        {"name":"Report.az","url":"https://report.az/az/feed/"}
    ])
    for i, s in enumerate(rss_sources):
        c1, c2 = st.columns([5,1])
        c1.markdown(f"**{s['name']}**")
        if c2.button("🗑️", key=f"d{i}"):
            rss_sources.pop(i); save_json("rss.json", rss_sources); st.rerun()
    n1 = st.text_input("Yeni ad")
    n2 = st.text_input("Yeni URL")
    if st.button("➕ Əlavə et"):
        if n1 and n2:
            rss_sources.append({"name":n1,"url":n2})
            save_json("rss.json", rss_sources); st.rerun()
    limit = st.slider("Hər mənbədən neçə xəbər", 1, 15, 5)
    dry   = st.toggle("Test rejimi", value=True)

# ── TABS ──
t1, t2, t3 = st.tabs(["🏠 Dashboard", "▶️ İşə Sal", "📋 Tarixçə"])

with t1:
    st.title("📰 DailyXeber Bot")
    sent = load_json("sent.json", [])
    c1,c2,c3 = st.columns(3)
    c1.metric("Göndərilmiş", len(sent))
    c2.metric("RSS Mənbə", len(rss_sources))
    today = sum(1 for a in sent if a.get("sent_at","").startswith(datetime.now().strftime("%Y-%m-%d")))
    c3.metric("Bu gün", today)
    st.divider()
    st.subheader("Son xəbərlər")
    for a in sent[:5]:
        st.markdown(f"**{a.get('title','')}**  \n🕐 {a.get('sent_at','')[:16]} · 📡 {a.get('source','')}")
        st.divider()

with t2:
    st.subheader("▶️ Xəbərləri Yüklə və Göndər")
    selected = st.multiselect("Mənbə seç", [s["name"] for s in rss_sources],
                               default=[s["name"] for s in rss_sources[:1]])
    ready = gemini_key and bot_token and chat_id
    if not ready:
        st.warning("Sol paneldən API açarlarını daxil edin.")

    if st.button("🚀 Başlat", disabled=not ready, type="primary"):
        articles = []
        for s in rss_sources:
            if s["name"] in selected:
                arts, err = fetch_rss(s["url"], limit)
                if err: st.error(f"{s['name']}: {err}")
                else: articles.extend(arts)

        st.info(f"{len(articles)} xəbər tapıldı")
        bar = st.progress(0)

        for i, art in enumerate(articles):
            if not art["url"]:
                st.warning(f"⏭️ URL yoxdur: {art['title'][:50]}"); continue
            if is_duplicate(art["url"]):
                st.warning(f"⏭️ Dublikat: {art['title'][:50]}"); continue
            try:
                summary = summarize(art["title"], art["body"], gemini_key)
            except Exception as e:
                st.error(f"Gemini xətası: {e}"); continue

            msg = f"📰 <b>{art['title']}</b>\n\n{summary}\n\n🔗 <a href='{art['url']}'>Tam oxu</a>\n<i>@dailyxeber</i>"

            if dry:
                st.success(f"✅ TEST: {art['title'][:60]}")
                with st.expander("Xülasəyə bax"):
                    st.markdown(summary)
            else:
                ok, _ = send_telegram(bot_token, chat_id, msg)
                if ok:
                    add_sent({"hash": url_hash(art["url"]), "title": art["title"],
                              "url": art["url"], "sent_at": datetime.now().isoformat(),
                              "source": art["source"], "summary": summary})
                    st.success(f"✅ Göndərildi: {art['title'][:60]}")
                else:
                    st.error(f"❌ Telegram xətası: {art['title'][:50]}")
            bar.progress((i+1)/len(articles))

with t3:
    st.subheader("📋 Tarixçə")
    sent = load_json("sent.json", [])
    search = st.text_input("🔍 Axtar")
    if st.button("🗑️ Sıfırla"):
        save_json("sent.json", []); st.rerun()
    filtered = [a for a in sent if not search or search.lower() in a.get("title","").lower()]
    st.markdown(f"**{len(filtered)} xəbər**")
    for a in filtered:
        with st.expander(f"📰 {a.get('title','')[:70]}"):
            st.markdown(f"**Mənbə:** {a.get('source','')}  |  **Vaxt:** {a.get('sent_at','')[:19]}")
            st.markdown(f"**Link:** {a.get('url','')}")
            if a.get("summary"):
                st.markdown(a["summary"])
