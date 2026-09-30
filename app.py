from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "savings.db"
JST = ZoneInfo("Asia/Tokyo")

THEMES = {
    "セージ": {"main": "#9EAD9A", "dark": "#566A5B", "soft": "#EEF2ED"},
    "ダスティブルー": {"main": "#91A8B8", "dark": "#4D6574", "soft": "#ECF2F5"},
    "モーヴ": {"main": "#B39AAF", "dark": "#725C6E", "soft": "#F4EEF3"},
    "テラコッタ": {"main": "#C98F7A", "dark": "#835847", "soft": "#F8EFEB"},
    "サンド": {"main": "#C4AD8D", "dark": "#74634D", "soft": "#F7F2EB"},
    "スモーキーミント": {"main": "#86AAA0", "dark": "#456B61", "soft": "#EAF3F1"},
}

GENRES = {
    "食費": "🍳", "外食": "☕", "買い物": "🛍️", "交通": "🚃", "光熱費": "💡",
    "通信": "📱", "趣味": "🎮", "美容・健康": "🌿", "子ども": "🧸", "その他": "✨",
}

st.set_page_config(page_title="ういた！", page_icon="🌱", layout="centered")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS savings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                genre TEXT NOT NULL,
                title TEXT NOT NULL,
                memo TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL CHECK(amount > 0),
                member_id INTEGER,
                created_at TEXT NOT NULL,
                likes INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(member_id) REFERENCES members(id)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        now = datetime.now(JST).isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO members(name, created_at) VALUES (?, ?)", ("わたし", now))
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('theme', 'セージ')")


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_setting(key: str, default: str) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def money(value: int) -> str:
    return f"¥{int(value):,}"


def e(value: object) -> str:
    return html.escape(str(value or ""))


