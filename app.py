import streamlit as st
import pandas as pd
import requests
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. PERSISTENCE & DATA ---
SAVE_FILE = "draft_state.json"

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"draft_history": st.session_state.draft_history, "my_team": st.session_state.my_team}, f)

def load_state():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.draft_history, st.session_state.my_team = state["draft_history"], state["my_team"]
        st.rerun()

@st.cache_data(ttl=3600)
def get_injuries():
    try:
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5).json()['players']
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r if p.get('injury')}
    except: return {}

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        # Advanced Weighting: 60% Avg, 40% Last 3 Form
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_Avg'] * 0.4).round(1)
        return df
    except: return pd.DataFrame()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df, injuries = load_data(), get_injuries()

# --- 2. SIDEBAR COMMAND ---
with st.sidebar:
    st.title("🛡️ Command Center")
    num_teams = st.number_input("Total Teams", value=10, min_value=1)
    my_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=num_teams)
    
    st.divider()
    st.write("**Roster Requirements**")
    c_req1, c_req2 = st.columns(2)
    reqs = {
        'DEF': c_req1.number_input("DEF", value=4, min_value=0),
        'MID': c_req2.number_input("MID", value=6, min_value=0),
        'RUC': c_req1.number_input("RUC", value=1, min_value=0),
        'FWD': c_req2.number_input("FWD", value=4, min_value=0)
    }
    
    st.divider()
    if st.button("🔄 Recover Draft"): load_state()
    
    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist())
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    if st.button("CONFIRM PICK", type="primary", use_container_width=True):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            rnd = ((p_num - 1) // num_teams) + 1
            turn = (p_num - 1) % num_teams + 1 if rnd % 2 != 0 else num_teams - ((p_num - 1) % num_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == my_slot: st.session_state.my_team.append(selected)
            save_state()
            st.rerun()

# --- 3. DYNAMIC VORP CALCS ---
avail_df = df[~df['full_name'].isin(taken_names)].copy()
if not avail_df.empty:
    baselines = {}
    for pos in ['DEF', 'MID', 'RUC', 'FWD']:
        used = len(df[df['full_name'].isin(taken_names) & df['positions'].str.contains(pos)])
        slots_left = max(1, (reqs[pos] * num_teams) - used)
        pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Power_Rating', ascending=False)
        idx = min(len(pool)-1, slots_left - 1)
        baselines[pos] = pool.iloc[idx]['Power_Rating'] if not pool.empty else 80

    avail_df['VORP'] = avail_df.apply(lambda x: round(x['Power_Rating'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
    avail_df['Health'] = avail_df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

# --- 4. TABS ---
t1, t2, t3, t4 = st.tabs(["🎯 Board", "📋 My Team", "📈 League", "🏢 Rosters"])

with t1:
    curr_p = len(st.session_state.draft_history) + 1
    rnd = ((curr_p - 1) // num_teams) + 1
    turn = (curr_p - 1) % num_teams + 1 if rnd % 2 != 0 else num_teams - ((curr_p - 1) % num_teams)
    
    if turn == my_slot:
        st.success("### 🚨 YOUR TURN!")
        recs = avail_df.sort_values('VORP', ascending=False).head(3)
        cols = st.columns(3)
        for i, (idx, p) in enumerate(recs.iterrows()):
            cols[i].metric(p['full_name'], f"VORP +{p['VORP']}", p['positions'])
    
    st.subheader("Big Board")
    # Color scale logic for VORP
    def color_vorp(val):
        color = '#1b5e20' if val > 12 else '#2e7d32' if val > 6 else '#388e3c' if val > 0 else 'none'
        return f'background-color: {color}'

    display_df = avail_df[['full_name', 'positions', 'VORP', 'Power_Rating', 'Health']].sort_values('VORP', ascending=False).head(40)
    st.dataframe(display_df.style.applymap(color_vorp, subset=['VORP']), use_container_width=True, hide_index=True)

with t2:
    my_df = df[df['full_name'].isin(st.session_state.my_team)]
    st.table(my_df[['full_name', 'positions', 'Avg']])
    st.metric("Proj. Weekly Total", int(my_df['Avg'].sum()))

with t3:
    if st.session_state.draft_history:
        st.dataframe(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False), use_container_width=True)

with t4:
    view_t = st.radio("Inspect Team:", [f"Team {i}" for i in range(1, num_teams+1)], horizontal=True)
    tid = int(view_t.split(" ")[1])
    t_players = df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == tid])]
    cols = st.columns(4)
    for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
        with cols[i]:
            st.write(f"**{pos}**")
            p_list = t_players[t_players['positions'].str.contains(pos)]
            for idx, p in enumerate(p_list.itertuples()):
                if idx < reqs[pos]: st.success(p.full_name)
                else: st.info(f"🔄 {p.full_name}")
