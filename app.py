import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Supercoach War Room Ultra", layout="wide", initial_sidebar_state="expanded")

# --- 1. AUTOMATED DATA FETCHING (Injuries via Squiggle API) ---
@st.cache_data(ttl=3600)
def fetch_injuries():
    try:
        response = requests.get("https://api.squiggle.com.au/?q=players", timeout=5)
        data = response.json()['players']
        injury_map = {}
        for p in data:
            if p['injury'] and p['injury'] != 'None':
                note = str(p['injury']).lower()
                name = f"{p['first_name']} {p['surname']}".strip()
                # Categorize and set scoring penalty
                if any(x in note for x in ['test', '1 wk', '2 wk']): status, penalty = "🟢 Short", 0.95
                elif any(x in note for x in ['3 wk', '4 wk', '5 wk', '6 wk']): status, penalty = "🟡 Medium", 0.70
                else: status, penalty = "🔴 Long", 0.30
                injury_map[name] = {"status": status, "note": p['injury'], "penalty": penalty}
        return injury_map
    except: return {}

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        cols = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        # Base quality score
        df['SuperScore'] = (df['Avg'] * 0.6 + df['Last3_Avg'] * 0.4).round(1)
        return df
    except: return pd.DataFrame()

# Initialize Engine
df = load_data()
injury_lookup = fetch_injuries()

