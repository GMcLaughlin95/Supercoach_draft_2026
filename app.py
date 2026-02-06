import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Supercoach War Room 2026", layout="wide", initial_sidebar_state="expanded")

# --- Constants
SAVE_FILE = "draft_state.json"

# --- 1. Persistence Engine ---
def save_state():
    """Save the app state to a JSON file."""
    state_data = {
        "step": st.session_state.step,
        "draft_history": st.session_state.draft_history, 
        "team_names": st.session_state.team_names,
        "params": st.session_state.params
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(state_data, f)

def load_state_logic():
    """Load the app state from a JSON file."""
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            state = json.load(f)
            st.session_state.step = state.get("step", "home")
            st.session_state.draft_history = state.get("draft_history", [])
            st.session_state.team_names = state.get("team_names", {})
            st.session_state.params = state.get("params", {
                "num_teams": 10, "draft_order": list(range(1, 11)), 
                "DEF": 6, "MID": 8, "RUC": 2, "FWD": 6
            })
            return True
    return False

def reset_draft():
    """Completely reset the draft."""
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- 2. Data Load ---
@st.cache_data
def load_player_data():
    """Load player data from the CSV."""
    try:
        df = pd.read_csv('supercoach_data.csv')
        df.columns = [c.strip() for c in df.columns]
        if 'full_name' not in df.columns:
            df['full_name'] = (df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)).str.strip()
        
        # Convert key columns to numeric and handle missing data
        numeric_columns = ['Avg', 'Last3_Avg', 'gamesPlayed', 'KickInAvg', 'CbaAvg']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)

        # Custom scoring algorithm
        df['Power_Rating'] = df.apply(calculate_power_rating, axis=1)
        df['Risk_Profile'] = df['gamesPlayed'].apply(get_risk_profile)
        return df
    except Exception as e:
        st.error(f"Error loading player data: {e}")
        return pd.DataFrame()

def calculate_power_rating(row):
    """Calculate the custom power rating of a player."""
    score = (row['Avg'] * 0.9) + (row['Last3_Avg'] * 0.1)
    if 'DEF' in row['positions']:
        score += (row['KickInAvg'] * 0.2)
    return round(score, 1)

def get_risk_profile(games_played):
    """Classify players based on games played."""
    if games_played >= 18:
        return "🟢 Low"
    elif games_played >= 12:
        return "🟡 Moderate"
    else:
        return "🔴 High"

def filter_players(df, search_query="", position=None, risk=None, min_avg=0):
    """Filter players based on user criteria."""
    if search_query:
        df = df[df['full_name'].str.contains(search_query, case=False)]
    if position:
        df = df[df['positions'].str.contains(position, na=False)]
    if risk:
        df = df[df['Risk_Profile'] == risk]
    if min_avg > 0:
        df = df[df['Avg'] >= min_avg]
    return df

df = load_player_data()

# --- 3. Helper Functions ---
def get_current_turn(curr_pick, draft_order):
    """Determine which team's turn it is."""
    total_teams = len(draft_order)
    if total_teams <= 0:
        return 1
    rnd_number = ((curr_pick - 1) // total_teams) + 1
    pos = (curr_pick - 1) % total_teams
    return draft_order[-pos - 1] if rnd_number % 2 == 0 else draft_order[pos]
