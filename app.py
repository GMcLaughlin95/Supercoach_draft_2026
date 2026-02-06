import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. PERSISTENCE & DATA ---
SAVE_FILE = "draft_state.json"

def save_state():
    """Saves current progress to a local JSON file."""
    with open(SAVE_FILE, "w") as f:
        json.dump({
            "draft_history": st.session_state.draft_history, 
            "my_team": st.session_state.my_team,
            "team_names": st.session_state.team_names
        }, f)

def load_state_logic():
    """Logic to pull data from file into session state."""
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.draft_history = state.get("draft_history", [])
            st.session_state.my_team = state.get("my_team", [])
            st.session_state.team_names = state.get("team_names", {})

def reset_draft():
    st.session_state.draft_history = []
    st.session_state.my_team = []
    st.session_state.team_names = {}
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    st.rerun()

# --- INITIALIZE & AUTO-LOAD ---
if 'draft_history' not in st.session_state:
    # This block runs only once per session start
    load_state_logic()
    # If after loading it's still empty, initialize properly
    if 'draft_history' not in st.session_state: st.session_state.draft_history = []
    if 'my_team' not in st.session_state: st.session_state.my_team = []
    if 'team_names' not in st.session_state: st.session_state.team_names = {}

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
            if new_name != existing_name:
                st.session_state.team_names[key] = new_name
                save_state() # Auto-save name changes

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
    if st.button("🚨 RESET DRAFT", use_container_width=True): reset_draft()

# --- 4. TOP ACTION AREA ---
curr_p_num = len(st.session_state.draft_history) + 1
active_team_id = get_current_turn(curr_p_num, num_teams)
active_name = get_team_name(active_team_id)

total_required_per_team = sum(user_inputs.values()) + (len(user_inputs) * 2)
is_draft_complete = len(st.session_state.draft_history) >= (num_teams * total_required_per_team)

if is_draft_complete:
    st.success("🎊 DRAFT COMPLETE! Final rosters are locked and saved.")
