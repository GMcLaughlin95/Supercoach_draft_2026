import streamlit as st
import pandas as pd
import requests
import json
import os
import time

st.set_page_config(page_title="Supercoach War Room Ultra", layout="wide", initial_sidebar_state="expanded")

# --- 1. DATA & STATE ENGINE ---
SAVE_FILE = "draft_state.json"

@st.cache_data
def load_data():
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

        # Scores
        for met in ['avg', 'last3_avg']:
            orig = low_cols.get(met)
            df[met.capitalize()] = pd.to_numeric(df[orig], errors='coerce').fillna(0) if orig else 0
        
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_avg'] * 0.4).round(1)
        return df
    except: return pd.DataFrame()

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"history": st.session_state.draft_history, "mine": st.session_state.my_team}, f)

def reset_draft():
    if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
    st.session_state.draft_history = []
    st.session_state.my_team = []
    st.rerun()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df = load_data()

# --- 2. SIDEBAR COMMANDS ---
with st.sidebar:
    st.title("⚔️ Command Center")
    n_teams = st.number_input("Total Teams", 10, min_value=1)
    m_slot = st.number_input("Your Slot", 5, min_value=1, max_value=n_teams)
    
    st.divider()
    if st.button("🚨 RESET DRAFT", type="secondary", use_container_width=True):
        reset_draft()
        
    if st.button("🤖 RUN FULL SIMULATION"):
        with st.status("Simulating Draft..."):
            reset_draft() # Start clean
            total_picks = n_teams * 15 # Simulate 15 rounds
            for i in range(total_picks):
                taken = [d['player'] for d in st.session_state.draft_history]
                avail = df[~df['full_name'].isin(taken)].sort_values('Power_Rating', ascending=False)
                if not avail.empty:
                    pick_p = avail.iloc[0]['full_name']
                    p_num = len(st.session_state.draft_history) + 1
                    rnd = ((p_num - 1) // n_teams) + 1
                    turn = (p_num - 1) % n_teams + 1 if rnd % 2 != 0 else n_teams - ((p_num - 1) % n_teams)
                    st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": pick_p})
                    if turn == m_slot: st.session_state.my_team.append(pick_p)
            save_state()
            st.rerun()

    st.divider()
    taken = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    if st.button("CONFIRM PICK", type="primary", use_container_width=True):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            rnd = ((p_num - 1) // n_teams) + 1
            turn = (p_num - 1) % n_teams + 1 if rnd % 2 != 0 else n_teams - ((p_num - 1) % n_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == m_slot: st.session_state.my_team.append(selected)
            save_state()
            st.rerun()

# --- 3. THE TABS ---
if not df.empty:
    t1, t2, t3, t4, t5 = st.tabs(["🎯 Board", "📋 My Team", "📈 Log", "🏢 Rosters", "🤝 Trade Calc"])

    with t1:
        st.subheader("Big Board")
        # VORP logic simplified for speed
        pool = df[~df['full_name'].isin(taken)].sort_values('Power_Rating', ascending=False).head(50)
        st.dataframe(pool[['full_name', 'positions', 'Power_Rating', 'Avg']], use_container_width=True, hide_index=True)

    with t2:
        my_df = df[df['full_name'].isin(st.session_state.my_team)]
        st.table(my_df[['full_name', 'positions', 'Avg']])

    with t5:
        st.header("🤝 Trade Calculator")
        st.caption("Compare the total 'Power' of players being exchanged.")
        
        col_t1, col_t2 = st.columns(2)
        
        with col_t1:
            st.subheader("Giving Away")
            give_players = st.multiselect("Select your players:", st.session_state.my_team)
            give_val = df[df['full_name'].isin(give_players)]['Power_Rating'].sum()
            st.metric("Total Value Out", round(give_val, 1))

        with col_t2:
            st.subheader("Receiving")
            all_drafted = [d['player'] for d in st.session_state.draft_history if d['player'] not in st.session_state.my_team]
            get_players = st.multiselect("Select target players:", all_drafted)
            get_val = df[df['full_name'].isin(get_players)]['Power_Rating'].sum()
            st.metric("Total Value In", round(get_val, 1))

        diff = get_val - give_val
        if diff > 0: st.success(f"✅ Trade Gain: +{round(diff, 1)} Power Points")
        elif diff < 0: st.error(f"❌ Trade Loss: {round(diff, 1)} Power Points")
        else: st.info("Select players to compare values.")

else:
    st.error("Missing supercoach_data.csv")
