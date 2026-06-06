import streamlit as st
import feedparser
import requests
import json
import hashlib
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="DailyXeber Bot",
    page_icon="📰",
    layout="wide"
)

# ── Custom CSS ──
st.markdown("""
<style>
/* Metric cards */
.card {
    padding: 20px;
    border-radius: 16px;
    text-align: center;
    margin-bottom: 8px;
}
.card-blue  { background: linear-gradient(135deg,#1e3a8a,#3b82f6); color:white; }
.card-green { background: linear-gradient(135deg,#065f46,#10b981); color:white; }
.card-orange{ background: linear-gradient(135deg,#92400e,#f59e0b); color:white; }
.card-purple{ background: linear-gradient(135deg,#4c1d95,#8b5cf6); color:white; }
.card h1 { font-size:2.5rem; margin:0; font-weight:800; }
.card p  { font-size:0.85rem; margin:4px 0 0; opacity:0.9; }

/* News items */
.news-item {
    background: linear-gradient(135deg,#1e1e2e,#2d2d44);
    border-left: 4px solid #6d28d9;
    border-radius: 0 12px 12px 0;
    padding: 14px 18px;
    margin-bottom: 10px;
    color: white;
}
.news-item .title { font-weight:600; font-size:0.95rem; }
.news-item .meta  { font-size:0.75rem; opacity:0.6; margin-top:4px; }

/* Status badge */
.badge-ok   { background:#10b981; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; }
.badge-err  { background:#ef4444; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; }
.badge-skip { background:#6b7280; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; }

/* Header banner */
.banner {
    background: linear-gradient(135deg, #1e1b4b, #312e81, #4c1d95);
    padding: 28px 32px;
    border-radius: 20px;
    color: white;
    margin-bottom: 24px;
}
.banner h1 { margin:0; font-size:2rem; }
.banner p  { margin:4px 0 0; opacity:0.7; font-size:0.9rem; }

/* Sidebar style */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f0f1a, #1a1a2e);
}
</style>
""", unsafe_allow_html=True)

# ── Storage ──
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

# ── Gemini ──
def summarize(title, body, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f"""Bu xəbəri iki dildə xülasə et.
Başlıq: {title}
Mətn: {body}

YALNIZ bu formatda cavab ver:
🇦🇿 AZ:
[2-3 cümlə Azərbaycan dilində]

🇬🇧 EN:
[2-3 sentence in English]"""
    return model.generate_content(prompt).text.strip()

# ── Telegram ──
def send_telegram(token, chat_id, text):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10
    )
    return r.ok, r.json()

# ── RSS ──
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
    st.markdown("## ⚙️ Parametrlər")
    st.divider()
    gemini_key = st.text_input("🔑 Gemini API Key", type="password")
    bot_token  = st.text_input("🤖 Telegram Bot Token", type="password")
    chat_id    = st.text_input("💬 Telegram Chat ID", placeholder="-1003904953293")
    st.divider()

    st.markdown("### 📡 RSS Mənbələri")
    rss_sources = load_json("rss.json", [
        {"name":"Trend Az","url":"https://az.trend.az/rss"},
        {"name":"Report.az","url":"https://report.az/az/feed/"}
    ])
    for i, s in enumerate(rss_sources):
        c1, c2 = st.columns([5,1])
        c1.markdown(f"📌 **{s['name']}**")
        if c2.button("🗑️", key=f"d{i}"):
            rss_sources.pop(i); save_json("rss.json", rss_sources); st.rerun()

    with st.expander("➕ Yeni mənbə əlavə et"):
        n1 = st.text_input("Ad",  key="na")
        n2 = st.text_input("URL", key="nu")
        if st.button("Əlavə et", use_container_width=True):
            if n1 and n2:
                rss_sources.append({"name":n1,"url":n2})
                save_json("rss.json", rss_sources); st.rerun()

    st.divider()
    limit = st.slider("📊 Hər mənbədən neçə xəbər", 1, 15, 5)
    dry   = st.toggle("🧪 Test rejimi", value=True)

# ── TABS ──
t1, t2, t3 = st.tabs(["🏠  Dashboard", "🚀  İşə Sal", "📋  Tarixçə"])

