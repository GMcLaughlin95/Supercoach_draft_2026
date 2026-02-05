import streamlit as st
import pandas as pd
import requests
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide")

# --- 1. DATA & INJURY ENGINE ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('.', '')
        # Handle naming
        if 'first_name' in df.columns and 'last_name' in df.columns:
            df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
        else:
            name_col = next((c for c in df.columns if c.lower() in ['player', 'name', 'full_name']), None)
            df['full_name'] = df[name_col] if name_col else "Unknown"
        
        df['Avg'] = pd.to_numeric(df['avg'], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_injuries():
    try:
        # Fetching real-time data from Squiggle API
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5).json()['players']
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r if p.get('injury')}
    except: return {}

df, injuries = load_data(), get_live_injuries()

# --- 2. PRE-DRAFT SETTINGS (SIDEBAR) ---
with st.sidebar:
    st.title("⚙️ Pre-Draft Settings")
    
    with st.expander("League Configuration", expanded=True):
        n_teams = st.number_input(label="Total Teams", value=10, min_value=1)
        m_slot = st.number_input(label="Your Draft Position", value=5, min_value=1, max_value=n_teams)
    
    with st.expander("Roster Requirements", expanded=True):
        col1, col2 = st.columns(2)
        r_def = col1.number_input(label="DEF", value=6, min_value=1)
        r_mid = col2.number_input(label="MID", value=8, min_value=1)
        r_ruc = col1.number_input(label="RUC", value=2, min_value=1)
        r_fwd = col2.number_input(label="FWD", value=6, min_value=1)
        
        st.write("**Bench Settings**")
        st.caption("Max 2 per position as per your rules")
        b_def = st.slider("Bench DEF", 0, 2, 1)
        b_mid = st.slider("Bench MID", 0, 2, 1)
        b_ruc = st.slider("Bench RUC", 0, 2, 0)
        b_fwd = st.slider("Bench FWD", 0, 2, 1)
        
        # Totals for VORP calculation
        reqs = {
            "DEF": r_def + b_def,
            "MID": r_mid + b_mid,
            "RUC": r_ruc + b_ruc,
            "FWD": r_fwd + b_fwd
        }

    if st.button("🚨 RESET DRAFT", use_container_width=True):
        st.session_state.draft_history = []
        st.session_state.my_team = []
        st.rerun()

# --- 3. DRAFT LOGIC ---
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

taken = [d['player'] for d in st.session_state.draft_history]

# Apply Injuries to Main DF
if not df.empty:
    df['Injury_Status'] = df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))
    
    # Calculate VORP based on NEW Roster Requirements
    avail_df = df[~df['full_name'].isin(taken)].copy()
    for pos in ["DEF", "MID", "RUC", "FWD"]:
        # Find the 'nth' player likely to be taken based on requirements
        baseline_idx = (reqs[pos] * n_teams) - len(df[df['full_name'].isin(taken) & df['positions'].str.contains(pos)])
        pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Avg', ascending=False)
        
        if not pool.empty:
            idx = min(len(pool)-1, max(0, baseline_idx))
            baseline_val = pool.iloc[idx]['Avg']
            avail_df.loc[avail_df['positions'].str.contains(pos), 'VORP'] = avail_df['Avg'] - baseline_val

# --- 4. TABS & INFOGRAPHIC ---
t1, t2 = st.tabs(["🎯 Draft Board", "📋 My Visual Roster"])

with t1:
    st.subheader("Available Players (Sorted by Value)")
    # Show Health status prominently
    st.dataframe(
        avail_df[['full_name', 'positions', 'Avg', 'VORP', 'Injury_Status']].sort_values('VORP', ascending=False),
        use_container_width=True,
        hide_index=True
    )

with t2:
    st.header("🛡️ Team Infographic")
    my_df = df[df['full_name'].isin(st.session_state.my_team)]
    
    if not my_df.empty:
        cols = st.columns(4)
        for i, pos in enumerate(["DEF", "MID", "RUC", "FWD"]):
            with cols[i]:
                st.markdown(f"### {pos}")
                # Separate Starters from Bench visually
                starters = my_df[my_df['positions'].str.contains(pos)].head(reqs[pos] - [b_def, b_mid, b_ruc, b_fwd][i])
                bench = my_df[my_df['positions'].str.contains(pos)].iloc[len(starters):]
                
                for p in starters.itertuples():
                    st.success(f"**{p.full_name}** \n{p.Avg} | {p.Injury_Status}")
                for p in bench.itertuples():
                    st.info(f"**BN: {p.full_name}** \n{p.Avg}")
    else:
        st.info("Draft players to see your lineup.")

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



