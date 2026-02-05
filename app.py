import streamlit as st
import pandas as pd
import requests
import json
import os
import time

# --- CONFIG & THEME ---
st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. DATA ENGINE (Robust Loading) ---
@st.cache_data
def load_data():
    try:
        # Load and clean headers
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

        # Metric Logic
        for met in ['avg', 'last3_avg']:
            orig = low_cols.get(met)
            df[met.capitalize()] = pd.to_numeric(df[orig], errors='coerce').fillna(0) if orig else 0
        
        # Bye Round Map (2026 Estimated)
        bye_map = {
            'Adelaide': 14, 'Brisbane': 12, 'Carlton': 14, 'Collingwood': 13,
            'Essendon': 13, 'Fremantle': 12, 'Geelong': 14, 'Gold Coast': 12,
            'GWS': 13, 'Hawthorn': 15, 'Melbourne': 14, 'North Melbourne': 15,
            'Port Adelaide': 12, 'Richmond': 15, 'St Kilda': 12, 'Sydney': 13,
            'West Coast': 14, 'Western Bulldogs': 15
        }
        t_col = low_cols.get('team') or low_cols.get('club')
        df['Bye'] = df[t_col].map(bye_map).fillna(0).astype(int) if t_col else 0
        
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_avg'] * 0.4).round(1)
        return df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_injuries():
    try:
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5).json()['players']
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r if p.get('injury')}
    except: return {}

# --- 2. STATE MANAGEMENT ---
SAVE_FILE = "draft_state.json"

if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"history": st.session_state.draft_history, "mine": st.session_state.my_team}, f)

def reset_draft():
    if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
    st.session_state.draft_history = []
    st.session_state.my_team = []
    st.rerun()

df, injuries = load_data(), get_injuries()

# --- 3. SIDEBAR (Fixed positional args) ---
with st.sidebar:
    st.title("🛡️ Draft Command")
    n_teams = st.number_input(label="Total Teams", value=10, min_value=1)
    m_slot = st.number_input(label="Your Slot", value=5, min_value=1, max_value=n_teams)
    
    st.divider()
    col_r1, col_r2 = st.columns(2)
    reqs = {
        'DEF': col_r1.number_input(label="DEF", value=4, min_value=0),
        'MID': col_r2.number_input(label="MID", value=6, min_value=0),
        'RUC': col_r1.number_input(label="RUC", value=1, min_value=0),
        'FWD': col_r2.number_input(label="FWD", value=4, min_value=0)
    }

    st.divider()
    if st.button("🤖 RUN SIMULATION"):
        with st.status("Simulating..."):
            st.session_state.draft_history = []
            st.session_state.my_team = []
            for i in range(n_teams * 12): # Simulate 12 rounds
                taken = [d['player'] for d in st.session_state.draft_history]
                avail = df[~df['full_name'].isin(taken)].sort_values('Power_Rating', ascending=False)
                if not avail.empty:
                    p_name = avail.iloc[0]['full_name']
                    p_num = len(st.session_state.draft_history) + 1
                    rnd = ((p_num - 1) // n_teams) + 1
                    turn = (p_num - 1) % n_teams + 1 if rnd % 2 != 0 else n_teams - ((p_num - 1) % n_teams)
                    st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": p_name})
                    if turn == m_slot: st.session_state.my_team.append(p_name)
            save_state()
            st.rerun()

    if st.button("🚨 RESET ALL", use_container_width=True): reset_draft()

    st.divider()
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_list = sorted(df[~df['full_name'].isin(taken_names)]['full_name'].tolist()) if not df.empty else []
    selected = st.selectbox(label="Record Pick:", options=[""] + avail_list)
    
    if st.button("CONFIRM PICK", type="primary", use_container_width=True):
        if selected:
            p_num = len(st.session_state.draft_history) + 1
            rnd = ((p_num - 1) // n_teams) + 1
            turn = (p_num - 1) % n_teams + 1 if rnd % 2 != 0 else n_teams - ((p_num - 1) % n_teams)
            st.session_state.draft_history.append({"pick": p_num, "team": turn, "player": selected})
            if turn == m_slot: st.session_state.my_team.append(selected)
            save_state()
            st.rerun()

# --- 4. MAIN INTERFACE ---
if not df.empty:
    # VORP Calculation Logic
    avail_df = df[~df['full_name'].isin(taken_names)].copy()
    if not avail_df.empty:
        baselines = {}
        for pos in ['DEF', 'MID', 'RUC', 'FWD']:
            u = len(df[df['full_name'].isin(taken_names) & df['positions'].str.contains(pos)])
            slots = max(1, (reqs[pos] * n_teams) - u)
            pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Power_Rating', ascending=False)
            idx = min(len(pool)-1, slots - 1)
            baselines[pos] = pool.iloc[idx]['Power_Rating'] if not pool.empty else 80
        avail_df['VORP'] = avail_df.apply(lambda x: round(x['Power_Rating'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
        avail_df['Health'] = avail_df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

    t1, t2, t3, t4, t5 = st.tabs(["🎯 Board", "📋 My Team", "📈 Log", "🏢 Rosters", "🤝 Trade Calc"])

    with t1:
        # Turn Logic
        cp = len(st.session_state.draft_history) + 1
        cr = ((cp - 1) // n_teams) + 1
        ct = (cp - 1) % n_teams + 1 if cr % 2 != 0 else n_teams - ((cp - 1) % n_teams)
        if ct == m_slot: st.success("### 🚨 YOUR TURN!")
        
        st.subheader("Big Board")
        def v_color(v):
            c = '#1b5e20' if v > 12 else '#2e7d32' if v > 6 else '#388e3c' if v > 0 else 'none'
            return f'background-color: {c}'
        
        disp = avail_df[['full_name', 'positions', 'VORP', 'Power_Rating', 'Bye', 'Health']].sort_values('VORP', ascending=False).head(40)
        st.dataframe(disp.style.applymap(v_color, subset=['VORP']), use_container_width=True, hide_index=True)

    with t2:
        my_df = df[df['full_name'].isin(st.session_state.my_team)]
        st.dataframe(my_df[['full_name', 'positions', 'Avg', 'Bye']], use_container_width=True, hide_index=True)
        if not my_df.empty:
            st.subheader("📅 Bye Round Exposure")
            st.bar_chart(my_df['Bye'].value_counts().sort_index())

    with t5:
        st.header("🤝 Trade Calculator")
        col_g, col_r = st.columns(2)
        with col_g:
            out_p = st.multiselect("Giving Away:", st.session_state.my_team)
            out_v = df[df['full_name'].isin(out_p)]['Power_Rating'].sum()
            st.metric("Value Out", round(out_v, 1))
        with col_r:
            all_others = [d['player'] for d in st.session_state.draft_history if d['player'] not in st.session_state.my_team]
            in_p = st.multiselect("Receiving:", all_others)
            in_v = df[df['full_name'].isin(in_p)]['Power_Rating'].sum()
            st.metric("Value In", round(in_v, 1))
        st.subheader(f"Trade Balance: {round(in_v - out_v, 1)}")

else:
    st.error("Please ensure 'supercoach_data.csv' is uploaded.")
