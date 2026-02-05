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

# --- ADDED: RESET FUNCTION ---
def reset_draft():
    st.session_state.draft_history = []
    st.session_state.my_team = []
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
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
        df.columns = [c.strip() for c in df.columns]
        if 'full_name' not in df.columns:
            df['full_name'] = (df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)).str.strip()
        df['Avg'] = pd.to_numeric(df.get('Avg', 0), errors='coerce').fillna(0)
        df['Last3_Avg'] = pd.to_numeric(df.get('Last3_Avg', 0), errors='coerce').fillna(0)
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_Avg'] * 0.4).round(1)
        df['VORP'] = 0.0
        df['Health'] = "✅ Fit"
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df, injuries = load_data(), get_injuries()

if not df.empty:
    df['Health'] = df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

# --- 2. HELPER FUNCTIONS ---
def get_current_turn(curr_pick, total_teams):
    if total_teams <= 0: return 1
    rnd = ((curr_pick - 1) // total_teams) + 1
    return (curr_pick - 1) % total_teams + 1 if rnd % 2 != 0 else total_teams - ((curr_pick - 1) % total_teams)

def check_roster_limit(player_name, team_id, user_inputs, history_list, data_df):
    player_row = data_df[data_df['full_name'] == player_name]
    if player_row.empty: return True, None, 0
    p_pos = player_row.iloc[0]['positions']
    team_p_names = [d['player'] for d in history_list if d['team'] == team_id]
    team_df = data_df[data_df['full_name'].isin(team_p_names)]
    for pos in ['DEF', 'MID', 'RUC', 'FWD']:
        if pos in p_pos:
            current_count = len(team_df[team_df['positions'].str.contains(pos, na=False)])
            if current_count >= user_inputs[pos] + 2:
                return False, pos, current_count
    ruc_c = len(team_df[team_df['positions'].str.contains('RUC', na=False)]) if 'RUC' in p_pos else 0
    return True, None, ruc_c

# --- 3. SIDEBAR COMMAND ---
with st.sidebar:
    st.title("🛡️ Command Center")
    num_teams = st.number_input("Total Teams", value=10, min_value=1)
    my_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=num_teams)
    
    st.divider()
    st.write("**Base Roster Settings**")
    c_req1, c_req2 = st.columns(2)
    user_inputs = {
        'DEF': c_req1.number_input("DEF", value=4, min_value=0),
        'MID': c_req2.number_input("MID", value=6, min_value=0),
        'RUC': c_req1.number_input("RUC", value=1, min_value=0),
        'FWD': c_req2.number_input("FWD", value=4, min_value=0)
    }
    
    st.divider()
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("💾 Save"): save_state()
    if col_s2.button("🔄 Recover"): load_state()
    
    # NEW: RESET BUTTON
    if st.button("🚨 RESET DRAFT", use_container_width=True, type="secondary"):
        reset_draft()
    
    if st.button("🤖 Sim to My Turn", use_container_width=True):
        while True:
            curr_p = len(st.session_state.draft_history) + 1
            turn = get_current_turn(curr_p, num_teams)
            if turn == my_slot: break
            taken_sim = [d['player'] for d in st.session_state.draft_history]
            avail_sim = df[~df['full_name'].isin(taken_sim)].sort_values('Power_Rating', ascending=False)
            if avail_sim.empty: break
            ai_choice = None
            for _, row in avail_sim.iterrows():
                fits, _, _ = check_roster_limit(row['full_name'], turn, user_inputs, st.session_state.draft_history, df)
                if fits:
                    ai_choice = row['full_name']
                    break
            if ai_choice:
                st.session_state.draft_history.append({"pick": curr_p, "team": turn, "player": ai_choice})
            else: break
        save_state(); st.rerun()
    
    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    can_confirm = True
    if selected:
        curr_p = len(st.session_state.draft_history) + 1
        turn = get_current_turn(curr_p, num_teams)
        allowed, pos_failed, ruc_count = check_roster_limit(selected, turn, user_inputs, st.session_state.draft_history, df)
        if "RUC" in df[df['full_name'] == selected]['positions'].values[0] and ruc_count == 2:
            st.warning(f"⚠️ Team {turn} drafting 3rd Ruckman. Absolute limit.")
        if not allowed:
            st.error(f"❌ Limit Reached: {pos_failed}")
            can_confirm = False

    if st.button("CONFIRM PICK", type="primary", use_container_width=True, disabled=not can_confirm):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, num_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == my_slot: st.session_state.my_team.append(selected)
            save_state(); st.rerun()

# --- 4. CALC VORP ---
if not df.empty:
    avail_df = df[~df['full_name'].isin(taken_names)].copy()
    if not avail_df.empty:
        baselines = {pos: (avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False).iloc[min(len(avail_df[avail_df['positions'].str.contains(pos, na=False)])-1, 12)]['Power_Rating'] if not avail_df[avail_df['positions'].str.contains(pos, na=False)].empty else 80) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
        avail_df['VORP'] = avail_df.apply(lambda x: round(x['Power_Rating'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
else: avail_df = pd.DataFrame()

# --- 5. TABS ---
t1, t2, t3, t4 = st.tabs(["🎯 Board", "📋 My Team", "📈 Log", "🏢 Analysis & Rosters"])

with t1:
    st.subheader("🎯 Big Board")
    if not avail_df.empty:
        cols_to_show = [c for c in ['full_name', 'positions', 'VORP', 'Power_Rating', 'Health'] if c in avail_df.columns]
        st.dataframe(avail_df[cols_to_show].sort_values('VORP', ascending=False).head(40), use_container_width=True, hide_index=True)
    else: st.info("No players available.")

with t2:
    st.subheader("My Squad")
    my_df = df[df['full_name'].isin(st.session_state.my_team)]
    if not my_df.empty:
        st.dataframe(my_df[['full_name', 'positions', 'Avg']], use_container_width=True, hide_index=True)
        st.metric("Projected Total", int(my_df['Avg'].sum()))

with t3:
    st.subheader("📈 Draft Log")
    if st.session_state.draft_history:
        log_df = pd.DataFrame(st.session_state.draft_history)
        st.dataframe(log_df.sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

with t4:
    # MOVED INSIDE TAB 4 AND PROPERLY INDENTED
    st.subheader("📊 League Power Rankings")
    team_stats = []
    for i in range(1, num_teams + 1):
        t_names = [d['player'] for d in st.session_state.draft_history if d['team'] == i]
        total_p = df[df['full_name'].isin(t_names)]['Power_Rating'].sum()
        team_stats.append({"Team": f"Team {i}", "Power": total_p})
    
    if team_stats:
        chart_df = pd.DataFrame(team_stats)
        st.bar_chart(chart_df.set_index("Team"), color="#2e7d32")
    
    st.divider()
    st.subheader("🏢 Opponent Rosters")
    view_t = st.radio("Inspect Team:", [f"Team {i}" for i in range(1, num_teams+1)], horizontal=True)
    tid = int(view_t.split(" ")[1])
    t_players = df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == tid])]
    
    cols = st.columns(4)
    for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
        with cols[i]:
            st.write(f"**{pos}**")
            p_list = t_players[t_players['positions'].str.contains(pos, na=False)]
            for p in p_list.itertuples():
                st.success(p.full_name)
