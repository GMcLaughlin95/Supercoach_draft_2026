import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. PERSISTENCE & DATA ---
SAVE_FILE = "draft_state.json"

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({
            "draft_history": st.session_state.draft_history, 
            "my_team": st.session_state.my_team,
            "team_names": st.session_state.team_names
        }, f)

def load_state():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.draft_history = state.get("draft_history", [])
            st.session_state.my_team = state.get("my_team", [])
            st.session_state.team_names = state.get("team_names", {})
        st.rerun()

def reset_draft():
    st.session_state.draft_history = []
    st.session_state.my_team = []
    st.session_state.team_names = {}
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
        
        cols_to_fix = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
        
        def calculate_custom_power(row):
            score = (row['Avg'] * 0.9) + (row['Last3_Avg'] * 0.05)
            if 'DEF' in row['positions']: score += (row['KickInAvg'] * 0.2)
            return round(score, 1)

        def get_risk_profile(games):
            if games >= 18: return "🟢 Low"
            if games >= 12: return "🟡 Mod"
            return "🔴 High"

        df['Power_Rating'] = df.apply(calculate_custom_power, axis=1)
        df['Risk_Profile'] = df['gamesPlayed'].apply(get_risk_profile)
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []
if 'team_names' not in st.session_state: st.session_state.team_names = {}

df = load_data()

# --- 2. HELPERS ---
def get_current_turn(curr_pick, total_teams):
    if total_teams <= 0: return 1
    rnd = ((curr_pick - 1) // total_teams) + 1
    if rnd % 2 != 0: return (curr_pick - 1) % total_teams + 1
    return total_teams - ((curr_pick - 1) % total_teams)

def get_team_name(tid):
    return st.session_state.team_names.get(str(tid), f"Team {tid}")

def check_roster_limit(chosen_pos, team_id, user_inputs, history_list):
    team_picks = [d for d in history_list if d['team'] == team_id]
    current_count = sum(1 for p in team_picks if p.get('assigned_pos') == chosen_pos)
    # Limit is core requirement + 2 extra bench slots per position
    return current_count < (user_inputs.get(chosen_pos, 0) + 2)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ Command Center")
    num_teams = st.number_input("Total Teams", value=10, min_value=1)
    my_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=num_teams)
    
    with st.expander("🏷️ Name Your Teams"):
        for i in range(1, num_teams + 1):
            key = str(i)
            existing_name = st.session_state.team_names.get(key, f"Team {i}")
            new_name = st.text_input(f"Slot {i}", value=existing_name, key=f"tn_{i}")
            st.session_state.team_names[key] = new_name

    st.divider()
    st.write("**Target Roster (On-Field)**")
    c_req1, c_req2 = st.columns(2)
    user_inputs = {
        'DEF': c_req1.number_input("DEF", value=6, min_value=0),
        'MID': c_req2.number_input("MID", value=8, min_value=0),
        'RUC': c_req1.number_input("RUC", value=2, min_value=0),
        'FWD': c_req2.number_input("FWD", value=6, min_value=0)
    }

    st.divider()
    curr_p_num = len(st.session_state.draft_history) + 1
    active_team_id = get_current_turn(curr_p_num, num_teams)
    active_name = get_team_name(active_team_id)
    st.subheader(f"Turn: {active_name}")
    
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
    
    assigned_pos, can_confirm = None, False
    if selected:
        player_row = df[df['full_name'] == selected].iloc[0]
        possible_pos = player_row['positions'].split('/')
        if len(possible_pos) > 1: assigned_pos = st.radio(f"Assign to:", possible_pos, horizontal=True)
        else: assigned_pos = possible_pos[0]
        if check_roster_limit(assigned_pos, active_team_id, user_inputs, st.session_state.draft_history):
            can_confirm = True

    if st.button("CONFIRM PICK", type="primary", use_container_width=True, disabled=not can_confirm):
        st.session_state.draft_history.append({"pick": curr_p_num, "team": active_team_id, "player": selected, "assigned_pos": assigned_pos})
        save_state(); st.rerun()

