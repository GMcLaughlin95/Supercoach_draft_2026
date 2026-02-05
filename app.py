import streamlit as st
import pandas as pd

st.set_page_config(page_title="Supercoach Pro Draft", layout="wide")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        cols = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        def get_superscore(row):
            score = (row['Avg'] * 0.6) + (row['Last3_Avg'] * 0.4)
            if row['gamesPlayed'] >= 21: score += 2
            elif row['gamesPlayed'] <= 14: score -= 5
            return round(score, 1)
            
        df['SuperScore'] = df.apply(get_superscore, axis=1)
        return df
    except: return pd.DataFrame()

df = load_data()

if not df.empty:
    if 'drafted' not in st.session_state: st.session_state.drafted = []
    if 'my_team' not in st.session_state: st.session_state.my_team = []

    # --- SIDEBAR SETTINGS ---
    with st.sidebar:
        st.header("⚙️ League Setup")
        num_teams = st.number_input("Teams in League", 10)
        my_pick = st.number_input("Your Draft Position", 5)
        st.markdown("---")
        
        # User-set requirements
        reqs = {
            'DEF': st.number_input("DEF Starters", 4),
            'MID': st.number_input("MID Starters", 6),
            'RUC': st.number_input("RUC Starters", 1),
            'FWD': st.number_input("FWD Starters", 4)
        }
        
        st.markdown("---")
        st.header("📢 Draft Entry")
        
        avail = sorted(df[~df['full_name'].isin(st.session_state.drafted)]['full_name'].unique())
        new_pick_name = st.selectbox("Select Player:", [""] + avail)
        
        if st.button("CONFIRM PICK", type="primary"):
            if new_pick_name:
                player_data = df[df['full_name'] == new_pick_name].iloc[0]
                primary_pos = player_data['positions'].split('/')[0]
                
                # Check current turn logic
                curr_total = len(st.session_state.drafted) + 1
                rnd = ((curr_total - 1) // num_teams) + 1
                is_me = (curr_total == ((rnd - 1) * num_teams + my_pick if rnd % 2 != 0 else (rnd * num_teams) - my_pick + 1))
                
                # LIMIT LOGIC: Check if my position is full (Req + 2)
                if is_me:
                    my_df = df[df['full_name'].isin(st.session_state.my_team)]
                    current_pos_count = len(my_df[my_df['positions'].str.contains(primary_pos)])
                    
                    if current_pos_count >= (reqs[primary_pos] + 2):
                        st.error(f"❌ Limit Reached! You cannot draft more than {reqs[primary_pos] + 2} {primary_pos}s.")
                    else:
                        st.session_state.drafted.append(new_pick_name)
                        st.session_state.my_team.append(new_pick_name)
                        st.rerun()
                else:
                    st.session_state.drafted.append(new_pick_name)
                    st.rerun()

        if st.button("Undo Last"):
            if st.session_state.drafted:
                rem = st.session_state.drafted.pop()
                if rem in st.session_state.my_team: st.session_state.my_team.remove(rem)
                st.rerun()

    # --- DYNAMIC VORP ENGINE ---
    # 1. Total League Demand
    league_demand = {k: v * num_teams for k, v in reqs.items()}
    
    # 2. Global Supply Used
    global_drafted = df[df['full_name'].isin(st.session_state.drafted)]
    used_supply = {'DEF':0, 'MID':0, 'RUC':0, 'FWD':0}
    for _, r in global_drafted.iterrows():
        p = r['positions'].split('/')[0]
        if p in used_supply: used_supply[p] += 1

    # 3. Dynamic Baselines
    avail_df = df[~df['full_name'].isin(st.session_state.drafted)].copy()
    baselines = {}
    for pos in reqs:
        remaining_slots = max(1, league_demand[pos] - used_supply[pos])
        pos_pool = avail_df[avail_df['positions'].str.contains(pos)].sort_values('SuperScore', ascending=False)
        
        idx = remaining_slots - 1
        baselines[pos] = pos_pool.iloc[idx]['SuperScore'] if idx < len(pos_pool) else pos_pool.iloc[-1]['SuperScore']

    avail_df['VORP'] = avail_df.apply(lambda x: round(x['SuperScore'] - baselines.get(x['positions'].split('/')[0], 80), 1), axis=1)

    # --- DASHBOARD ---
    st.title("🚀 Supercoach Pro Draft Board")
    
    c1, c2 = st.columns([1,3])
    c1.metric("Current Pick", len(st.session_state.drafted) + 1)
    
    st.dataframe(avail_df[['full_name', 'positions', 'SuperScore', 'VORP']]
                 .sort_values('VORP', ascending=False).head(15), use_container_width=True)

    # --- INFOGRAPHIC WITH INTERCHANGE ---
    st.markdown("---")
    st.subheader("🏟️ My Team Structure")
    
    my_squad_names = st.session_state.my_team
    cols = st.columns(4)
    
    for i, (pos, icon) in enumerate([('DEF','🟦'),('MID','🟩'),('RUC','🟧'),('FWD','🟥')]):
        with cols[i]:
            st.markdown(f"### {icon} {pos}")
            
            # Filter my players in this position
            pos_players = []
            for name in my_squad_names:
                p_info = df[df['full_name'] == name].iloc[0]
                if pos in p_info['positions']:
                    pos_players.append(p_info)
            
            # Display Starters vs Interchange
            for idx, p in enumerate(pos_players):
                if idx < reqs[pos]:
                    st.success(f"**{p['full_name']}** ({p['Avg']})")
                elif idx < reqs[pos] + 2:
                    st.info(f"🔄 **INTERCHANGE**\n\n{p['full_name']} ({p['Avg']})")
            
            if not pos_players: st.caption("No players selected")

else:
    st.error("Missing 'supercoach_data.csv'")
