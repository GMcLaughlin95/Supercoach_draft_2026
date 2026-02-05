import streamlit as st
import pandas as pd
import requests
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. ROBUST DATA LOADING ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        # Clean columns: strip spaces, replace dots/spaces with underscores
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('.', '')
        
        # Mapping to find columns regardless of exact naming/casing
        low_cols = {c.lower(): c for c in df.columns}
        
        # Create full_name
        f_col = low_cols.get('first_name') or low_cols.get('firstname')
        l_col = low_cols.get('last_name') or low_cols.get('lastname')
        if f_col and l_col:
            df['full_name'] = (df[f_col].astype(str) + ' ' + df[l_col].astype(str)).str.strip()
        else:
            # Fallback to 'player' or 'name' if separate columns don't exist
            name_col = low_cols.get('player') or low_cols.get('name') or low_cols.get('full_name')
            df['full_name'] = df[name_col] if name_col else "Unknown Player"

        # Force Metrics to Numeric
        for met in ['avg', 'last3_avg', 'gamesplayed']:
            orig = low_cols.get(met)
            df[met.capitalize()] = pd.to_numeric(df[orig], errors='coerce').fillna(0) if orig else 0

        # Bye Round Map
        bye_map = {
            'Adelaide': 14, 'Brisbane': 12, 'Carlton': 14, 'Collingwood': 13,
            'Essendon': 13, 'Fremantle': 12, 'Geelong': 14, 'Gold Coast': 12,
            'GWS': 13, 'Hawthorn': 15, 'Melbourne': 14, 'North Melbourne': 15,
            'Port Adelaide': 12, 'Richmond': 15, 'St Kilda': 12, 'Sydney': 13,
            'West Coast': 14, 'Western Bulldogs': 15
        }
        t_col = low_cols.get('team') or low_cols.get('club')
        df['Bye'] = df[t_col].map(bye_map).fillna(0).astype(int) if t_col else 0
        
        # Power Rating Calculation
        df['Power_Rating'] = (df['Avg'] * 0.6 + df['Last3_avg'] * 0.4).round(1)
        return df
    except Exception as e:
        st.error(f"Critical Data Error: {e}")
        return pd.DataFrame()

# --- 2. STATE MANAGEMENT ---
SAVE_FILE = "draft_state.json"

def save_state():
    with open(SAVE_FILE, "w") as f:
        json.dump({"history": st.session_state.draft_history, "mine": st.session_state.my_team}, f)

def load_state():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            s = json.load(f)
            st.session_state.draft_history, st.session_state.my_team = s["history"], s["mine"]
        st.rerun()

@st.cache_data(ttl=3600)
def get_injuries():
    try:
        r = requests.get("https://api.squiggle.com.au/?q=players", timeout=5).json()['players']
        return {f"{p['first_name']} {p['surname']}": p['injury'] for p in r if p.get('injury')}
    except: return {}

# Initialize Session
if 'draft_history' not in st.session_state: st.session_state.draft_history = []
if 'my_team' not in st.session_state: st.session_state.my_team = []

df, injuries = load_data(), get_injuries()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ Command Center")
    n_teams = st.number_input("Total Teams", value=10, min_value=1)
    m_slot = st.number_input("Your Slot", value=5, min_value=1, max_value=n_teams)
    
    st.divider()
    st.write("**Requirements**")
    c1, c2 = st.columns(2)
    reqs = {'DEF': c1.number_input("DEF", 4), 'MID': c2.number_input("MID", 6),
            'RUC': c1.number_input("RUC", 1), 'FWD': c2.number_input("FWD", 4)}
    
    if st.button("🔄 Recover Progress"): load_state()
    
    st.divider()
    taken = [d['player'] for d in st.session_state.draft_history]
    if not df.empty:
        avail_list = sorted(df[~df['full_name'].isin(taken)]['full_name'].tolist())
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

# --- 4. ENGINE & UI ---
if not df.empty:
    # VORP Calculation
    avail_df = df[~df['full_name'].isin(taken)].copy()
    if not avail_df.empty:
        baselines = {}
        for pos in ['DEF', 'MID', 'RUC', 'FWD']:
            u = len(df[df['full_name'].isin(taken) & df['positions'].str.contains(pos)])
            slots = max(1, (reqs[pos] * n_teams) - u)
            pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Power_Rating', ascending=False)
            idx = min(len(pool)-1, slots - 1)
            baselines[pos] = pool.iloc[idx]['Power_Rating'] if not pool.empty else 80
        
        avail_df['VORP'] = avail_df.apply(lambda x: round(x['Power_Rating'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
        avail_df['Health'] = avail_df['full_name'].map(lambda x: injuries.get(x, "✅ Fit"))

    t1, t2, t3, t4 = st.tabs(["🎯 Board", "📋 My Team", "📈 League", "🏢 Rosters"])

    with t1:
        # Turn spotlight
        cp = len(st.session_state.draft_history) + 1
        cr = ((cp - 1) // n_teams) + 1
        ct = (cp - 1) % n_teams + 1 if cr % 2 != 0 else n_teams - ((cp - 1) % n_teams)
        
        if ct == m_slot:
            st.success("### 🚨 YOUR TURN!")
            recs = avail_df.sort_values('VORP', ascending=False).head(3)
            cols = st.columns(3)
            for i, (idx, p) in enumerate(recs.iterrows()):
                cols[i].metric(p['full_name'], f"VORP +{p['VORP']}", f"R{p['Bye']} Bye")
        
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

    with t3:
        if st.session_state.draft_history:
            st.dataframe(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False), use_container_width=True)

    with t4:
        vt = st.radio("Team:", [f"Team {i}" for i in range(1, n_teams+1)], horizontal=True)
        tid = int(vt.split(" ")[1])
        tp = df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == tid])]
        cols = st.columns(4)
        for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
            with cols[i]:
                st.write(f"**{pos}**")
                for p in tp[tp['positions'].str.contains(pos)].itertuples():
                    st.info(p.full_name)

    # DEBUG SECTION
    with st.expander("🛠️ Data Debugger (Use if columns missing)"):
        st.write("Current Columns:", df.columns.tolist())
        st.write("Data Preview:", df.head())

else:
    st.warning("Please ensure 'supercoach_data.csv' is in your repository folder.")