# --- 4. OPTIMIZER LOGIC ---
if not df.empty:
    avail_df = df[~df['full_name'].isin(taken_names)].copy()
    active_picks = [d for d in st.session_state.draft_history if d['team'] == active_team_id]
    counts = {pos: sum(1 for p in active_picks if p['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
    
    lookahead = num_teams + 2
    costs = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
    for pos in costs:
        pool = avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
        if len(pool) > lookahead: costs[pos] = pool.iloc[0]['Power_Rating'] - pool.iloc[lookahead]['Power_Rating']

    def calculate_display_score(row):
        pos_list = row['positions'].split('/')
        best_val = -999.0
        for p in pos_list:
            if not check_roster_limit(p, active_team_id, user_inputs, st.session_state.draft_history): continue
            v = row['Power_Rating'] + (costs.get(p, 0) * 0.4)
            if counts[p] < user_inputs[p]: v += 5.0
            else: v -= 25.0
            if v > best_val: best_val = v
        return best_val

    avail_df['Optimizer_Score'] = avail_df.apply(calculate_display_score, axis=1)
else: avail_df = pd.DataFrame()

# --- 5. TABS ---
t1, t2, t3, t4 = st.tabs(["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis"])

with t1:
    search_q = st.text_input("🔍 Search Player:", "")
    display_df = avail_df.copy()
    if search_q: display_df = display_df[display_df['full_name'].str.contains(search_q, case=False)]
    
    # Format the score to handle "Full" positions
    display_df['Score_Display'] = display_df['Optimizer_Score'].apply(lambda x: "POS FULL" if x <= -500 else round(x, 1))
    
    st.dataframe(
        display_df[['full_name', 'positions', 'Score_Display', 'Avg', 'Risk_Profile', 'gamesPlayed']].sort_values('Optimizer_Score', ascending=False).head(400), 
        use_container_width=True, hide_index=True, height=600
    )
    
    # NEW: Remaining Position Counter
    st.divider()
    st.subheader(f"Roster Status: {active_name}")
    cols = st.columns(4)
    for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
        rem = user_inputs[pos] - counts[pos]
        label = f"**{pos}:** {counts[pos]}/{user_inputs[pos]}"
        if rem > 0: cols[i].warning(f"{label} (Need {rem})")
        else: cols[i].success(f"{label} (Bench Mode)")

with t2:
    my_picks = [d for d in st.session_state.draft_history if d['team'] == my_slot]
    if my_picks:
        total_team_avg = round(df[df['full_name'].isin([p['player'] for p in my_picks])]['Avg'].sum(), 1)
        st.subheader(f"{get_team_name(my_slot)} | Projected Score: {total_team_avg}")
        
        # NEW: Team Infographic Sorted by Category
        st.markdown("### 🏟️ Team Infographic")
        info_cols = st.columns(5)
        categories = ['DEF', 'MID', 'RUC', 'FWD', 'Bench']
        
        # Logic to separate on-field and bench
        on_field = {pos: [] for pos in ['DEF', 'MID', 'RUC', 'FWD']}
        bench_list = []
        
        # Track counts to determine who is bench
        tracking_counts = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
        for p in my_picks:
            pos = p['assigned_pos']
            if tracking_counts[pos] < user_inputs[pos]:
                on_field[pos].append(p['player'])
                tracking_counts[pos] += 1
            else:
                bench_list.append(f"{p['player']} ({pos})")
        
        for i, cat in enumerate(categories):
            with info_cols[i]:
                st.write(f"**{cat}**")
                players = on_field[cat] if cat != 'Bench' else bench_list
                if players:
                    for name in players: st.info(name)
                else: st.caption("Empty")
    else: st.info("Draft players to see your squad.")

with t3:
    if st.session_state.draft_history:
        log_df = pd.DataFrame(st.session_state.draft_history).copy()
        log_df['team_name'] = log_df['team'].apply(get_team_name)
        st.dataframe(log_df[['pick', 'team_name', 'player', 'assigned_pos']].sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

with t4:
    team_stats = [{"Team": get_team_name(i), "Total Avg": df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == i])]['Avg'].sum()} for i in range(1, num_teams+1)]
    if team_stats:
        st.subheader("League Standings")
        st.bar_chart(pd.DataFrame(team_stats).set_index("Team"))
