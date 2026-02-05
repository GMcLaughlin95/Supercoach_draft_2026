import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Supercoach War Room Pro", layout="wide", initial_sidebar_state="expanded")

# --- 1. AUTOMATED INJURY FETCHING ---
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
                if any(x in note for x in ['test', '1 wk', '2 wk']): status, penalty = "🟢 Short", 0.95
                elif any(x in note for x in ['3 wk', '4 wk', '5 wk', '6 wk']): status, penalty = "🟡 Medium", 0.70
                else: status, penalty = "🔴 Long", 0.30
                injury_map[name] = {"status": status, "note": p['injury'], "penalty": penalty}
        return injury_map
    except: return {}

# --- 2. DATA ENGINE ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        cols = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        df['SuperScore'] = (df['Avg'] * 0.6 + df['Last3_Avg'] * 0.4).round(1)
        return df
    except: return pd.DataFrame()

df = load_data()
injury_lookup = fetch_injuries()

if not df.empty:
    # Initialize Session States
    if 'draft_history' not in st.session_state: st.session_state.draft_history = [] # List of dicts: {'pick': 1, 'team': 1, 'player': 'Name'}
    if 'my_team_names' not in st.session_state: st.session_state.my_team_names = []

    # --- SIDEBAR: LEAGUE SETUP ---
    with st.sidebar:
        st.title("⚙️ League Settings")
        num_teams = st.number_input("Total Teams", 10)
        my_pos = st.number_input("Your Draft Slot", 5)
        st.markdown("---")
        reqs = {'DEF': st.number_input("DEF", 4), 'MID': st.number_input("MID", 6),
                'RUC': st.number_input("RUC", 1), 'FWD': st.number_input("FWD", 4)}
        
        st.markdown("---")
        st.header("📢 Enter Pick")
        drafted_names = [d['player'] for d in st.session_state.draft_history]
        avail_list = sorted(df[~df['full_name'].isin(drafted_names)]['full_name'].unique())
        selected_player = st.selectbox("Search Player:", [""] + avail_list)
        
        if st.button("CONFIRM PICK", type="primary"):
            if selected_player:
                curr_pick = len(st.session_state.draft_history) + 1
                rnd = ((curr_pick - 1) // num_teams) + 1
                
                # Identify which team is currently picking
                if rnd % 2 != 0: # Odd Round: 1, 2, 3...
                    team_picking = (curr_pick - 1) % num_teams + 1
                else: # Even Round (Snake): 10, 9, 8...
                    team_picking = num_teams - ((curr_pick - 1) % num_teams)

                # Roster Validation for "My Team"
                if team_picking == my_pos:
                    p_data = df[df['full_name'] == selected_player].iloc[0]
                    p_pos = p_data['positions'].split('/')[0]
                    my_count = len(df[df['full_name'].isin(st.session_state.my_team_names) & df['positions'].str.contains(p_pos)])
                    if my_count >= (reqs[p_pos] + 2):
                        st.error(f"❌ {p_pos} Position Full!")
                    else:
                        st.session_state.draft_history.append({'pick': curr_pick, 'team': team_picking, 'player': selected_player})
                        st.session_state.my_team_names.append(selected_player)
                        st.rerun()
                else:
                    st.session_state.draft_history.append({'pick': curr_pick, 'team': team_picking, 'player': selected_player})
                    st.rerun()

        if st.button("Undo Last Pick"):
            if st.session_state.draft_history:
                last = st.session_state.draft_history.pop()
                if last['player'] in st.session_state.my_team_names:
                    st.session_state.my_team_names.remove(last['player'])
                st.rerun()

    # --- CALCULATIONS ---
    drafted_names = [d['player'] for d in st.session_state.draft_history]
    avail_df = df[~df['full_name'].isin(drafted_names)].copy()
    
    # Apply Injury Penalties
    def get_adj_score(name, base):
        inj = injury_lookup.get(name)
        return round(base * inj['penalty'], 1) if inj else base
    avail_df['Adj_Score'] = avail_df.apply(lambda x: get_adj_score(x['full_name'], x['SuperScore']), axis=1)

    # Dynamic VORP
    used_supply = {p: len(df[df['full_name'].isin(drafted_names) & df['positions'].str.contains(p)]) for p in reqs}
    baselines = {}
    for pos in reqs:
        slots_left = max(1, (reqs[pos] * num_teams) - used_supply[pos])
        pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('Adj_Score', ascending=False)
        idx = slots_left - 1
        baselines[pos] = pool.iloc[idx]['Adj_Score'] if idx < len(pool) else pool.iloc[-1]['Adj_Score']
    
    avail_df['VORP'] = avail_df.apply(lambda x: round(x['Adj_Score'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)
    avail_df['Health'] = avail_df['full_name'].apply(lambda x: injury_lookup.get(x, {}).get('status', '✅ Fit'))

    # --- TABS INTERFACE ---
    tab1, tab2, tab3 = st.tabs(["🎯 Draft Board", "📊 League Standings", "📜 Draft Log"])

    with tab1:
        st.title("Draft War Room")
        c1, c2 = st.columns(2)
        curr_p = len(st.session_state.draft_history) + 1
        c1.metric("Current Pick", f"#{curr_p}")
        
        st.dataframe(avail_df[['full_name', 'positions', 'VORP', 'Health', 'Adj_Score']]
                     .sort_values('VORP', ascending=False).head(25), use_container_width=True, hide_index=True)

    with tab2:
        st.title("League Rankings")
        # Build Team Data
        rankings = []
        for t in range(1, num_teams + 1):
            team_players = [d['player'] for d in st.session_state.draft_history if d['team'] == t]
            team_stats = df[df['full_name'].isin(team_players)]
            total_score = team_stats['SuperScore'].sum()
            avg_ss = team_stats['SuperScore'].mean() if not team_stats.empty else 0
            rankings.append({'Team': f"Team {t}", 'Total Power': round(total_score, 1), 'Avg Score': round(avg_ss, 1), 'Count': len(team_players)})
        
        rank_df = pd.DataFrame(rankings).sort_values('Total Power', ascending=False)
        
        # Infographic style
        st.table(rank_df)
        
        

    with tab3:
        st.title("Pick History")
        if st.session_state.draft_history:
            log_df = pd.DataFrame(st.session_state.draft_history).sort_values('pick', ascending=False)
            st.write(log_df)
        else:
            st.write("No picks made yet.")

else:
    st.error("Please ensure 'supercoach_data.csv' is in your directory.")
