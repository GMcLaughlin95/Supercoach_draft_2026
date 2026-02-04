import streamlit as st
import pandas as pd

st.set_page_config(page_title="Supercoach Draft Optimizer Pro", layout="wide")

# Load data
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('supercoach_data.csv')
        df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
        return df
    except:
        return pd.DataFrame()

df = load_data()

if not df.empty:
    # --- SIDEBAR SETTINGS ---
    with st.sidebar:
        st.header("⚙️ Draft Settings")
        
        # 1. Custom Number of Teams
        num_teams = st.number_input("Number of Teams in League", min_value=2, max_value=20, value=10)
        
        # 2. Custom Draft Position
        my_pos = st.number_input("Your Draft Position (Pick #)", min_value=1, max_value=num_teams, value=5)
        
        st.markdown("---")
        st.subheader("📋 Roster Requirements")
        # 3. Custom Team Configuration
        req_def = st.number_input("Defenders (DEF) required", value=4)
        req_mid = st.number_input("Midfielders (MID) required", value=6)
        req_ruc = st.number_input("Rucks (RUC) required", value=1)
        req_fwd = st.number_input("Forwards (FWD) required", value=4)
        
        st.markdown("---")
        st.header("Drafted Players")
        if 'drafted' not in st.session_state: st.session_state.drafted = []

        new_pick = st.selectbox("Search & Add Player:", [""] + sorted(list(df['full_name'].unique())))
        if st.button("Confirm Pick") and new_pick != "":
            if new_pick not in st.session_state.drafted:
                st.session_state.drafted.append(new_pick)
            st.rerun()
        
        if st.button("Undo Last Pick"):
            if st.session_state.drafted:
                st.session_state.drafted.pop()
                st.rerun()

    # --- LOGIC ---
    current_pick = len(st.session_state.drafted) + 1
    round_num = ((current_pick - 1) // num_teams) + 1
    
    # Calculate when your next turn is based on snake draft logic
    if round_num % 2 != 0: target_pick = (round_num - 1) * num_teams + my_pos
    else: target_pick = (round_num * num_teams) - my_pos + 1
    is_my_turn = (current_pick == target_pick)

    remaining = df[~df['full_name'].isin(st.session_state.drafted)].copy()

    # Dynamic VORP: Automatically adjusts based on team numbers and roster requirements
    def get_replacement_val(pos, count):
        pos_df = df[df['positions'].str.contains(pos, na=False)].sort_values('Avg', ascending=False)
        rank = count * num_teams # e.g. 10 teams * 4 DEF = 40th ranked DEF
        return pos_df.iloc[rank-1]['Avg'] if len(pos_df) >= rank else pos_df.iloc[-1]['Avg']

    REPLACEMENT = {
        'DEF': get_replacement_val('DEF', req_def),
        'MID': get_replacement_val('MID', req_mid),
        'RUC': get_replacement_val('RUC', req_ruc),
        'FWD': get_replacement_val('FWD', req_fwd)
    }
    remaining['VORP'] = remaining.apply(lambda x: x['Avg'] - REPLACEMENT.get(x['positions'].split('/')[0], 90), axis=1)

    # --- DISPLAY ---
    st.title("🚀 Supercoach Draft Optimizer")
    c1, c2 = st.columns(2)
    c1.metric("Current Pick", current_pick)
    if is_my_turn: c2.success("🎯 IT'S YOUR TURN!")
    else: c2.info(f"Your next pick is #{target_pick}")

    st.subheader("Top Available Players (Ranked by Positional Value)")
    st.dataframe(remaining[['full_name', 'positions', 'Avg', 'VORP']]
                 .sort_values('VORP', ascending=False).head(25), use_container_width=True)
else:
    st.error("Please ensure 'supercoach_data.csv' is uploaded to your GitHub repository.")