def add_saving(genre: str, title: str, memo: str, amount: int, member_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO savings(genre, title, memo, amount, member_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (genre, title.strip(), memo.strip(), int(amount), member_id, datetime.now(JST).isoformat(timespec="seconds")),
        )


def like_saving(record_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE savings SET likes = likes + 1 WHERE id = ?", (record_id,))


def delete_saving(record_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM savings WHERE id = ?", (record_id,))


def load_records(where: str = "", params: tuple = ()) -> pd.DataFrame:
    sql = """
        SELECT s.id, s.genre, s.title, s.memo, s.amount, s.created_at, s.likes,
               COALESCE(m.name, '未設定') AS member_name
        FROM savings s LEFT JOIN members m ON s.member_id = m.id
    """
    if where:
        sql += " WHERE " + where
    sql += " ORDER BY s.created_at DESC, s.id DESC"
    return query_df(sql, params)


def render_record(row: pd.Series, theme_dark: str, key_prefix: str) -> None:
    icon = GENRES.get(row["genre"], "✨")
    created = datetime.fromisoformat(row["created_at"]).astimezone(JST).strftime("%Y/%m/%d %H:%M")
    memo_text = e(row["memo"]) if row["memo"] else "メモなし"
    st.markdown(
        f"""
        <div class="record-card">
          <div class="record-icon">{icon}</div>
          <div class="record-body">
            <div class="record-title">{e(row['title'])}</div>
            <div class="record-memo">{memo_text}</div>
            <div class="record-meta">{e(row['member_name'])} ・ {created} ・ {e(row['genre'])}</div>
          </div>
          <div class="record-amount" style="color:{theme_dark}">+{money(row['amount'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1.4, 1, 5])
    if c1.button(f"♡ {int(row['likes'])}", key=f"{key_prefix}_like_{int(row['id'])}", use_container_width=True):
        like_saving(int(row["id"]))
        st.rerun()
    with c2.popover("•••", use_container_width=True):
        st.caption("この記録の操作")
        if st.button("削除する", key=f"{key_prefix}_delete_{int(row['id'])}", type="secondary"):
            delete_saving(int(row["id"]))
            st.rerun()


init_db()
current_theme_name = get_setting("theme", "セージ")
if current_theme_name not in THEMES:
    current_theme_name = "セージ"
theme = THEMES[current_theme_name]

now = datetime.now(JST)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
summary = query_df(
    """
    SELECT
      COALESCE(SUM(CASE WHEN created_at >= ? THEN amount ELSE 0 END), 0) AS month_total,
      COALESCE(SUM(CASE WHEN created_at >= ? THEN amount ELSE 0 END), 0) AS today_total
    FROM savings
    """,
    (month_start, today_start),
).iloc[0]

st.markdown(
    f"""
    <style>
      :root {{ --main:{theme['main']}; --dark:{theme['dark']}; --soft:{theme['soft']}; }}
      .stApp {{ background:#FBFAF8; color:#29302D; }}
      .block-container {{ max-width:780px; padding-top:0.5rem; padding-bottom:5rem; }}
      [data-testid="stHeader"] {{ background:transparent; }}
      .sticky-summary {{ position:sticky; top:0.5rem; z-index:999; background:var(--main); border-radius:24px;
        padding:20px 22px; box-shadow:0 12px 30px rgba(48,55,51,.14); margin-bottom:18px; }}
      .summary-grid {{ display:flex; align-items:center; justify-content:space-between; gap:20px; }}
      .summary-label,.summary-foot {{ font-size:.78rem; font-weight:700; color:#fff; opacity:.95; }}
      .summary-amount {{ font-size:2.25rem; line-height:1.1; font-weight:900; color:#fff; letter-spacing:-.04em; margin:4px 0; }}
      .today-pill {{ white-space:nowrap; background:#fff; color:var(--dark); padding:12px 16px; border-radius:999px; font-weight:900; box-shadow:0 4px 12px rgba(0,0,0,.08); }}
      .section-title {{ margin:18px 0 8px; font-size:1.15rem; font-weight:900; }}
      .record-card {{ display:grid; grid-template-columns:58px minmax(0,1fr) auto; gap:14px; align-items:center; background:#fff;
        border:1px solid #ECEAE6; border-radius:20px; padding:16px; margin-top:10px; box-shadow:0 5px 16px rgba(48,55,51,.055); }}
      .record-icon {{ width:52px; height:52px; display:flex; align-items:center; justify-content:center; border-radius:17px; background:var(--soft); font-size:1.7rem; }}
      .record-title {{ font-family:Arial,'Noto Sans JP',sans-serif; font-weight:900; font-size:1rem; color:#252B28; }}
      .record-memo,.record-meta {{ font-family:Arial,'Noto Sans JP',sans-serif; color:#9A9D9B; font-size:.78rem; margin-top:3px; overflow-wrap:anywhere; }}
      .record-amount {{ font-weight:900; font-size:1.05rem; white-space:nowrap; }}
      div[data-testid="stForm"] {{ background:#fff; border:1px solid #ECEAE6; border-radius:22px; padding:10px 18px 18px; }}
      .stButton > button, .stFormSubmitButton > button {{ border-radius:14px; font-weight:800; }}
      .stFormSubmitButton > button {{ background:var(--dark); color:white; border:none; }}
      @media (max-width:560px) {{
        .block-container {{ padding-left:12px; padding-right:12px; }}
        .sticky-summary {{ top:.25rem; border-radius:20px; padding:16px; }}
        .summary-amount {{ font-size:1.85rem; }} .today-pill {{ padding:10px 12px; font-size:.82rem; }}
        .record-card {{ grid-template-columns:50px minmax(0,1fr); }}
        .record-icon {{ width:46px; height:46px; }} .record-amount {{ grid-column:2; margin-top:2px; }}
      }}
    </style>
    <div class="sticky-summary">
      <div class="summary-grid">
        <div>
          <div class="summary-label">今月</div>
          <div class="summary-amount">{money(int(summary['month_total']))}</div>
          <div class="summary-foot">浮いた！</div>
        </div>
        <div class="today-pill">本日 +{money(int(summary['today_total']))}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

home_tab, history_tab, settings_tab = st.tabs(["🌱 直近の記録", "🗓️ 月別の履歴", "⚙️ 設定"])

with home_tab:
    st.markdown('<div class="section-title">節約を記録する</div>', unsafe_allow_html=True)
    members = query_df("SELECT id, name FROM members ORDER BY id")
    member_options = {row["name"]: int(row["id"]) for _, row in members.iterrows()}
    with st.form("saving_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        genre = c1.selectbox("ジャンル", list(GENRES), format_func=lambda x: f"{GENRES[x]}  {x}")
        member_name = c2.selectbox("記録したメンバー", list(member_options))
        title = st.text_input("節約したもの", placeholder="例：コンビニを我慢してお弁当にした")
        memo = st.text_area("メモ", placeholder="例：家族3人分のお昼代", height=80)
        amount = st.number_input("いくら節約した？", min_value=1, max_value=10_000_000, value=300, step=100)
        submitted = st.form_submit_button("＋ 記録する", use_container_width=True)
        if submitted:
            if not title.strip():
                st.error("「節約したもの」を入力してね。")
            else:
                add_saving(genre, title, memo, int(amount), member_options[member_name])
                st.success(f"{money(int(amount))} の節約を記録したよ！")
                st.rerun()

    st.markdown('<div class="section-title">直近の記録</div>', unsafe_allow_html=True)
    recent = load_records().head(8)
    if recent.empty:
        st.info("まだ記録がありません。最初の『浮いた！』を登録してみよう 🌱")
    else:
        for _, record in recent.iterrows():
            render_record(record, theme["dark"], "recent")

with history_tab:
    records = load_records()
    if records.empty:
        st.info("月別の履歴は、記録を追加すると表示されます。")
    else:
        records["month"] = pd.to_datetime(records["created_at"]).dt.strftime("%Y年%m月")
        month_options = list(records["month"].drop_duplicates())
        selected_month = st.selectbox("表示する月", month_options)
        monthly = records[records["month"] == selected_month]
        st.metric("この月に浮いた金額", money(int(monthly["amount"].sum())))
        st.caption(f"{len(monthly)}件の記録")
        for _, record in monthly.iterrows():
            render_record(record, theme["dark"], f"history_{selected_month}")

with settings_tab:
    st.subheader("テーマカラー")
    selected_theme = st.selectbox("好きなくすみカラーを選択", list(THEMES), index=list(THEMES).index(current_theme_name))
    palette = THEMES[selected_theme]
    st.markdown(
        f'<div style="height:72px;border-radius:18px;background:{palette["main"]};display:flex;align-items:center;padding:0 20px;color:white;font-weight:900;">{e(selected_theme)} プレビュー</div>',
        unsafe_allow_html=True,
    )
    if st.button("この色に変更", use_container_width=True):
        set_setting("theme", selected_theme)
        st.rerun()

    st.divider()
    st.subheader("共有メンバー")
    member_rows = query_df("SELECT id, name FROM members ORDER BY id")
    for _, member in member_rows.iterrows():
        left, right = st.columns([5, 1])
        new_name = left.text_input("メンバー名", value=member["name"], key=f"member_name_{member['id']}", label_visibility="collapsed")
        if right.button("保存", key=f"member_save_{member['id']}"):
            if new_name.strip():
                try:
                    with get_connection() as conn:
                        conn.execute("UPDATE members SET name = ? WHERE id = ?", (new_name.strip(), int(member["id"])))
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("同じ名前のメンバーがいます。")

    with st.form("add_member_form", clear_on_submit=True):
        new_member = st.text_input("新しいメンバー", placeholder="例：パパ、ママ、子ども")
        if st.form_submit_button("メンバーを追加", use_container_width=True):
            if new_member.strip():
                try:
                    with get_connection() as conn:
                        conn.execute(
                            "INSERT INTO members(name, created_at) VALUES (?, ?)",
                            (new_member.strip(), datetime.now(JST).isoformat(timespec="seconds")),
                        )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("同じ名前のメンバーがいます。")

    st.divider()
    st.caption("記録は app.py と同じフォルダの savings.db に保存されます。家族で共用する場合は、同じStreamlitサーバーへアクセスしてください。")
