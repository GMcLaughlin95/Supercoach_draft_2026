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
                "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6, "bench_size": 8
            })
            if "bench_size" not in st.session_state.params:
                st.session_state.params["bench_size"] = 8
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
        st.session_state.params = {"num_teams": 10, "my_slot": 5, "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6, "bench_size": 8}

@st.cache_data
def load_data():
    try:
        # 1. Load Main Supercoach Stats Data
        df = pd.read_csv('supercoach_data.csv')
        df.columns = [c.strip() for c in df.columns]
        if 'full_name' not in df.columns:
            df['full_name'] = (df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)).str.strip()
        cols_to_fix = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
            
        # 2. Load Expert Ratings & Parse Format
        expert_scores = {}
        try:
            exp_df = pd.read_csv('Draft Doctor SC Ratings.csv')
            data_rows = exp_df.iloc[1:].copy() # Drop the first row of headers (Steve/Statesman)
            data_rows['Rank'] = pd.to_numeric(data_rows['Rank'], errors='coerce')
            
            for _, r in data_rows.iterrows():
                rank = r['Rank']
                if pd.isna(rank): continue
                
                # Check all columns for player names to capture both experts across all positions
                for col in data_rows.columns:
                    if col == 'Rank': continue
                    name = str(r[col]).strip()
                    if name and name.lower() != 'nan':
                        # Record their best (lowest) rank
                        current_best = expert_scores.get(name, 999)
                        if rank < current_best:
                            expert_scores[name] = rank
        except Exception as e:
            st.warning(f"Note: Could not load 'Draft Doctor SC Ratings.csv'. {e}")

        # Map to main dataframe
        df['Expert_Rank'] = df['full_name'].map(expert_scores).fillna(999)
        
        # 3. Enhanced Power Rating calculation
        def calculate_custom_power(row):
            # Base Stats (Weighted down slightly to make room for expert opinion)
            score = (row['Avg'] * 0.85) + (row['Last3_Avg'] * 0.05)
            if 'DEF' in row['positions']: score += (row['KickInAvg'] * 0.2)
            
            # Incorporate Expert Consensus Bonuses
            exp_rank = row['Expert_Rank']
            if exp_rank <= 10:
                score += 12.0
            elif exp_rank <= 25:
                score += 8.0
            elif exp_rank <= 50:
                score += 4.0
            elif exp_rank <= 100:
                score += 1.5
                
            return round(score, 1)

        df['Power_Rating'] = df.apply(calculate_custom_power, axis=1)
        df['Risk_Profile'] = df['gamesPlayed'].apply(lambda x: "🟢 Low" if x >= 18 else ("🟡 Mod" if x >= 12 else "🔴 High"))
        return df
    except Exception as e: 
        st.error(f"Error Loading Data: {e}")
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