else:
    st.subheader(f"⏱️ Now Picking: {active_name}")
    act_col1, act_col2 = st.columns([1, 2])
    
    with act_col1:
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
            save_state() # AUTO-SAVE after simulation
            st.rerun()

    with act_col2:
        taken_names = [d['player'] for d in st.session_state.draft_history]
        avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
        r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
        selected = r_col1.selectbox("Select Player:", [""] + avail_list, label_visibility="collapsed")
        
        assigned_pos, can_confirm = None, False
        if selected:
            player_row = df[df['full_name'] == selected].iloc[0]
            possible_pos = player_row['positions'].split('/')
            assigned_pos = r_col2.radio("Pos:", possible_pos, horizontal=True, label_visibility="collapsed")
            if check_roster_limit(assigned_pos, active_team_id, user_inputs, st.session_state.draft_history):
                can_confirm = True
        
        if r_col3.button("CONFIRM", type="primary", disabled=not can_confirm, use_container_width=True):
            st.session_state.draft_history.append({"pick": curr_p_num, "team": active_team_id, "player": selected, "assigned_pos": assigned_pos})
            save_state() # AUTO-SAVE after manual pick
            st.rerun()

    # Recommendations
    if not df.empty:
        avail_df = df[~df['full_name'].isin(taken_names)].copy()
        active_picks = [d for d in st.session_state.draft_history if d['team'] == active_team_id]
        counts = {pos: sum(1 for p in active_picks if p['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
        costs = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
        for pos in costs:
            pool = avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
            if len(pool) > (num_teams + 2): costs[pos] = pool.iloc[0]['Power_Rating'] - pool.iloc[num_teams+2]['Power_Rating']
        
        avail_df['Optimizer_Score'] = avail_df.apply(lambda row: max([row['Power_Rating'] + (costs.get(p, 0) * 0.4) + (5.0 if counts[p] < user_inputs[p] else -25.0) for p in row['positions'].split('/') if check_roster_limit(p, active_team_id, user_inputs, st.session_state.draft_history)] + [-999]), axis=1)
        top_3 = avail_df[avail_df['Optimizer_Score'] > -500].sort_values('Optimizer_Score', ascending=False).head(3)
        rec_text = " / ".join([f"**{i+1}. {r['full_name']}** ({r['positions']})" for i, r in top_3.iterrows()])
        st.markdown(f"<p style='font-size: 0.85rem; color: #666;'>💡 Recommended: {rec_text}</p>", unsafe_allow_html=True)

# --- 5. TABS ---
tab_list = ["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis"]
if is_draft_complete: tab_list.append("🏆 Final Teams")
tabs = st.tabs(tab_list)

# (Tabs logic remains identical to previous stable version to preserve features)
with tabs[0]:
    search_q = st.text_input("🔍 Filter Board:", "")
    display_df = avail_df.copy()
    if search_q: display_df = display_df[display_df['full_name'].str.contains(search_q, case=False)]
    if not display_df.empty:
        display_df = display_df.sort_values('Optimizer_Score', ascending=False)
        display_df['Score'] = display_df['Optimizer_Score'].apply(lambda x: "FULL" if x <= -500 else round(x, 1))
        st.dataframe(display_df[['full_name', 'positions', 'Score', 'Avg', 'Risk_Profile', 'gamesPlayed']].head(200), use_container_width=True, hide_index=True)
    st.divider()
    c_cols = st.columns(4)
    for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
        rem = user_inputs[pos] - counts[pos]
        c_cols[i].metric(pos, f"{counts[pos]}/{user_inputs[pos]}", delta=f"-{rem}" if rem > 0 else "FULL", delta_color="inverse" if rem > 0 else "normal")

with tabs[1]:
    my_picks = [d for d in st.session_state.draft_history if d['team'] == my_slot]
    if my_picks:
        st.subheader(f"🏟️ {get_team_name(my_slot)} Infographic")
        info_cols = st.columns(5)
        on_field, bench, tracking = {p: [] for p in ['DEF', 'MID', 'RUC', 'FWD']}, [], {p: 0 for p in ['DEF', 'MID', 'RUC', 'FWD']}
        for p in my_picks:
            if tracking[p['assigned_pos']] < user_inputs[p['assigned_pos']]:
                on_field[p['assigned_pos']].append(p['player'])
                tracking[p['assigned_pos']] += 1
            else: bench.append(f"{p['player']} ({p['assigned_pos']})")
        for i, cat in enumerate(['DEF', 'MID', 'RUC', 'FWD', 'Bench']):
            with info_cols[i]:
                st.write(f"**{cat}**")
                for name in (on_field[cat] if cat != 'Bench' else bench): st.info(name)
    else: st.info("No players drafted yet.")

with tabs[2]:
    if st.session_state.draft_history:
        log_df = pd.DataFrame(st.session_state.draft_history).copy()
        log_df['team_name'] = log_df['team'].apply(get_team_name)
        st.dataframe(log_df[['pick', 'team_name', 'player', 'assigned_pos']].sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("League Analysis")
    all_teams_data = []
    for i in range(1, num_teams + 1):
        t_picks = [d for d in st.session_state.draft_history if d['team'] == i]
        t_df = df[df['full_name'].isin([p['player'] for p in t_picks])]
        row = {"Team": get_team_name(i), "Total": t_df['Avg'].sum()}
        for pos in ['DEF', 'MID', 'RUC', 'FWD']:
            row[pos] = df[df['full_name'].isin([p['player'] for p in t_picks if p['assigned_pos'] == pos])]['Avg'].sum()
        all_teams_data.append(row)
    if all_teams_data:
        stats_df = pd.DataFrame(all_teams_data)
        st.bar_chart(stats_df.set_index("Team")['Total'])
        st.dataframe(stats_df.set_index("Team"), use_container_width=True)

if is_draft_complete:
    with tabs[4]:
        st.header("🏆 Final League Rosters")
        for i in range(1, num_teams + 1):
            with st.expander(f"📍 {get_team_name(i)}"):
                t_picks = [d for d in st.session_state.draft_history if d['team'] == i]
                st.table(pd.DataFrame(t_picks)[['player', 'assigned_pos', 'pick']])
