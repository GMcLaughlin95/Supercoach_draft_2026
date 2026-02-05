import streamlit as st
import pandas as pd
import requests
import json
import os

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Supercoach War Room 2026", layout="wide")

# --- 2. PERSISTENCE LOGIC (SAVE/LOAD) ---
SAVE_FILE = "draft_state.json"

def save_state():
    state = {
        "draft_history": st.session_state.draft_history,
        "my_team": st.session_state.my_team
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.draft_history = state["draft_history"]
            st.session_state.my_team = state["my_team"]
        st.success("✅ Draft Restored!")
        st.rerun()

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_injury_data():
    try:
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5)
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r.json()['players'] if p['injury']}
    except: return {}

@st.cache_data
def load_and_score_players():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        # Advanced Weighting: 50% Season Avg, 30% Recent Form, 20% Reliability
        df['Power_Rating'] = (df['Avg'] * 0.5 + df['Last3_Avg'] * 0.3 + (df['gamesPlayed'] * 2) * 0.2).round(1)
        return df
    except: return pd.DataFrame()

# Initialize Session States
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df = load_and_score_players()
injuries = get_injury_data()

# --- 4. SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("🛡️ Draft Command")
    
    # Fix for st.number_input error using named arguments
    num_teams = st.number_input(label="Total Teams", value=10, min_value=1, step=1)
    my_slot = st.number_input(label="Your Draft Slot", value=5, min_value=1, max_value=num_teams, step=1)
    
    st.divider()
    st.subheader("💾 Backup")
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("Save Now"): save_state()
    if col_s2.button("Load Last"): load_state()
    
    st.divider()
    st.subheader("📢 Record Pick")
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_options = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist())
    
    selected_player = st.selectbox(label="Select Player", options=[""] + avail_options)
    
    if st.button("CONFIRM PICK", type="primary", use_container_width=True):
        if selected_player:
            pick_num = len(st.session_state.draft_history) + 1
            round_num = ((pick_num - 1) // num_teams) + 1
            # Snake Draft Logic
            if round_num % 2 != 0:
                turn = (pick_num - 1) % num_teams + 1
            else:
                turn = num_teams - ((pick_num - 1) % num_teams)
            
            pick_data = {"pick": pick_num, "round": round_num, "team": turn, "player": selected_player}
            st.session_state.draft_history.append(pick_data)
            
            if turn == my_slot:
                st.session_state.my_team.append(selected_player)
            
            save_state() # Auto-save every pick
            st.rerun()

# --- 5. MAIN INTERFACE ---
if not df.empty:
    tab1, tab2, tab3 = st.tabs(["🎯 Draft Board", "📋 My Team", "📈 League View"])

    with tab1:
        # Calculate Current Turn
        current_pick = len(st.session_state.draft_history) + 1
        curr_rnd = ((current_pick - 1) // num_teams) + 1
        if curr_rnd % 2 != 0: curr_turn = (current_pick - 1) % num_teams + 1
        else: curr_turn = num_teams - ((current_pick - 1) % num_teams)

        if curr_turn == my_slot:
            st.warning("⚠️ **YOUR TURN!**")
        
        # Available Players with Injury Tags
        st.subheader("Top Available Players")
        view_df = df[~df['full_name'].isin(taken_names)].copy()
        view_df['Injury_Status'] = view_df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))
        
        st.dataframe(
            view_df[['full_name', 'positions', 'Power_Rating', 'Avg', 'Injury_Status']]
            .sort_values('Power_Rating', ascending=False).head(30),
            use_container_width=True, hide_index=True
        )

    with tab2:
        st.subheader("Your Roster")
        my_players = df[df['full_name'].isin(st.session_state.my_team)]
        if not my_players.empty:
            st.table(my_players[['full_name', 'positions', 'Avg']])
            st.metric("Projected Weekly Score", int(my_players['Avg'].sum()))
        else:
            st.info("No players drafted yet.")

    with tab3:
        st.subheader("Draft History")
        if st.session_state.draft_history:
            history_df = pd.DataFrame(st.session_state.draft_history)
            st.dataframe(history_df.sort_values('pick', ascending=False), use_container_width=True)
        else:
            st.info("Draft hasn't started.")
else:
    st.error("Missing 'supercoach_data.csv'. Please upload the data file.")