# ══ TAB 1 ══
with t1:
    st.markdown("""
    <div class="banner">
        <h1>📰 DailyXeber Bot</h1>
        <p>Azərbaycan xəbərləri — Gemini AI ilə Azərbaycanca + İngiliscə xülasə → @dailyxeber</p>
    </div>
    """, unsafe_allow_html=True)

    sent = load_json("sent.json", [])
    today = sum(1 for a in sent if a.get("sent_at","").startswith(datetime.now().strftime("%Y-%m-%d")))
    status_color = "card-green" if (gemini_key and bot_token and chat_id) else "card-err"
    status_text  = "🟢 Aktiv" if (gemini_key and bot_token and chat_id) else "🔴 Yoxdur"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="card card-blue"><h1>{len(sent)}</h1><p>📨 Göndərilmiş</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="card card-green"><h1>{len(rss_sources)}</h1><p>📡 RSS Mənbə</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="card card-orange"><h1>{today}</h1><p>📅 Bu gün</p></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="card card-purple"><h1 style="font-size:1.1rem;padding-top:8px">{status_text}</h1><p>⚡ Bot statusu</p></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🕐 Son Göndərilənlər")
    if sent:
        for a in sent[:6]:
            st.markdown(f"""
            <div class="news-item">
                <div class="title">📰 {a.get('title','')[:80]}</div>
                <div class="meta">📡 {a.get('source','')} &nbsp;|&nbsp; 🕐 {a.get('sent_at','')[:16]} &nbsp;|&nbsp; <a href="{a.get('url','')}" target="_blank" style="color:#a78bfa">🔗 Link</a></div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("💡 Hələ xəbər göndərilməyib. 'İşə Sal' tabından başla!")

# ══ TAB 2 ══
with t2:
    st.markdown("### 🚀 Xəbərləri Yüklə və Göndər")

    selected = st.multiselect(
        "📡 Mənbə seç:",
        options=[s["name"] for s in rss_sources],
        default=[s["name"] for s in rss_sources[:1]]
    )

    ready = bool(gemini_key and bot_token and chat_id)

    col1, col2 = st.columns(2)
    with col1:
        if dry:
            st.info("🧪 **Test rejimi aktiv** — xəbərlər Telegram-a göndərilməyəcək")
        else:
            st.success("✅ **Real rejim** — xəbərlər @dailyxeber kanalına göndəriləcək")
    with col2:
        if not ready:
            st.warning("⚠️ Sol paneldən API açarlarını daxil edin")

    if st.button("🚀 Başlat", disabled=not ready, type="primary", use_container_width=True):
        articles = []
        with st.spinner("📡 RSS mənbələrindən xəbərlər yüklənir..."):
            for s in rss_sources:
                if s["name"] in selected:
                    arts, err = fetch_rss(s["url"], limit)
                    if err:
                        st.error(f"❌ {s['name']}: {err}")
                    else:
                        articles.extend(arts)

        st.success(f"✅ {len(articles)} xəbər tapıldı!")
        bar = st.progress(0)

        for i, art in enumerate(articles):
            if not art["url"]:
                st.markdown('<span class="badge-skip">⏭️ URL yoxdur</span>', unsafe_allow_html=True)
                continue
            if is_duplicate(art["url"]):
                st.markdown(f'<span class="badge-skip">⏭️ Dublikat: {art["title"][:50]}</span>', unsafe_allow_html=True)
                continue
            try:
                with st.spinner(f"🤖 Gemini işləyir: {art['title'][:50]}..."):
                    summary = summarize(art["title"], art["body"], gemini_key)
            except Exception as e:
                st.error(f"❌ Gemini xətası: {e}")
                continue

            msg = f"📰 <b>{art['title']}</b>\n\n{summary}\n\n🔗 <a href='{art['url']}'>Tam oxu</a>\n<i>@dailyxeber</i>"

            if dry:
                with st.expander(f"✅ TEST — {art['title'][:60]}"):
                    st.markdown(summary)
                    st.code(msg, language=None)
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

        st.balloons()

# ══ TAB 3 ══
with t3:
    st.markdown("### 📋 Göndərilmiş Xəbərlər")
    sent = load_json("sent.json", [])

    col1, col2 = st.columns([4,1])
    with col1:
        search = st.text_input("🔍 Axtar", placeholder="Başlıq və ya mənbə...")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Sıfırla", type="secondary"):
            save_json("sent.json", []); st.rerun()

    filtered = [a for a in sent if not search or search.lower() in a.get("title","").lower()]

    st.markdown(f"**📊 {len(filtered)} xəbər tapıldı**")
    st.divider()

    if filtered:
        for a in filtered:
            with st.expander(f"📰 {a.get('title','')[:75]}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**📡 Mənbə:** {a.get('source','')}")
                c2.markdown(f"**🕐 Vaxt:** {a.get('sent_at','')[:16]}")
                with c3:
                    if a.get("url"):
                        st.link_button("🔗 Xəbərə Keç", a["url"])
                if a.get("summary"):
                    st.markdown("---")
                    st.markdown(a["summary"])
    else:
        st.info("📭 Tarixçə boşdur.")

st.divider()
st.markdown("<div style='text-align:center;color:#6b7280;font-size:0.75rem'>📰 DailyXeber Bot · Gemini AI · @dailyxeber</div>", unsafe_allow_html=True)
