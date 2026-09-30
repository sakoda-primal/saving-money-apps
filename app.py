from __future__ import annotations
import html, sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

DB_PATH=Path(__file__).with_name('savings.db'); JST=ZoneInfo('Asia/Tokyo')
THEMES={'セージ':('#9EAD9A','#566A5B','#EEF2ED'),'ダスティブルー':('#91A8B8','#4D6574','#ECF2F5'),'モーヴ':('#B39AAF','#725C6E','#F4EEF3'),'テラコッタ':('#C98F7A','#835847','#F8EFEB'),'サンド':('#C4AD8D','#74634D','#F7F2EB'),'スモーキーミント':('#86AAA0','#456B61','#EAF3F1')}
GENRES={'食費':'🍳','外食':'☕','買い物':'🛍️','交通':'🚃','光熱費':'💡','通信':'📱','趣味':'🎮','美容・健康':'🌿','子ども':'🧸','その他':'✨'}
st.set_page_config(page_title='ういた！',page_icon='🌱',layout='centered')

def conn():
    c=sqlite3.connect(DB_PATH,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS savings(id INTEGER PRIMARY KEY AUTOINCREMENT,genre TEXT NOT NULL,title TEXT NOT NULL,memo TEXT NOT NULL DEFAULT '',amount INTEGER NOT NULL CHECK(amount>0),member_id INTEGER,created_at TEXT NOT NULL,likes INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(member_id) REFERENCES members(id));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS record_likes(
          saving_id INTEGER NOT NULL,
          member_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(saving_id,member_id),
          FOREIGN KEY(saving_id) REFERENCES savings(id) ON DELETE CASCADE,
          FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
        );''')
        now=datetime.now(JST).isoformat(timespec='seconds')
        c.execute('INSERT OR IGNORE INTO members(name,created_at) VALUES(?,?)',('わたし',now))
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme','セージ')")

def df(sql,params=()):
    with conn() as c:return pd.read_sql_query(sql,c,params=params)
def esc(x):return html.escape(str(x or ''))
def money(x):return f'¥{int(x):,}'
def setting(k,d):
    with conn() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone(); return r['value'] if r else d
def set_setting(k,v):
    with conn() as c:c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
def add_saving(g,t,m,a,mid):
    with conn() as c:c.execute('INSERT INTO savings(genre,title,memo,amount,member_id,created_at) VALUES(?,?,?,?,?,?)',(g,t.strip(),m.strip(),int(a),mid,datetime.now(JST).isoformat(timespec='seconds')))
def delete_saving(sid):
    with conn() as c:c.execute('DELETE FROM record_likes WHERE saving_id=?',(sid,)); c.execute('DELETE FROM savings WHERE id=?',(sid,))
def delete_member(mid):
    with conn() as c:c.execute('DELETE FROM record_likes WHERE member_id=?',(mid,)); c.execute('UPDATE savings SET member_id=NULL WHERE member_id=?',(mid,)); c.execute('DELETE FROM members WHERE id=?',(mid,))
def toggle_member_like(sid,mid):
    with conn() as c:
        hit=c.execute('SELECT 1 FROM record_likes WHERE saving_id=? AND member_id=?',(sid,mid)).fetchone()
        if hit:c.execute('DELETE FROM record_likes WHERE saving_id=? AND member_id=?',(sid,mid))
        else:c.execute('INSERT INTO record_likes(saving_id,member_id,created_at) VALUES(?,?,?)',(sid,mid,datetime.now(JST).isoformat(timespec='seconds')))
def records(active_mid):
    return df('''SELECT s.id,s.genre,s.title,s.memo,s.amount,s.created_at,COALESCE(m.name,'未設定') member_name,
      COUNT(rl.member_id) like_count,
      MAX(CASE WHEN rl.member_id=? THEN 1 ELSE 0 END) is_liked
      FROM savings s LEFT JOIN members m ON s.member_id=m.id LEFT JOIN record_likes rl ON rl.saving_id=s.id
      GROUP BY s.id ORDER BY s.created_at DESC,s.id DESC''',(active_mid,))
def render_record(r,dark,prefix,active_mid):
    created=datetime.fromisoformat(r.created_at).astimezone(JST).strftime('%Y/%m/%d %H:%M')
    with st.container(border=True):
        a,b,c=st.columns([.8,4.6,1.8],vertical_alignment='center')
        a.markdown(f'<div class="record-icon">{GENRES.get(r.genre,"✨")}</div>',unsafe_allow_html=True)
        b.markdown(f'<div class="record-title">{esc(r.title)}</div>',unsafe_allow_html=True)
        if r.memo:b.markdown(f'<div class="muted">{esc(r.memo)}</div>',unsafe_allow_html=True)
        b.markdown(f'<div class="muted">{esc(r.member_name)} ・ {created}</div>',unsafe_allow_html=True)
        c.markdown(f'<div class="amount" style="color:{dark}">+{money(r.amount)}</div>',unsafe_allow_html=True)
        liked=bool(r.is_liked); label=f'{"♥" if liked else "♡"} {int(r.like_count)}'
        if c.button(label,key=f'{prefix}_like_{r.id}',type='primary' if liked else 'secondary',width='stretch'):
            toggle_member_like(int(r.id),active_mid); st.rerun()
        with c.popover('•••',width='stretch'):
            if st.button('削除を確定',key=f'{prefix}_del_{r.id}',width='stretch'):
                delete_saving(int(r.id)); st.rerun()

init_db(); members=df('SELECT id,name FROM members ORDER BY id'); ids=[int(x) for x in members.id]
if st.session_state.get('active_member_id') not in ids:st.session_state.active_member_id=ids[0]
active_mid=st.selectbox('現在のメンバー',ids,index=ids.index(st.session_state.active_member_id),format_func=lambda x:members.loc[members.id==x,'name'].iloc[0],key='active_member_id')
name=members.loc[members.id==active_mid,'name'].iloc[0]
theme_name=setting('theme','セージ'); main,dark,soft=THEMES.get(theme_name,THEMES['セージ'])
now=datetime.now(JST); ms=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0).isoformat(); ts=now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
sumrow=df('SELECT COALESCE(SUM(CASE WHEN created_at>=? THEN amount ELSE 0 END),0) month_total,COALESCE(SUM(CASE WHEN created_at>=? THEN amount ELSE 0 END),0) today_total FROM savings',(ms,ts)).iloc[0]
st.markdown(f'''<style>:root{{--main:{main};--dark:{dark};--soft:{soft}}}.block-container{{max-width:780px;padding-top:.5rem}}.sticky{{position:sticky;top:.5rem;z-index:99;background:var(--main);padding:18px;border-radius:14px;color:white;display:flex;justify-content:space-between;align-items:center;box-shadow:0 8px 20px #0002}}.big{{font-size:2rem;font-weight:900}}.pill{{background:white;color:var(--dark);padding:10px 14px;border-radius:8px;font-weight:800}}.record-icon{{background:var(--soft);border-radius:9px;font-size:1.6rem;padding:10px;text-align:center}}.record-title{{font-weight:900}}.muted{{color:#999;font-size:.78rem;margin-top:3px}}.amount{{font-weight:900;text-align:right;margin-bottom:5px}}div[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:10px}}</style><div class="sticky"><div><small>今月</small><div class="big">{money(sumrow.month_total)}</div><small>浮いた！</small></div><div class="pill">本日 +{money(sumrow.today_total)}</div></div>''',unsafe_allow_html=True)
st.caption(f'現在のメンバー：{name} ｜ いいねはメンバーごとにON／OFFされます')
home,history,settings=st.tabs(['🌱 直近の記録','🗓️ 月別の履歴','⚙️ 設定'])
with home:
    with st.form('saving_form',clear_on_submit=True):
        c1,c2=st.columns(2); genre=c1.selectbox('ジャンル',list(GENRES),format_func=lambda x:f'{GENRES[x]} {x}'); recorder=c2.selectbox('記録したメンバー',ids,index=ids.index(active_mid),format_func=lambda x:members.loc[members.id==x,'name'].iloc[0])
        title=st.text_input('節約したもの'); memo=st.text_area('メモ'); amount=st.number_input('いくら節約した？',min_value=1,max_value=10_000_000,value=None,step=100,placeholder='金額を入力')
        if st.form_submit_button('＋ 記録する',width='stretch'):
            if not title.strip():st.error('「節約したもの」を入力してね。')
            elif amount is None:st.error('節約した金額を入力してね。')
            else:add_saving(genre,title,memo,amount,recorder); st.rerun()
    data=records(active_mid).head(8)
    if data.empty:st.info('まだ記録がありません。')
    for _,r in data.iterrows():render_record(r,dark,'recent',active_mid)
with history:
    data=records(active_mid)
    if data.empty:st.info('記録を追加すると表示されます。')
    else:
        data['month']=pd.to_datetime(data.created_at).dt.strftime('%Y年%m月'); month=st.selectbox('表示する月',list(data.month.drop_duplicates())); monthly=data[data.month==month]; st.metric('この月に浮いた金額',money(monthly.amount.sum()))
        for _,r in monthly.iterrows():render_record(r,dark,f'history_{month}',active_mid)
with settings:
    chosen=st.selectbox('テーマカラー',list(THEMES),index=list(THEMES).index(theme_name))
    if st.button('この色に変更',width='stretch'):set_setting('theme',chosen); st.rerun()
    st.divider(); st.subheader('共有メンバー')
    member_rows=df('SELECT id,name FROM members ORDER BY id')
    for _,m in member_rows.iterrows():
        x,y,z=st.columns([4.8,1,1]); new=x.text_input('メンバー名',m['name'],key=f'mn_{m.id}',label_visibility='collapsed')
        if y.button('保存',key=f'ms_{m.id}',width='stretch'):
            try:
                with conn() as c:c.execute('UPDATE members SET name=? WHERE id=?',(new.strip(),int(m.id)))
                st.rerun()
            except sqlite3.IntegrityError:st.error('同じ名前のメンバーがいます。')
        with z.popover('削除',width='stretch'):
            if len(member_rows)<=1:st.caption('最後の1人は削除できません。')
            else:
                st.caption('過去の記録は残り、メンバー名は「未設定」になります。このメンバーのいいねは削除されます。')
                if st.button('削除を確定',key=f'md_{m.id}',width='stretch'):delete_member(int(m.id)); st.session_state.pop('active_member_id',None); st.rerun()
    with st.form('add_member',clear_on_submit=True):
        new=st.text_input('新しいメンバー')
        if st.form_submit_button('メンバーを追加',width='stretch') and new.strip():
            try:
                with conn() as c:c.execute('INSERT INTO members(name,created_at) VALUES(?,?)',(new.strip(),datetime.now(JST).isoformat(timespec='seconds')))
                st.rerun()
            except sqlite3.IntegrityError:st.error('同じ名前のメンバーがいます。')
