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
        
        # Convert all metrics to numeric for the calculation
        cols_to_fix = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg', 'Tog%']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
        
        # ADVANCED POWER RATING CALCULATION
        def calculate_custom_power(row):
            score = (row['Avg'] * 0.5) + (row['Last3_Avg'] * 0.3)
            if 0 < row['gamesPlayed'] < 15: score -= 5.0 # Injury Risk penalty
            if 'DEF' in row['positions']: score += (row['KickInAvg'] * 0.5)
            if 'MID' in row['positions'] and row['CbaAvg'] > 50: score += 3.0
            if 0 < row['Tog%'] < 75: score += 2.0 # Efficiency boost
            return round(score, 1)

        df['Power_Rating'] = df.apply(calculate_custom_power, axis=1)
        df['VORP'] = 0.0
        df['Health'] = "✅ Fit"
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

# Initialize Session State
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df, injuries = load_data(), get_injuries()
if not df.empty:
    df['Health'] = df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

# --- 2. HELPER FUNCTIONS ---
def get_current_turn(curr_pick, total_teams):
    if total_teams <= 0: return 1
    rnd = ((curr_pick - 1) // total_teams) + 1
    if rnd % 2 != 0: return (curr_pick - 1) % total_teams + 1
    return total_teams - ((curr_pick - 1) % total_teams)

def check_roster_limit(chosen_pos, team_id, user_inputs, history_list):
    team_picks = [d for d in history_list if d['team'] == team_id]
    current_count = sum(1 for p in team_picks if p.get('assigned_pos') == chosen_pos)
    return current_count < (user_inputs.get(chosen_pos, 0) + 2)

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
    if st.button("🚨 RESET DRAFT", use_container_width=True): reset_draft()
    
    if st.button("🤖 Sim to My Turn", use_container_width=True):
        while True:
            curr_p = len(st.session_state.draft_history) + 1
            turn = get_current_turn(curr_p, num_teams)
            if turn == my_slot: break
            taken_sim = [d['player'] for d in st.session_state.draft_history]
            avail_sim = df[~df['full_name'].isin(taken_sim)].sort_values('Power_Rating', ascending=False)
            if avail_sim.empty: break
            
            ai_choice, ai_pos = None, None
            for _, row in avail_sim.iterrows():
                possible_pos = row['positions'].split('/')
                for p in possible_pos:
                    if check_roster_limit(p, turn, user_inputs, st.session_state.draft_history):
                        ai_choice, ai_pos = row['full_name'], p
                        break
                if ai_choice: break
            
            if ai_choice:
                st.session_state.draft_history.append({"pick": curr_p, "team": turn, "player": ai_choice, "assigned_pos": ai_pos})
            else: break
        save_state(); st.rerun()
    
    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    assigned_pos = None
    can_confirm = False
    
    if selected:
        curr_p = len(st.session_state.draft_history) + 1
        turn = get_current_turn(curr_p, num_teams)
        player_row = df[df['full_name'] == selected].iloc[0]
        possible_pos = player_row['positions'].split('/')
        
        if len(possible_pos) > 1:
            assigned_pos = st.radio(f"Assign {selected} to:", possible_pos, horizontal=True)
        else:
            assigned_pos = possible_pos[0]
            st.info(f"Position: {assigned_pos}")

        if check_roster_limit(assigned_pos, turn, user_inputs, st.session_state.draft_history):
            can_confirm = True
            ruc_count = sum(1 for p in st.session_state.draft_history if p['team'] == turn and p.get('assigned_pos') == 'RUC')
            if assigned_pos == 'RUC' and ruc_count == 2: st.warning("⚠️ 3rd Ruckman: Limit Reached.")
        else:
            st.error(f"❌ Team {turn} is full at {assigned_pos}")

    if st.button("CONFIRM PICK", type="primary", use_container_width=True, disabled=not can_confirm):
        p_num = len(st.session_state.draft_history) + 1
        turn = get_current_turn(p_num, num_teams)
        st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected, "assigned_pos": assigned_pos})
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
t1, t2, t3, t4 = st.tabs(["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis & Rosters"])

with t1:
    search_q = st.text_input("🔍 Search Player:", "")
    display_df = avail_df.copy()
    if search_q:
        display_df = display_df[display_df['full_name'].str.contains(search_q, case=False)]
    
    st.subheader(f"Available Players ({len(display_df)})")
    if not display_df.empty:
        cols_to_show = [c for c in ['full_name', 'positions', 'VORP', 'Power_Rating', 'Health'] if c in display_df.columns]
        st.dataframe(
            display_df[cols_to_show].sort_values('VORP', ascending=False).head(400), 
            use_container_width=True, 
            hide_index=True,
            height=800  # Increased height for better scrolling
        )

with t2:
    st.subheader("My Squad")
    my_picks = [d for d in st.session_state.draft_history if d['team'] == my_slot]
    if my_picks: st.table(pd.DataFrame(my_picks)[['player', 'assigned_pos', 'pick']])
    else: st.info("Draft players to see your team.")

with t3:
    st.subheader("📈 Draft Log")
    if st.session_state.draft_history:
        st.dataframe(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

with t4:
    st.subheader("📊 League Power Rankings")
    team_stats = [{"Team": f"Team {i}", "Power": df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == i])]['Power_Rating'].sum()} for i in range(1, num_teams+1)]
    if team_stats: st.bar_chart(pd.DataFrame(team_stats).set_index("Team"), color="#2e7d32")
    
    st.divider()
    view_t = st.radio("Inspect Team:", [f"Team {i}" for i in range(1, num_teams+1)], horizontal=True)
    tid = int(view_t.split(" ")[1])
    t_picks = [d for d in st.session_state.draft_history if d['team'] == tid]
    
    cols = st.columns(4)
    for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
        with cols[i]:
            st.write(f"**{pos}**")
            for p in [x for x in t_picks if x['assigned_pos'] == pos]: st.success(p['player'])
