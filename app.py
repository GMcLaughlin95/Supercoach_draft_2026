import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- 1. PERSISTENCE ENGINE ---
SAVE_FILE = "draft_state.json"

def save_state():
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
        st.session_state.params = {"num_teams": 10, "my_slot": 5, "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6}

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

        df['Power_Rating'] = df.apply(calculate_custom_power, axis=1)
        df['Risk_Profile'] = df['gamesPlayed'].apply(lambda x: "🟢 Low" if x >= 18 else ("🟡 Mod" if x >= 12 else "🔴 High"))
        return df
    except: return pd.DataFrame()

df = load_data()

# --- 2. HELPERS ---
def get_current_turn(curr_pick, total_teams):
    if total_teams <= 0: return 1
    rnd = ((curr_pick - 1) // total_teams) + 1
    if rnd % 2 != 0: return (curr_pick - 1) % total_teams + 1
    return total_teams - ((curr_pick - 1) % total_teams)

def get_team_name(tid):
    return st.session_state.team_names.get(str(tid), f"Team {tid}")

def check_roster_limit(chosen_pos, team_id, p, history_list):
    team_picks = [d for d in history_list if d['team'] == team_id]
    current_count = sum(1 for p_pick in team_picks if p_pick.get('assigned_pos') == chosen_pos)
    if chosen_pos == "RUC":
        return current_count < 2
    return current_count < (p.get(chosen_pos, 0) + 2)

# --- 3. PAGE ROUTING ---
if st.session_state.step == "home":
    st.title("Welcome Smarty Pants")
    if st.button("Start", type="primary", use_container_width=True):
        st.session_state.step = "settings"; save_state(); st.rerun()

elif st.session_state.step == "settings":
    st.title("Draft Settings")
    col1, col2 = st.columns(2)
    with col1:
        n_teams = st.number_input("Total Teams", value=st.session_state.params["num_teams"], min_value=1)
        m_slot = st.number_input("Your Slot", value=st.session_state.params["my_slot"], min_value=1, max_value=n_teams)
    with col2:
        st.write("**Target Roster**")
        d_r = st.number_input("DEF", value=st.session_state.params["DEF"])
        m_r = st.number_input("MID", value=st.session_state.params["MID"])
        r_r = st.number_input("RUC", value=2, disabled=True) 
        f_r = st.number_input("FWD", value=st.session_state.params["FWD"])
    st.divider()
    for i in range(1, n_teams + 1):
        existing = st.session_state.team_names.get(str(i), f"Team {i}")
        st.session_state.team_names[str(i)] = st.text_input(f"Slot {i} Name", value=existing)
    if st.button("Start Draft", type="primary", use_container_width=True):
        st.session_state.params = {"num_teams": n_teams, "my_slot": m_slot, "DEF": d_r, "MID": m_r, "RUC": 2, "FWD": f_r}
        st.session_state.step = "draft"; save_state(); st.rerun()

elif st.session_state.step == "draft":
    p = st.session_state.params
    with st.sidebar:
        st.title("🛡️ Command Center")
        st.info(f"Slot: {p['my_slot']} | Teams: {p['num_teams']}")
        if st.button("🚨 RESET DRAFT", use_container_width=True): reset_draft()

    curr_p_num = len(st.session_state.draft_history) + 1
    active_id = get_current_turn(curr_p_num, p['num_teams'])
    total_slots = sum([p['DEF'], p['MID'], p['RUC'], p['FWD']]) + 8
    is_complete = len(st.session_state.draft_history) >= (p['num_teams'] * total_slots)

    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_df = df[~df['full_name'].isin(taken_names)].copy()

    tab_list = ["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis"]
    if is_complete:
        tab_list.append("🏆 Final Teams")
    
    tabs = st.tabs(tab_list)

    if not is_complete:
        st.subheader(f"⏱️ Now Picking: {get_team_name(active_id)}")
        act_c1, act_c2 = st.columns([1, 2])
        with act_c1:
            if st.button("🤖 Sim to My Turn", use_container_width=True):
                while True:
                    cp = len(st.session_state.draft_history) + 1
                    tn = get_current_turn(cp, p['num_teams'])
                    if tn == p['my_slot']: break
                    tkn = [d['player'] for d in st.session_state.draft_history]
                    av_sim = df[~df['full_name'].isin(tkn)].sort_values('Power_Rating', ascending=False)
                    if av_sim.empty: break
                    choice, p_pos = None, None
                    for _, r in av_sim.iterrows():
                        for po in r['positions'].split('/'):
                            if check_roster_limit(po, tn, p, st.session_state.draft_history):
                                choice, p_pos = r['full_name'], po; break
                        if choice: break
                    if choice: st.session_state.draft_history.append({"pick": cp, "team": tn, "player": choice, "assigned_pos": p_pos})
                    else: break
                save_state(); st.rerun()
        with act_c2:
            r_c1, r_c2, r_c3 = st.columns([2, 1, 1])
            sel = r_c1.selectbox("Select Player:", [""] + sorted(avail_df['full_name'].tolist()), label_visibility="collapsed")
            conf_pos, can_conf = None, False
            if sel:
                pos_o = df[df['full_name'] == sel].iloc[0]['positions'].split('/')
                conf_pos = r_c2.radio("Pos:", pos_o, horizontal=True, label_visibility="collapsed")
                if check_roster_limit(conf_pos, active_id, p, st.session_state.draft_history): can_conf = True
            if r_c3.button("CONFIRM", type="primary", disabled=not can_conf, use_container_width=True):
                st.session_state.draft_history.append({"pick": curr_p_num, "team": active_id, "player": sel, "assigned_pos": conf_pos})
                save_state(); st.rerun()

    # Tab Rendering Logic
    with tabs[0]:
        if is_complete: st.info("Draft Complete.")
        else:
            search = st.text_input("🔍 Filter Board:", "")
            disp = avail_df.copy()
            if search: disp = disp[disp['full_name'].str.contains(search, case=False)]
            st.dataframe(disp[['full_name', 'positions', 'Avg', 'Risk_Profile', 'gamesPlayed']].head(100), use_container_width=True, hide_index=True)

    with tabs[1]:
        my_pks = [d for d in st.session_state.draft_history if d['team'] == p['my_slot']]
        if my_pks:
            inf_cols = st.columns(5)
            on_f, bnch, trk = {x: [] for x in ['DEF', 'MID', 'RUC', 'FWD']}, [], {x: 0 for x in ['DEF', 'MID', 'RUC', 'FWD']}
            # Ensure high scorers are listed on field in the UI
            sorted_my_pks = sorted(my_pks, key=lambda x: df[df['full_name']==x['player']]['Avg'].values[0] if not df[df['full_name']==x['player']].empty else 0, reverse=True)
            for pk in sorted_my_pks:
                if trk[pk['assigned_pos']] < p[pk['assigned_pos']]:
                    on_f[pk['assigned_pos']].append(pk['player']); trk[pk['assigned_pos']] += 1
                else: bnch.append(f"{pk['player']} ({pk['assigned_pos']})")
            for i, cat in enumerate(['DEF', 'MID', 'RUC', 'FWD', 'Bench']):
                with inf_cols[i]:
                    st.write(f"**{cat}**")
                    for n in (on_f[cat] if cat != 'Bench' else bnch): st.info(n)

    with tabs[2]:
        if st.session_state.draft_history:
            log_df = pd.DataFrame(st.session_state.draft_history).copy()
            log_df['team_name'] = log_df['team'].apply(get_team_name)
            st.dataframe(log_df[['pick', 'team_name', 'player', 'assigned_pos']].sort_values('pick', ascending=False), use_container_width=True, hide_index=True)

    with tabs[3]:
        all_t = []
        for i in range(1, p['num_teams'] + 1):
            t_pks = [d for d in st.session_state.draft_history if d['team'] == i]
            all_t.append({"Team": get_team_name(i), "Total": round(df[df['full_name'].isin([x['player'] for x in t_pks])]['Avg'].sum(), 1)})
        if all_t: st.bar_chart(pd.DataFrame(all_t).set_index("Team")['Total'])

    if is_complete:
        with tabs[4]:
            st.header("🏆 Final Team Rankings")
            summary_data = []
            for i in range(1, p['num_teams'] + 1):
                t_pks = [d for d in st.session_state.draft_history if d['team'] == i]
                field_pts, total_pts = 0.0, 0.0
                
                for pos in ['DEF', 'MID', 'RUC', 'FWD']:
                    pos_list = [d['player'] for d in t_pks if d['assigned_pos'] == pos]
                    p_scores = sorted(df[df['full_name'].isin(pos_list)]['Avg'].tolist(), reverse=True)
                    
                    limit = p[pos]
                    field_pts += sum(p_scores[:limit])
                    total_pts += sum(p_scores)
                
                summary_data.append({
                    "Team Name": get_team_name(i),
                    "On-Field Points": round(field_pts, 1),
                    "Full Squad Points": round(total_pts, 1)
                })
            
            st.table(pd.DataFrame(summary_data).sort_values("On-Field Points", ascending=False))
            st.divider()
            for i in range(1, p['num_teams'] + 1):
                with st.expander(f"📍 {get_team_name(i)} Roster"):
                    st.dataframe(pd.DataFrame([d for d in st.session_state.draft_history if d['team'] == i])[['pick', 'player', 'assigned_pos']], hide_index=True)
