import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. PERSISTENCE ENGINE ---
SAVE_FILE = "draft_state.json"

def save_state():
    """Saves everything: the picks, the team names, and the locked parameters."""
    state_data = {
        "step": st.session_state.step,
        "draft_history": st.session_state.draft_history, 
        "team_names": st.session_state.team_names,
        "params": st.session_state.params
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(state_data, f)

def load_state_logic():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.step = state.get("step", "home")
            st.session_state.draft_history = state.get("draft_history", [])
            st.session_state.team_names = state.get("team_names", {})
            st.session_state.params = state.get("params", {
                "num_teams": 10, "my_slot": 5, 
                "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6
            })
            return True
    return False

def reset_draft():
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- INITIALIZATION ---
if 'step' not in st.session_state:
    if not load_state_logic():
        st.session_state.step = "home"
        st.session_state.draft_history = []
        st.session_state.team_names = {}
        st.session_state.params = {
            "num_teams": 10, "my_slot": 5, 
            "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6
        }

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

# --- 3. PAGE ROUTING ---

if st.session_state.step == "home":
    st.title("Welcome Smarty Pants")
    st.write("Ready to dominate the 2026 Supercoach season?")
    if st.button("Start", type="primary", use_container_width=True):
        st.session_state.step = "settings"
        save_state()
        st.rerun()

elif st.session_state.step == "settings":
    st.title("Draft Settings")
    col1, col2 = st.columns(2)
    with col1:
        n_teams = st.number_input("Total Teams", value=st.session_state.params["num_teams"], min_value=1)
        m_slot = st.number_input("Your Slot", value=st.session_state.params["my_slot"], min_value=1, max_value=n_teams)
    with col2:
        st.write("**Target Roster (On-Field)**")
        d_req = st.number_input("DEF", value=st.session_state.params["DEF"])
        m_req = st.number_input("MID", value=st.session_state.params["MID"])
        r_req = st.number_input("RUC", value=st.session_state.params["RUC"])
        f_req = st.number_input("FWD", value=st.session_state.params["FWD"])

    st.divider()
    for i in range(1, n_teams + 1):
        existing = st.session_state.team_names.get(str(i), f"Team {i}")
        st.session_state.team_names[str(i)] = st.text_input(f"Slot {i} Name", value=existing)

    if st.button("Start Draft", type="primary", use_container_width=True):
        st.session_state.params = {"num_teams": n_teams, "my_slot": m_slot, "DEF": d_req, "MID": m_req, "RUC": r_req, "FWD": f_req}
        st.session_state.step = "draft"
        save_state()
        st.rerun()

elif st.session_state.step == "draft":
    p = st.session_state.params
    with st.sidebar:
        st.title("🛡️ Command Center")
        st.info(f"League: {p['num_teams']} Teams | Your Slot: {p['my_slot']}")
        st.write("**Roster Limits:**")
        st.caption(f"DEF: {p['DEF']} | MID: {p['MID']} | RUC: {p['RUC']} | FWD: {p['FWD']}")
        st.divider()
        if st.button("🚨 RESET DRAFT", use_container_width=True):
            reset_draft()

    curr_p_num = len(st.session_state.draft_history) + 1
    active_team_id = get_current_turn(curr_p_num, p['num_teams'])
    active_name = get_team_name(active_team_id)
    
    total_required = sum([p['DEF'], p['MID'], p['RUC'], p['FWD']]) + 8 
    is_draft_complete = len(st.session_state.draft_history) >= (p['num_teams'] * total_required)

    # --- FIX: ALWAYS DEFINE avail_df BEFORE TABS ---
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_df = df[~df['full_name'].isin(taken_names)].copy()

    if is_draft_complete:
        st.success("🎊 DRAFT COMPLETE!")
    else:
        st.subheader(f"⏱️ Now Picking: {active_name}")
        act_col1, act_col2 = st.columns([1, 2])
        
        with act_col1:
            if st.button("🤖 Sim to My Turn", use_container_width=True):
                while True:
                    curr_p = len(st.session_state.draft_history) + 1
                    turn = get_current_turn(curr_p, p['num_teams'])
                    if turn == p['my_slot']: break
                    taken_sim = [d['player'] for d in st.session_state.draft_history]
                    avail_sim = df[~df['full_name'].isin(taken_sim)].sort_values('Power_Rating', ascending=False)
                    if avail_sim.empty: break
                    ai_choice, ai_pos = None, None
                    for _, row in avail_sim.iterrows():
                        for po in row['positions'].split('/'):
                            if check_roster_limit(po, turn, p, st.session_state.draft_history):
                                ai_choice, ai_pos = row['full_name'], po
                                break
                        if ai_choice: break
                    if ai_choice:
                        st.session_state.draft_history.append({"pick": curr_p, "team": turn, "player": ai_choice, "assigned_pos": ai_pos})
                    else: break
                save_state(); st.rerun()

        with act_col2:
            avail_list = sorted(avail_df['full_name'].tolist()) if not avail_df.empty else []
            r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
            selected = r_col1.selectbox("Select Player:", [""] + avail_list, label_visibility="collapsed")
            assigned_pos, can_confirm = None, False
            if selected:
                pos_opts = df[df['full_name'] == selected].iloc[0]['positions'].split('/')
                assigned_pos = r_col2.radio("Pos:", pos_opts, horizontal=True, label_visibility="collapsed")
                if check_roster_limit(assigned_pos, active_team_id, p, st.session_state.draft_history):
                    can_confirm = True
            if r_col3.button("CONFIRM", type="primary", disabled=not can_confirm, use_container_width=True):
                st.session_state.draft_history.append({"pick": curr_p_num, "team": active_team_id, "player": selected, "assigned_pos": assigned_pos})
                save_state(); st.rerun()

        # Recommendations logic
        if not avail_df.empty:
            active_picks = [d for d in st.session_state.draft_history if d['team'] == active_team_id]
            counts = {pos: sum(1 for d in active_picks if d['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
            costs = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
            for pos in costs:
                pool = avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
                if len(pool) > (p['num_teams'] + 2): costs[pos] = pool.iloc[0]['Power_Rating'] - pool.iloc[p['num_teams']+2]['Power_Rating']
            
            avail_df['Opt_Score'] = avail_df.apply(lambda row: max([row['Power_Rating'] + (costs.get(x, 0) * 0.4) + (5.0 if counts[x] < p[x] else -25.0) for x in row['positions'].split('/') if check_roster_limit(x, active_team_id, p, st.session_state.draft_history)] + [-999]), axis=1)
            top_3 = avail_df[avail_df['Opt_Score'] > -500].sort_values('Opt_Score', ascending=False).head(3)
            rec_text = " / ".join([f"**{i+1}. {r['full_name']}** ({r['positions']})" for i, r in top_3.iterrows()])
            st.markdown(f"<p style='font-size: 0.85rem; color: #666;'>💡 Recommended: {rec_text}</p>", unsafe_allow_html=True)

    # --- TABS ---
    tabs = st.tabs(["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis"] + (["🏆 Final Teams"] if is_draft_complete else []))
    
    with tabs[0]:
        if is_draft_complete:
            st.info("The Draft is complete! All players have been selected.")
        else:
            search_q = st.text_input("🔍 Filter Board:", "")
            display_df = avail_df.copy()
            if search_q: display_df = display_df[display_df['full_name'].str.contains(search_q, case=False)]
            if not display_df.empty:
                # Ensure Opt_Score exists before sorting
                if 'Opt_Score' in display_df.columns:
                    display_df = display_df.sort_values('Opt_Score', ascending=False)
                    display_df['Score'] = display_df['Opt_Score'].apply(lambda x: "FULL" if x <= -500 else round(x, 1))
                else:
                    display_df['Score'] = "-"
                st.dataframe(display_df[['full_name', 'positions', 'Score', 'Avg', 'Risk_Profile', 'gamesPlayed']].head(200), use_container_width=True, hide_index=True)
            
            st.divider()
            c_cols = st.columns(4)
            # Re-calculating counts for current metric display if draft not complete
            active_picks = [d for d in st.session_state.draft_history if d['team'] == active_team_id]
            counts = {pos: sum(1 for d in active_picks if d['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
            for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
                rem = p[pos] - counts[pos]
                c_cols[i].metric(pos, f"{counts[pos]}/{p[pos]}", delta=f"-{rem}" if rem > 0 else "FULL", delta_color="inverse" if rem > 0 else "normal")

    with tabs[1]:
        my_picks = [d for d in st.session_state.draft_history if d['team'] == p['my_slot']]
        if my_picks:
            st.subheader(f"🏟️ {get_team_name(p['my_slot'])} Infographic")
            info_cols = st.columns(5)
            on_f, bnch, trk = {x: [] for x in ['DEF', 'MID', 'RUC', 'FWD']}, [], {x: 0 for x in ['DEF', 'MID', 'RUC', 'FWD']}
            for pk in my_picks:
                if trk[pk['assigned_pos']] < p[pk['assigned_pos']]:
                    on_f[pk['assigned_pos']].append(pk['player']); trk[pk['assigned_pos']] += 1
                else: bnch.append(f"{pk['player']} ({pk['assigned_pos']})")
            for i, cat in enumerate(['DEF', 'MID', 'RUC', 'FWD', 'Bench']):
                with info_cols[i]:
                    st.write(f"**{cat}**")
                    for n in (on_f[cat] if cat != 'Bench' else bnch): st.info(n)
        else: st.info("You haven't drafted any players yet.")

    with tabs[2]:
        if st.session_state.draft_history:
            log_df = pd.DataFrame(st.session_state.draft_history).copy()
            log_df['team_name'] = log_df['team'].apply(get_team_name)
            st.dataframe(log_df[['pick', 'team_name', 'player', 'assigned_pos']].sort_values('pick', ascending=False), use_container_width=True, hide_index=True)
        else: st.info("Draft history is empty.")

    with tabs[3]:
        all_t = []
        for i in range(1, p['num_teams'] + 1):
            t_pks = [d for d in st.session_state.draft_history if d['team'] == i]
            row = {"Team": get_team_name(i), "Total": df[df['full_name'].isin([x['player'] for x in t_pks])]['Avg'].sum()}
            all_t.append(row)
        if all_t: st.bar_chart(pd.DataFrame(all_t).set_index("Team")['Total'])

    if is_draft_complete:
        with tabs[4]:
            for i in range(1, p['num_teams'] + 1):
                with st.expander(f"📍 {get_team_name(i)}"):
                    st.table(pd.DataFrame([d for d in st.session_state.draft_history if d['team'] == i]))