def check_roster_limit(chosen_pos, team_id, p, history_list):
    count = sum(1 for d in history_list if d['team'] == team_id and d.get('assigned_pos') == chosen_pos)
    if chosen_pos == "RUC":
        return count < 2
    return count < (p.get(chosen_pos, 0) + (p.get('bench_size', 8) // 2 + 1))

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
        b_size = st.number_input("Bench Size (Total Players)", value=st.session_state.params.get("bench_size", 8), min_value=0)
    with col2:
        st.write("**Target Field Roster**")
        d_r = st.number_input("DEF", value=st.session_state.params["DEF"])
        m_r = st.number_input("MID", value=st.session_state.params["MID"])
        r_r = st.number_input("RUC", value=2, max_value=2) 
        f_r = st.number_input("FWD", value=st.session_state.params["FWD"])
    st.divider()
    for i in range(1, n_teams + 1):
        existing = st.session_state.team_names.get(str(i), f"Team {i}")
        st.session_state.team_names[str(i)] = st.text_input(f"Slot {i} Name", value=existing)
    if st.button("Start Draft", type="primary", use_container_width=True):
        st.session_state.params = {"num_teams": n_teams, "my_slot": m_slot, "DEF": d_r, "MID": m_r, "RUC": 2, "FWD": f_r, "bench_size": b_size}
        st.session_state.step = "draft"; save_state(); st.rerun()

elif st.session_state.step == "draft":
    p = st.session_state.params
    bench_val = p.get('bench_size', 8)
    total_slots_per_team = sum([p['DEF'], p['MID'], p['RUC'], p['FWD']]) + bench_val
    total_expected_picks = p['num_teams'] * total_slots_per_team
    is_complete = len(st.session_state.draft_history) >= total_expected_picks

    with st.sidebar:
        st.title("🛡️ Command Center")
        st.info(f"Slot: {p['my_slot']} | Teams: {p['num_teams']}")
        if not is_complete:
            st.write(f"Pick: {len(st.session_state.draft_history) + 1} / {total_expected_picks}")
        if st.button("🚨 RESET DRAFT", use_container_width=True): reset_draft()

    curr_p_num = len(st.session_state.draft_history) + 1
    active_id = get_current_turn(curr_p_num, p['num_teams'])
    
    taken_names = [d['player'] for d in st.session_state.draft_history]
    avail_df = df[~df['full_name'].isin(taken_names)].copy()

    if is_complete:
        st.balloons()
        st.success("🎊 DRAFT COMPLETE! Final standings and rosters are ready.")
    else:
        st.subheader(f"⏱️ Now Picking: {get_team_name(active_id)}")
        act_c1, act_c2 = st.columns([1, 2])
        with act_c1:
            if st.button("🤖 Sim to My Turn", use_container_width=True):
                while len(st.session_state.draft_history) < total_expected_picks:
                    cp = len(st.session_state.draft_history) + 1
                    tn = get_current_turn(cp, p['num_teams'])
                    if tn == p['my_slot']: break
                    
                    tkn = [d['player'] for d in st.session_state.draft_history]
                    av_sim = df[~df['full_name'].isin(tkn)].copy()
                    if av_sim.empty: break
                    
                    costs = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
                    for pos in costs:
                        pool = av_sim[av_sim['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
                        if len(pool) > (p['num_teams'] + 2): 
                            costs[pos] = pool.iloc[0]['Power_Rating'] - pool.iloc[p['num_teams']+2]['Power_Rating']
                    
                    sim_pks = [d for d in st.session_state.draft_history if d['team'] == tn]
                    sim_counts = {pos: sum(1 for d in sim_pks if d['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
                    
                    best_player, best_pos, best_score = None, None, -9999.0
                    for _, r in av_sim.iterrows():
                        for po in r['positions'].split('/'):
                            if check_roster_limit(po, tn, p, st.session_state.draft_history):
                                score = r['Power_Rating'] + (costs.get(po, 0) * 0.4)
                                if sim_counts.get(po, 0) < p.get(po, 0): score += 5.0
                                else: score -= 25.0
                                    
                                if score > best_score:
                                    best_score = score
                                    best_player = r['full_name']
                                    best_pos = po
                    
                    if best_player:
                        st.session_state.draft_history.append({"pick": cp, "team": tn, "player": best_player, "assigned_pos": best_pos})
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

        if not avail_df.empty:
            active_pks = [d for d in st.session_state.draft_history if d['team'] == active_id]
            counts = {pos: sum(1 for d in active_pks if d['assigned_pos'] == pos) for pos in ['DEF', 'MID', 'RUC', 'FWD']}
            costs = {pos: 0 for pos in ['DEF', 'MID', 'RUC', 'FWD']}
            for pos in costs:
                pool = avail_df[avail_df['positions'].str.contains(pos, na=False)].sort_values('Power_Rating', ascending=False)
                if len(pool) > (p['num_teams'] + 2): costs[pos] = pool.iloc[0]['Power_Rating'] - pool.iloc[p['num_teams']+2]['Power_Rating']
            avail_df['Opt_Score'] = avail_df.apply(lambda row: max([row['Power_Rating'] + (costs.get(x, 0) * 0.4) + (5.0 if counts[x] < p[x] else -25.0) for x in row['positions'].split('/') if check_roster_limit(x, active_id, p, st.session_state.draft_history)] + [-999]), axis=1)
            top_3 = avail_df[avail_df['Opt_Score'] > -500].sort_values('Opt_Score', ascending=False).head(3)
            rec_text = " / ".join([f"**{i+1}. {r['full_name']}** ({r['positions']})" for i, r in top_3.iterrows()])
            st.markdown(f"<p style='font-size: 0.85rem; color: #666;'>💡 Recommended: {rec_text}</p>", unsafe_allow_html=True)

    # --- TABS ---
    tab_titles = ["🎯 Big Board", "📋 My Team", "📈 Log", "📊 Analysis"]
    if is_complete: tab_titles.append("🏆 Final Teams")
    tabs = st.tabs(tab_titles)
    
    with tabs[0]:
        if is_complete: st.info("Draft complete.")
        else:
            search = st.text_input("🔍 Filter Board:", "")
            disp = avail_df.copy()
            if search: disp = disp[disp['full_name'].str.contains(search, case=False)]
            if not disp.empty and 'Opt_Score' in disp.columns:
                disp = disp.sort_values('Opt_Score', ascending=False)
                disp['Score'] = disp['Opt_Score'].apply(lambda x: "FULL" if x <= -500 else round(x, 1))
                
                # Format Expert Rank for Display
                disp['Expert'] = disp['Expert_Rank'].apply(lambda x: f"Top {int(x)}" if x != 999 else "-")
                
                cols_to_show = ['full_name', 'positions', 'Score', 'Avg', 'Expert', 'Risk_Profile', 'gamesPlayed']
                st.dataframe(disp[cols_to_show].head(100), use_container_width=True, hide_index=True)
            st.divider()
            cols = st.columns(4)
            for i, pos in enumerate(['DEF', 'MID', 'RUC', 'FWD']):
                cur_c = sum(1 for d in st.session_state.draft_history if d['team'] == active_id and d['assigned_pos'] == pos)
                rem = p[pos] - cur_c
                cols[i].metric(pos, f"{cur_c}/{p[pos]}", delta=f"-{rem}" if rem > 0 else "FIELD FULL", delta_color="inverse" if rem > 0 else "normal")

    with tabs[1]:
        my_pks = [d for d in st.session_state.draft_history if d['team'] == p['my_slot']]
        if my_pks:
            inf_cols = st.columns(5)
            on_f, bnch, trk = {x: [] for x in ['DEF', 'MID', 'RUC', 'FWD']}, [], {x: 0 for x in ['DEF', 'MID', 'RUC', 'FWD']}
            for pk in my_pks:
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
            all_t.append({"Team": get_team_name(i), "Total Avg": df[df['full_name'].isin([x['player'] for x in t_pks])]['Avg'].sum()})
        if all_t: st.bar_chart(pd.DataFrame(all_t).set_index("Team")['Total Avg'])

    if is_complete:
        with tabs[4]:
            st.header("🏆 Final League Performance")
            final_stats = []
            for i in range(1, p['num_teams'] + 1):
                t_pks = [d for d in st.session_state.draft_history if d['team'] == i]
                f_score, w_score = 0.0, 0.0
                for pos in ['DEF', 'MID', 'RUC', 'FWD']:
                    p_list = [d['player'] for d in t_pks if d['assigned_pos'] == pos]
                    p_avg = sorted(df[df['full_name'].isin(p_list)]['Avg'].tolist(), reverse=True)
                    f_score += sum(p_avg[:p[pos]])
                    w_score += sum(p_avg)
                final_stats.append({
                    "Team Name": get_team_name(i),
                    "Combined Points (Fielded)": round(f_score, 1),
                    "Combined Points (Whole Team)": round(w_score, 1)
                })
            st.table(pd.DataFrame(final_stats).sort_values("Combined Points (Fielded)", ascending=False))
            st.divider()
            for i in range(1, p['num_teams'] + 1):
                with st.expander(f"📍 {get_team_name(i)} Full List"):
                    st.dataframe(pd.DataFrame([d for d in st.session_state.draft_history if d['team'] == i])[['pick', 'player', 'assigned_pos']], hide_index=True)
