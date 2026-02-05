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
        
        # Identity Logic
        f_col, l_col = low_cols.get('first_name'), low_cols.get('last_name')
        if f_col and l_col:
            df['full_name'] = (df[f_col].astype(str) + ' ' + df[l_col].astype(str)).str.strip()
        else:
            name_col = low_cols.get('player') or low_cols.get('name') or low_cols.get('full_name')
            df['full_name'] = df[name_col] if name_col else "Unknown"

        # Stats & Power Rating
        for met in ['avg', 'last3_avg']:
            orig = low_cols.get(met)
            df[met.capitalize()] = pd.to_numeric(df[orig], errors='coerce').fillna(0) if orig else 0
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_avg'] * 0.4).round(1)

        # Bye Rounds
        bye_map = {'Adelaide': 14, 'Brisbane': 12, 'Carlton': 14, 'Collingwood': 13, 'Essendon': 13, 'Fremantle': 12, 'Geelong': 14, 'Gold Coast': 12, 'GWS': 13, 'Hawthorn': 15, 'Melbourne': 14, 'North Melbourne': 15, 'Port Adelaide': 12, 'Richmond': 15, 'St Kilda': 12, 'Sydney': 13, 'West Coast': 14, 'Western Bulldogs': 15}
        t_col = low_cols.get('team') or low_cols.get('club')
        df['Bye'] = df[t_col].map(bye_map).fillna(0).astype(int) if t_col else 0
        
        # Placeholders
        df['VORP'] = 0.0
        df['Health'] = "✅ Fit"
        return df
    except: return pd.DataFrame()

# --- 2. STATE ---
SAVE_FILE = "draft_state.json"
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"history": st.session_state.draft_history, "mine": st.session_state.my_team}, f)

df = load_and_prep_data()

def get_current_turn(curr_pick, total_teams):
    rnd = ((curr_pick - 1) // total_teams) + 1
    return (curr_pick - 1) % total_teams + 1 if rnd % 2 != 0 else total_teams - ((curr_pick - 1) % total_teams)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ War Room")
    n_teams = st.number_input(label="Total Teams", value=10, min_value=1)
    m_slot = st.number_input(label="Your Slot", value=5, min_value=1, max_value=n_teams)
    
    if st.button("🤖 Simulate To My Turn", use_container_width=True):
        while True:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, n_teams)
            if turn == m_slot: break
            taken = [d['player'] for d in st.session_state.draft_history]
            avail = df[~df['full_name'].isin(taken)].sort_values('Power_Rating', ascending=False)
            if avail.empty: break
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": avail.iloc[0]['full_name']})
        save_state(); st.rerun()

    if st.button("🚨 RESET ALL", type="secondary"):
        if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
        st.session_state.draft_history, st.session_state.my_team = [], []
        st.rerun()

    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox(label="Next Pick:", options=[""] + avail_list)
    if st.button("CONFIRM PICK", type="primary", use_container_width=True):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            turn = get_current_turn(p_num, n_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == m_slot: st.session_state.my_team.append(selected)
            save_state(); st.rerun()

# --- 4. MAIN UI ---
if not df.empty:
    # Recalculate VORP globally for Draft Analysis
    # We use a static baseline of the 100th-150th best players to judge value
    baselines = {'DEF': 85, 'MID': 105, 'RUC': 90, 'FWD': 85}
    df['VORP'] = df.apply(lambda x: round(x['Power_Rating'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)

    t1, t2, t3, t4 = st.tabs(["🎯 Board", "📋 My Team", "📈 Draft Analysis", "🏢 Rosters"])

    with t1:
        st.subheader("Big Board")
        avail_df = df[~df['full_name'].isin(taken_names)].sort_values('VORP', ascending=False)
        st.dataframe(avail_df[['full_name', 'positions', 'VORP', 'Power_Rating', 'Bye']].head(50), use_container_width=True, hide_index=True)

    with t2:
        st.header("🛡️ My Squad Infographic")
        
        # Filter only your players from the master dataframe
        my_df = df[df['full_name'].isin(st.session_state.my_team)]
        
        if not my_df.empty:
            # Create 4 columns for the 4 positional groups
            col1, col2, col3, col4 = st.columns(4)
            
            # Mapping columns to positions
            positions_to_show = {"DEF": col1, "MID": col2, "RUC": col3, "FWD": col4}
            
            for pos, col in positions_to_show.items():
                with col:
                    # Filter players belonging to this category
                    p_list = my_df[my_df['positions'].str.contains(pos)]
                    count = len(p_list)
                    
                    # Header
                    st.markdown(f"### {pos} ({count})")
                    
                    # Render each player as a "Card"
                    for p in p_list.itertuples():
                        with st.container(border=True):
                            st.markdown(f"**{p.full_name}**")
                            st.caption(f"Avg: {p.Avg} | Bye: {p.Bye}")
        else:
            st.info("Your roster is currently empty. Start drafting!")

    with t3:
        st.subheader("📊 League Power Rankings")
        if st.session_state.draft_history:
            history_df = pd.DataFrame(st.session_state.draft_history)
            # Merge with master DF to get VORP
            analysis = history_df.merge(df[['full_name', 'VORP']], left_on='player', right_on='full_name')
            rankings = analysis.groupby('team')['VORP'].sum().reset_index()
            
            # Grading Logic
            avg_vorp = rankings['VORP'].mean()
            def get_grade(v):
                if v > avg_vorp + 20: return "A+"
                if v > avg_vorp + 10: return "A"
                if v > avg_vorp: return "B"
                if v > avg_vorp - 10: return "C"
                return "D"
            
            rankings['Grade'] = rankings['VORP'].apply(get_grade)
            rankings = rankings.sort_values('VORP', ascending=False)
            
            cols = st.columns(len(rankings))
            for idx, row in enumerate(rankings.itertuples()):
                with cols[idx]:
                    st.metric(f"Team {row.team}", f"{row.Grade}", f"{round(row.VORP, 1)} pts")
            
            st.divider()
            st.dataframe(rankings, use_container_width=True, hide_index=True)
        else:
            st.info("Draft some players to see league analysis.")

    with t4:
        st.subheader("Opponent Scouting")
        opponent_slots = [i for i in range(1, n_teams + 1) if i != m_slot]
        view_team = st.selectbox("Select Team:", opponent_slots)
        t_p = [d['player'] for d in st.session_state.draft_history if d['team'] == view_team]
        t_df = df[df['full_name'].isin(t_p)]
        
        c = st.columns(4)
        for i, pt in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
            with c[i]:
                st.write(f"**{pt}**")
                for p in t_df[t_df['positions'].str.contains(pt)].itertuples():
                    st.info(f"{p.full_name}")


