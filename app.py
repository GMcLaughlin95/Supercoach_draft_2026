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
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_Avg'] * 0.4).round(1)
        return df
    except: return pd.DataFrame()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df, injuries = load_data(), get_injuries()

# --- 2. HELPER FUNCTIONS ---
def get_current_turn(curr_pick, total_teams):
    rnd = ((curr_pick - 1) // total_teams) + 1
    return (curr_pick - 1) % total_teams + 1 if rnd % 2 != 0 else total_teams - ((curr_pick - 1) % total_teams)

def check_roster_limit(player_name, team_id, roster_reqs, history_list, data_df):
    """Returns True if the team CAN draft the player without exceeding requirements."""
    player_data = data_df[data_df['full_name'] == player_name].iloc[0]
    p_pos = player_data['positions']
    
    # Get current players for this team
    team_p_names = [d['player'] for d in history_list if d['team'] == team_id]
    team_df = data_df[data_df['full_name'].isin(team_p_names)]
    
    # Check each position tag the player has (e.g. MID/FWD)
    for pos in ['DEF', 'MID', 'RUC', 'FWD']:
        if pos in p_pos:
            current_count = len(team_df[team_df['positions'].str.contains(pos)])
            if current_count >= roster_reqs[pos]:
                return False, pos
    return True, None

# --- 3. SIDEBAR COMMAND ---
with st.sidebar:
    st.title("🛡️ Command Center")
    num_teams = st.number_input("Total Teams", value=10, min_value=1)
    my_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=num_teams)
    
    st.divider()
    st.write("**Roster Limits (Max per Pos)**")
    c_req1, c_req2 = st.columns(2)
    reqs = {
        'DEF': c_req1.number_input("DEF", value=4, min_value=0),
        'MID': c_req2.number_input("MID", value=6, min_value=0),
        'RUC': c_req1.number_input("RUC", value=1, min_value=0),
        'FWD': c_req2.number_input("FWD", value=4, min_value=0)
    }
    
    st.divider()
    col_save1, col_save2 = st.columns(2)
    if col_save1.button("💾 Save Progress"): 
        save_state()
        st.toast("Draft Saved!")
    if col_save2.button("🔄 Recover Draft"): load_state()
    
    # --- SMART AI SIMULATION ---
    if st.button("🤖 Simulate to My Turn", use_container_width=True):
        while True:
            curr_p = len(st.session_state.draft_history) + 1
            turn = get_current_turn(curr_p, num_teams)
            if turn == my_slot:
                st.toast("It's your turn!")
                break
            
            taken_sim = [d['player'] for d in st.session_state.draft_history]
            avail_sim = df[~df['full_name'].isin(taken_sim)].sort_values('Power_Rating', ascending=False)
            
            if avail_sim.empty: break
            
            # Find the best player that fits AI's roster limits
            ai_choice = None
            for _, row in avail_sim.iterrows():
                fits, _ = check_roster_limit(row['full_name'], turn, reqs, st.session_state.draft_history, df)
                if fits:
                    ai_choice = row['full_name']
                    break
            
            if ai_choice:
                st.session_state.draft_history.append({"pick": curr_p, "team": turn, "player": ai_choice})
            else:
                break # All available players exceed limits (roster full)
        
        save_state()
        st.rerun()
    
    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist())
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    # --- USER VALIDATION ---
    can_pick = True
    if selected:
        curr_p = len(st.session_state.draft_history) + 1
        turn = get_current_turn(curr_p, num_teams)
        allowed, pos_failed = check_roster_limit(selected, turn, reqs, st.session_state.draft_history, df)
        if not allowed:
            st.error(f"⚠️ Cannot pick {selected}. Team {turn} already has maximum {pos_failed}s ({reqs[pos_failed]}).")
            can_pick = False

    if st.button("CONFIRM PICK", type="primary", use_container_width=True, disabled=not can_pick):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, num_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == my_slot: st.session_state.my_team.append(selected)
            save_state()
            st.rerun()

# --- 4. DYNAMIC VORP CALCS ---
avail_df = df[~df['full_name'].isin(taken_names)].copy()
if not avail_df.empty:
    baselines = {}
    for pos in ['DEF', 'MID', 'RUC', 'FWD']:
        used = len(df[df['full_name'].isin(taken_names) & df['positions'].str.contains(pos)])
        slots_left = max(1, (reqs[pos] * num_teams) - used)
        pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('
