import streamlit as st
import pandas as pd
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

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df.columns = [c.strip() for c in df.columns]
        if 'full_name' not in df.columns:
            df['full_name'] = (df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)).str.strip()
        
        cols_to_fix = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg', 'Tog%']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
        
        # POWER RATING: Optimized for Total Points Projection
        def calculate_custom_power(row):
            # 85% Weight on Avg to maximize total team average
            score = (row['Avg'] * 0.85) + (row['Last3_Avg'] * 0.15)
            # Volatility adjustment: Penalty for low sample size
            if 0 < row['gamesPlayed'] < 10: score -= 8.0
            return round(score, 1)

        df['Power_Rating'] = df.apply(calculate_custom_power, axis=1)
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df = load_data()

# --- 2. HELPER FUNCTIONS ---
def get_current_turn(curr_pick, total_teams):
    if total_teams <= 0: return 1
    rnd = ((curr_pick - 1) // total_teams) + 1
    if rnd % 2 != 0: return (curr_pick - 1) % total_teams + 1
    return total_teams - ((curr_pick - 1) % total_teams)

def check_roster_limit(chosen_pos, team_id, user_inputs, history_list):
    team_picks = [d for d in history_list if d['team'] == team_id]
    current_count = sum(1 for p in team_picks if p.get('assigned_pos') == chosen_pos)
    # Hard limit is set to the requirement + 2 bench spots
    return current_count < (user_inputs.get(chosen_pos, 0) + 2)

# --- 3. SIDEBAR COMMAND ---
with st.sidebar:
    st.title("🛡️ Strategy Command")
    num_teams = st.number_input("Total Teams", value=10, min_value=1)
    my_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=num_teams)
    
    st.divider()
    st.write("**Target Roster**")
    c_req1, c_req2 = st.columns(2)
    user_inputs = {
        'DEF': c_req1.number_input("DEF", value=6, min_value=0),
        'MID': c_req2.number_input("MID", value=8, min_value=0),
        'RUC': c_req1.number_input("RUC", value=2, min_value=0),
        'FWD': c_req2.number_input("FWD", value=6, min_value=0)
    }

    # STRATEGY ADVISOR: SCARCITY FOCUSED
    st.divider()
    st.subheader("💡 Logic: Maximize Avg")
    curr_pick_num = len(st.session_state.draft_history) + 1
    active_team = get_current_turn(curr_pick_num, num_teams)
    active_picks = [d for d in st.session_state.draft_history if d['team'] == active_team]
    counts = {pos: sum(1 for p in active_picks if p['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
    
    tips = []
    for pos, req in user_inputs.items():
        if counts[pos] < req:
            needed = req - counts[pos]
            tips.append(f"Fill {pos}: {needed} left")
    
    if tips: st.warning("\n".join(tips))
    else: st.success("✅ Main Roster Full - Optimization Mode")
    
    st.divider()
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("💾 Save"): save_state()
    if col_s2.button("🔄 Recover"): load_state()
    if st.button("🚨 RESET DRAFT", use_container_width=True): reset_draft()
    
    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox("Record Pick:", [""] + avail_list)
    
    assigned_pos, can_confirm = None, False
    if selected:
        player_row = df[df['full_name'] == selected].iloc[0]
        possible_pos = player_row['positions'].split('/')
        if len(possible_pos) > 1: assigned_pos = st.radio(f"Assign {selected} to:", possible_pos, horizontal=True)
        else: assigned_pos = possible_pos[0]

        if check_roster_limit(assigned_pos, active_team, user_inputs, st.session_state.draft_history):
            can_confirm = True
        else: st.error(f"❌ Position {assigned_pos} is full.")

    if st.button("CONFIRM PICK", type="primary", use_container_width=True, disabled=not can_confirm):
        st.session_state.draft_history.append({"pick": curr_pick_num, "team": active_team, "player": selected, "assigned_pos": assigned_pos})
        save_state(); st.rerun()

# --- 4. THE RANKING RE-WORK: SCARCITY VORP ---
if not df.empty:
    avail_df = df[~df['full_name'].isin(taken_names)].copy()
    
    # We define the baseline as the 'n-th' player available, where n is roughly 
    # the number of teams remaining to pick that position.
    baselines = {}
    for pos in ['DEF', 'MID', 'RUC', 'FWD']:
        pool = avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
        # Baseline is 1.5x the number of teams (simulating the next round's dropoff)
        depth_index = min(len(pool)-1, num_teams + 5)
        baselines[pos] = pool.iloc[depth_index]['Power_Rating'] if not pool.empty else 0

    def calculate_scarcity_vorp(row):
        pos_list = row['positions'].split('/')
        best_v = -999.0
        
        for p in pos_list:
            # 1. Check if we actually NEED this position
            is_full = not check_roster_limit(p, active_team, user_inputs, st.session_state.draft_history)
            if is_full: continue
            
            # 2. Raw Value vs Baseline
            v = row['Power_Rating'] - baselines.get(p, 80)
            
            # 3. WEIGHTING: Focus on filling empty slots first to ensure "all positions filled"
            if counts[p] < user_inputs[p]:
                # Massive boost for unfilled required spots
                v += 25.0 
            else:
                # Penalty for bench/extra slots to prioritize core team average
                v -= 15.0
                
            if v > best_v: best_v = v
        return round(best_v, 1)

    avail_df['VORP'] = avail_df.apply(calculate_scarcity_vorp, axis=1)
else: avail_df = pd.DataFrame()

# --- 5. DISPLAY ---
t1, t2, t3, t4 = st.tabs(["🎯 Optimized Board", "📋 My Team", "📈 Draft Log", "📊 League Analysis"])

with t1:
    search_q = st.text_input("🔍 Search Player:", "")
    display_df = avail_df.copy()
    if search_q: display_df = display_df[display_df['full_name'].str.contains(search_q, case=False)]
    
    st.subheader(f"Strategy: Maximize Total Average (Team {active_team})")
    st.info("The VORP below reflects how much a player's Average contributes to your team relative to the scarcity of their position.")
    
    st.dataframe(
        display_df[['full_name', 'positions', 'VORP', 'Avg', 'Power_Rating']].sort_values('VORP', ascending=False).head(400), 
        use_container_width=True, hide_index=True, height=800
    )

with t2:
    my_team_display = [d for d in st.session_state.draft_history if d['team'] == my_slot]
    if my_team_display:
        st.subheader(f"My Team (Proj. Avg: {round(sum(df[df['full_name'].isin([p['player'] for p in my_team_display])]['Avg']),1)})")
        st.table(pd.DataFrame(my_team_display)[['player', 'assigned_pos', 'pick']])
    else: st.info("Draft players to see your projected average.")

with t3:
    if st.session_state.draft_history:
        st.dataframe(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

with t4:
    team_stats = []
    for i in range(1, num_teams+1):
        t_players = [d['player'] for d in st.session_state.draft_history if d['team'] == i]
        total_avg = df[df['full_name'].isin(t_players)]['Avg'].sum()
        team_stats.append({"Team": f"Team {i}", "Combined Avg": round(total_avg, 1)})
    
    if team_stats:
        st.subheader("Combined Team Averages")
        st.bar_chart(pd.DataFrame(team_stats).set_index("Team"))