if not df.empty:
    if 'draft_history' not in st.session_state: st.session_state.draft_history = []
    if 'my_team_names' not in st.session_state: st.session_state.my_team_names = []

    # --- SIDEBAR: CONTROLS & SETTINGS ---
    with st.sidebar:
        st.title("⚙️ Draft Settings")
        num_teams = st.number_input("Total Teams", 10)
        my_pos = st.number_input("Your Slot", 5)
        st.divider()
        reqs = {'DEF': st.number_input("DEF", 4), 'MID': st.number_input("MID", 6),
                'RUC': st.number_input("RUC", 1), 'FWD': st.number_input("FWD", 4)}
        
        st.divider()
        st.header("📢 Entry")
        drafted_names = [d['player'] for d in st.session_state.draft_history]
        avail_list = sorted(df[~df['full_name'].isin(drafted_names)]['full_name'].unique())
        selected = st.selectbox("Select Player:", [""] + avail_list)
        
        if st.button("CONFIRM PICK", type="primary"):
            if selected:
                curr_pick = len(st.session_state.draft_history) + 1
                rnd = ((curr_pick - 1) // num_teams) + 1
                # Snake Draft Logic
                t_idx = (curr_pick - 1) % num_teams + 1 if rnd % 2 != 0 else num_teams - ((curr_pick - 1) % num_teams)
                
                if t_idx == my_pos:
                    p_pos = df[df['full_name'] == selected].iloc[0]['positions'].split('/')[0]
                    my_df = df[df['full_name'].isin(st.session_state.my_team_names)]
                    if len(my_df[my_df['positions'].str.contains(p_pos)]) >= (reqs[p_pos] + 2):
                        st.error(f"❌ {p_pos} Position Full!")
                    else:
                        st.session_state.draft_history.append({'pick': curr_pick, 'team': t_idx, 'player': selected})
                        st.session_state.my_team_names.append(selected)
                        st.rerun()
                else:
                    st.session_state.draft_history.append({'pick': curr_pick, 'team': t_idx, 'player': selected})
                    st.rerun()

        if st.button("Undo Last"):
            if st.session_state.draft_history:
                last = st.session_state.draft_history.pop()
                if last['player'] in st.session_state.my_team_names: st.session_state.my_team_names.remove(last['player'])
                st.rerun()

    # --- DYNAMIC CALCULATIONS ---
    avail_df = df[~df['full_name'].isin(drafted_names)].copy()
    
    # Injury Penalties
    def get_adj(row):
        inj = injury_lookup.get(row['full_name'])
        return round(row['SuperScore'] * inj['penalty'], 1) if inj else row['SuperScore']
    avail_df['Adj_Score'] = avail_df.apply(get_adj, axis=1)

    # Scarcity Baselines (Total League Demand)
    used_supply = {p: len(df[df['full_name'].isin(drafted_names) & df['positions'].str.contains(p)]) for p in reqs}
    baselines = {}
    for pos in reqs:
        slots_left = max(1, (reqs[pos] * num_teams) - used_supply[pos])
        pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Adj_Score', ascending=False)
        idx = slots_left - 1
        baselines[pos] = pool.iloc[idx]['Adj_Score'] if idx < len(pool) else pool.iloc[-1]['Adj_Score']
    
    avail_df['VORP'] = avail_df.apply(lambda x: round(x['Adj_Score'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
    avail_df['Health'] = avail_df['full_name'].apply(lambda x: injury_lookup.get(x, {}).get('status', '✅ Fit'))

    # --- TABS ---
    t1, t2, t3, t4, t5 = st.tabs(["🎯 Board", "📊 Rankings", "📜 Log", "🏢 Clubs", "👥 League Rosters"])

    with t1:
        # Determine Turn
        curr_p = len(st.session_state.draft_history) + 1
        rnd = ((curr_p - 1) // num_teams) + 1
        t_idx = (curr_p - 1) % num_teams + 1 if rnd % 2 != 0 else num_teams - ((curr_p - 1) % num_teams)
        
        if t_idx == my_pos:
            st.success("### 🚨 YOUR TURN! RECOMMENDED:")
            recs = avail_df.sort_values('VORP', ascending=False).head(3)
            cols = st.columns(3)
            for i, (idx, p) in enumerate(recs.iterrows()):
                cols[i].metric(p['full_name'], f"VORP +{p['VORP']}", p['positions'])
            st.divider()

        st.subheader("Big Board")
        top_names = avail_df.sort_values('VORP', ascending=False).head(3)['full_name'].tolist()
        def highlight_picks(s):
            if t_idx == my_pos and s.full_name in top_names: return ['background-color: #1b5e20'] * len(s)
            return [''] * len(s)
        
        st.dataframe(avail_df[['full_name', 'positions', 'VORP', 'Health', 'Adj_Score']]
                     .sort_values('VORP', ascending=False).head(40).style.apply(highlight_picks, axis=1), 
                     use_container_width=True, hide_index=True)

    with t2:
        st.title("League Leaderboard")
        rankings = []
        for t in range(1, num_teams + 1):
            team_p = [d['player'] for d in st.session_state.draft_history if d['team'] == t]
            team_df = df[df['full_name'].isin(team_p)]
            rankings.append({'Team': f"Team {t}", 'Power': round(team_df['SuperScore'].sum(), 1), 'Count': len(team_p)})
        st.table(pd.DataFrame(rankings).sort_values('Power', ascending=False))
        

    with t3:
        st.title("Pick History")
        st.write(pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False))

    with t4:
        st.title("Club Depth")
        club = st.selectbox("Select Club", sorted(df['team'].unique()))
        club_p = df[df['team'] == club]
        cols = st.columns(4)
        for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
            with cols[i]:
                st.write(f"**{pos}**")
                for _, p in club_p[club_p['positions'].str.contains(pos)].iterrows():
                    status = "~~" if p['full_name'] in drafted_names else ""
                    st.write(f"{status}{p['full_name']} ({int(p['Avg'])}){status}")

    with t5:
        st.title("League-Wide Rosters")
        view_team = st.radio("Inspect Team:", [f"Team {i}" for i in range(1, num_teams+1)], horizontal=True)
        tid = int(view_team.split(" ")[1])
        t_players = df[df['full_name'].isin([d['player'] for d in st.session_state.draft_history if d['team'] == tid])]
        cols = st.columns(4)
        for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
            with cols[i]:
                st.subheader(pos)
                p_list = t_players[t_players['positions'].str.contains(pos)]
                for idx, p in enumerate(p_list.itertuples()):
                    label = f"**{p.full_name}** ({p.Avg})"
                    if idx < reqs[pos]: st.success(label)
                    else: st.info(f"🔄 {p.full_name}")

else:
    st.error("Upload 'supercoach_data.csv' to begin.")
