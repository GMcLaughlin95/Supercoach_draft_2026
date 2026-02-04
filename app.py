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
    # Initialize session state
    if 'drafted' not in st.session_state: st.session_state.drafted = []
    if 'my_team_names' not in st.session_state: st.session_state.my_team_names = []

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Settings")
        num_teams = st.number_input("Teams", min_value=2, max_value=20, value=10)
        my_pos = st.number_input("Your Pick #", min_value=1, max_value=num_teams, value=5)
        
        st.markdown("---")
        req_def = st.number_input("DEF Needs", value=4)
        req_mid = st.number_input("MID Needs", value=6)
        req_ruc = st.number_input("RUC Needs", value=1)
        req_fwd = st.number_input("FWD Needs", value=4)
        
        st.markdown("---")
        current_pick = len(st.session_state.drafted) + 1
        round_num = ((current_pick - 1) // num_teams) + 1
        if round_num % 2 != 0: target_pick = (round_num - 1) * num_teams + my_pos
        else: target_pick = (round_num * num_teams) - my_pos + 1
        is_my_turn = (current_pick == target_pick)

        # IMPORTANT: This list filters out drafted players instantly
        available_list = sorted(df[~df['full_name'].isin(st.session_state.drafted)]['full_name'].unique())
        new_pick = st.selectbox("Draft Player:", [""] + available_list)
        
        if st.button("Confirm Pick") and new_pick != "":
            st.session_state.drafted.append(new_pick)
            if is_my_turn: st.session_state.my_team_names.append(new_pick)
            st.rerun()
        
        if st.button("Undo Last"):
            if st.session_state.drafted:
                removed = st.session_state.drafted.pop()
                if removed in st.session_state.my_team_names: st.session_state.my_team_names.remove(removed)
                st.rerun()

    # --- MAIN VIEW ---
    st.title("🚀 Supercoach Draft Optimizer")
    
    col1, col2 = st.columns(2)
    col1.metric("Pick #", current_pick)
    if is_my_turn: col2.success("🎯 YOUR TURN!")
    else: col2.info(f"Next turn: #{target_pick}")

    # Available Players Table
    st.subheader("📋 Best Available")
    remaining = df[~df['full_name'].isin(st.session_state.drafted)].copy()
    
    # Simple VORP calc for display
    remaining['VORP'] = remaining.apply(lambda x: round(x['Avg'] - 98, 1), axis=1) # Baseline 98
    st.dataframe(remaining[['full_name', 'positions', 'Avg', 'VORP']].sort_values('VORP', ascending=False).head(15), use_container_width=True)

    # --- INFOGRAPHIC SECTION ---
    st.markdown("---")
    st.subheader("🏟️ My Team Sheet")
    
    my_team_df = df[df['full_name'].isin(st.session_state.my_team_names)]
    
    # Layout 4 columns for positions
    d_col, m_col, r_col, f_col = st.columns(4)
    layout = [('DEF', d_col, "🟦"), ('MID', m_col, "🟩"), ('RUC', r_col, "🟧"), ('FWD', f_col, "🟥")]
    
    for pos, col, emoji in layout:
        with col:
            st.markdown(f"### {emoji} {pos}")
            # Filter players by position
            p_list = my_team_df[my_team_df['positions'].str.contains(pos)]
            if not p_list.empty:
                for _, p in p_list.iterrows():
                    st.success(f"**{p['full_name']}**\n\nAvg: {p['Avg']}")
            else:
                st.write("*Empty*")
