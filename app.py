import streamlit as st
import pandas as pd
import requests
import json
import os

# --- CONFIG ---
st.set_page_config(page_title="Supercoach War Room 2026", layout="wide")

# --- 1. DATA ENGINE ---
@st.cache_data
def load_and_prep_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('.', '')
        low_cols = {c.lower(): c for c in df.columns}
        
        # Identity
        f_col, l_col = low_cols.get('first_name'), low_cols.get('last_name')
        if f_col and l_col:
            df['full_name'] = (df[f_col].astype(str) + ' ' + df[l_col].astype(str)).str.strip()
        else:
            name_col = low_cols.get('player') or low_cols.get('name') or low_cols.get('full_name')
            df['full_name'] = df[name_col] if name_col else "Unknown"

        # Stats
        for met in ['avg', 'last3_avg']:
            orig = low_cols.get(met)
            df[met.capitalize()] = pd.to_numeric(df[orig], errors='coerce').fillna(0) if orig else 0
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_avg'] * 0.4).round(1)

        # Bye Map
        bye_map = {'Adelaide': 14, 'Brisbane': 12, 'Carlton': 14, 'Collingwood': 13, 'Essendon': 13, 'Fremantle': 12, 'Geelong': 14, 'Gold Coast': 12, 'GWS': 13, 'Hawthorn': 15, 'Melbourne': 14, 'North Melbourne': 15, 'Port Adelaide': 12, 'Richmond': 15, 'St Kilda': 12, 'Sydney': 13, 'West Coast': 14, 'Western Bulldogs': 15}
        t_col = low_cols.get('team') or low_cols.get('club')
        df['Bye'] = df[t_col].map(bye_map).fillna(0).astype(int) if t_col else 0
        
        df['VORP'] = 0.0
        df['Health'] = "✅ Fit"
        return df
    except Exception as e:
        st.error(f"Setup Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_injury_map():
    try:
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5).json()['players']
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r if p.get('injury')}
    except: return {}

# --- 2. STATE ---
SAVE_FILE = "draft_state.json"
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"history": st.session_state.draft_history, "mine": st.session_state.my_team}, f)

df, injuries = load_and_prep_data(), get_injury_map()
if not df.empty:
    df['Health'] = df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

# Helper for Snake Logic
def get_current_turn(curr_pick, total_teams):
    rnd = ((curr_pick - 1) // total_teams) + 1
    if rnd % 2 != 0:
        return (curr_pick - 1) % total_teams + 1
    else:
        return total_teams - ((curr_pick - 1) % total_teams)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ Draft War Room")
    n_teams = st.number_input(label="Total Teams", value=10, min_value=1)
    m_slot = st.number_input(label="Your Slot", value=5, min_value=1, max_value=n_teams)
    
    st.divider()
    
    # --- SIMULATE BUTTON ---
    if st.button("🤖 Simulate Until My Turn", use_container_width=True):
        while True:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, n_teams)
            
            # Stop if it's the user's turn
            if turn == m_slot:
                st.toast("It's your turn!")
                break
            
            # AI Pick Logic
            taken = [d['player'] for d in st.session_state.draft_history]
            avail = df[~df['full_name'].isin(taken)].sort_values('Power_Rating', ascending=False)
            if avail.empty: break
            
            ai_pick = avail.iloc[0]['full_name']
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": ai_pick})
        save_state()
        st.rerun()

    if st.button("🚨 RESET DRAFT", type="secondary", use_container_width=True):
        if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
        st.session_state.draft_history, st.session_state.my_team = [], []
        st.rerun()

    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox(label="Your Pick:", options=[""] + avail_list)
    
    if st.button("CONFIRM MY PICK", type="primary", use_container_width=True):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, n_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == m_slot:
                st.session_state.my_team.append(selected)
            save_state()
            st.rerun()

# --- 4. MAIN UI ---
if not df.empty:
    avail_df = df[~df['full_name'].isin(taken_names)].copy()
    if not avail_df.empty:
        # Dynamic VORP
        for pos in ['DEF', 'MID', 'RUC', 'FWD']:
            pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Power_Rating', ascending=False)
            baseline = pool.iloc[min(len(pool)-1, 10)]['Power_Rating'] if not pool.empty else 80
            avail_df.loc[avail_df['positions'].str.contains(pos), 'VORP'] = (avail_df['Power_Rating'] - baseline).round(1)

    t1, t2, t3 = st.tabs(["🎯 Big Board", "📋 My Team", "📈 Draft Log"])

    with t1:
        p_num = len(st.session_state.draft_history) + 1
        turn = get_current_turn(p_num, n_teams)
        if turn == m_slot:
            st.warning(f"### 🚨 YOUR TURN (Pick {p_num})")
        else:
            st.info(f"Currently Picking: Team {turn} (Pick {p_num})")

        display_cols = ['full_name', 'positions', 'VORP', 'Power_Rating', 'Bye', 'Health']
        st.dataframe(avail_df[display_cols].sort_values('VORP', ascending=False).head(50), use_container_width=True, hide_index=True)

    with t2:
        st.subheader("My Roster")
        st.dataframe(df[df['full_name'].isin(st.session_state.my_team)][['full_name', 'positions', 'Avg', 'Bye']], use_container_width=True)

    with t3:
        st.subheader("Draft History")
        if st.session_state.draft_history:
            st.dataframe(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False), use_container_width=True)
