import streamlit as st
import pandas as pd

st.set_page_config(page_title="Supercoach Draft Pro", layout="wide")

# Load data
@st.cache_data
def load_data():
    df = pd.read_csv('supercoach_data.csv')
    df['full_name'] = (df['first_name'] + ' ' + df['last_name']).str.strip()
    return df

df = load_data()

st.title("🚀 Pick 5: Draft Optimizer")

# Sidebar for Drafted Players
if 'drafted' not in st.session_state:
    st.session_state.drafted = []

with st.sidebar:
    st.header("Drafted Players")
    new_pick = st.selectbox("Search Player to Add:", [""] + list(df['full_name'].unique()))
    if st.button("Confirm Pick") and new_pick != "":
        st.session_state.drafted.append(new_pick)
    
    if st.button("Undo Last Pick"):
        if st.session_state.drafted: st.session_state.drafted.pop()

# Main Logic
remaining = df[~df['full_name'].isin(st.session_state.drafted)].copy()

# Calculate VORP (Using our logic)
REPLACEMENT = {'DEF': 99.4, 'MID': 98.4, 'RUC': 101.7, 'FWD': 99.7}
remaining['VORP'] = remaining.apply(lambda x: x['Avg'] - REPLACEMENT.get(x['positions'].split('/')[0], 90), axis=1)

st.subheader("Top Recommendations")
st.dataframe(remaining[['full_name', 'positions', 'Avg', 'VORP']]
             .sort_values('VORP', ascending=False).head(15), use_container_width=True)