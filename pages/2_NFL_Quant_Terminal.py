import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from modules.nfl_engine import (
    WEEK_7_SCHEDULE,
    compute_nfl_team_baselines,
    calculate_matchup_factors_for_slate,
    process_nfl_player_matrix
)

st.set_page_config(page_title="NFL Quant Terminal", page_icon="🏈", layout="wide")

st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# Safe Scoped Session State
if "nfl_bet_slip" not in st.session_state:
    st.session_state["nfl_bet_slip"] = []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏈 NFL Quant Terminal")
    st.subheader("⚙️ NFL Model Settings")
    min_gp = st.slider("Minimum Current Season GP Filter", 1, 6, 3)
    
    st.subheader("🎯 Market-Tailored Edge Filters")
    profit_boost = st.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=0)

st.title("🏈 NFL Quant Terminal: Production Suite")
st.markdown("##### Multi-Market Accumulator, Schedule Pace Matchups, and Compound Parlay Generator")

tab1, tab2 = st.tabs(["📑 Checked Slips & Nexus Odds Comparator", "📁 Slate Matrix & Projections"])

# --- TAB 2: DATA & MATRIX ---
with tab2:
    st.subheader("Single Dropzone: NFL Play-by-Play Processor")
    uploaded_file = st.file_uploader("Drop your pbp-2026.csv file here", type=["csv"])
    
    col1, col2 = st.columns(2)
    with col1:
        market = st.selectbox(
            "Select Target Prop Market",
            ["Passing Yards", "Rushing Yards", "Receiving Yards", "Receptions", "Anytime Touchdown Scorer"]
        )
    with col2:
        if market == "Passing Yards":
            threshold = st.selectbox("Select Target Threshold Line", [174.5, 199.5, 224.5, 249.5, 274.5, 299.5], index=2)
        elif market == "Rushing Yards":
            threshold = st.selectbox("Select Target Threshold Line", [39.5, 49.5, 59.5, 69.5, 79.5, 89.5], index=2)
        elif market == "Receiving Yards":
            threshold = st.selectbox("Select Target Threshold Line", [39.5, 49.5, 59.5, 69.5, 79.5], index=1)
        elif market == "Receptions":
            threshold = st.selectbox("Select Target Threshold Line", [2.5, 3.5, 4.5, 5.5, 6.5], index=1)
        else:
            threshold = st.selectbox("Select Target Threshold Line", [0.5], index=0)
            
    target_date = st.date_input("Target Slate Date", datetime.strptime("2026-10-25", "%Y-%m-%d"))
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    slate_games = [g for g in WEEK_7_SCHEDULE if g["date"] == target_date_str]
    
    if uploaded_file is not None and len(slate_games) > 0:
        df_pbp = pd.read_csv(uploaded_file, low_memory=False)
        baselines = compute_nfl_team_baselines(df_pbp)
        matchup_factors = calculate_matchup_factors_for_slate(slate_games, baselines)
        
        st.markdown("🎯 **Filter Specific Game Matchups (Sorted by Pace Factor)**")
        badges = [f"{m['matchup']} [{m['combined_factor']}{' 🔥' if m['is_fire'] else ''}]" for m in matchup_factors]
        selected_badges = st.multiselect("Active Matchups", badges, default=badges, label_visibility="collapsed")
        
        chosen_matchups = [m for m in matchup_factors if any(m['matchup'] in b for b in selected_badges)]
        
        matrix_df = process_nfl_player_matrix(df_pbp, baselines, chosen_matchups, market, threshold, min_gp=min_gp)
        
        if not matrix_df.empty:
            st.markdown(f"### 📈 Slate Alt-Line Matrix ({market} > {threshold}):")
            
            matrix_df.insert(0, "Select", False)
            edited_df = st.data_editor(
                matrix_df,
                column_config={"Select": st.column_config.CheckboxColumn("Select", default=False)},
                disabled=[c for c in matrix_df.columns if c not in ["Select", "Market"]],
                hide_index=True,
                use_container_width=True
            )
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("➕ Add Checked Players to Bet Slip"):
                    checked_players = edited_df[edited_df["Select"] == True]
                    for _, row in checked_players.iterrows():
                        st.session_state["nfl_bet_slip"].append(row.to_dict())
                    st.success(f"Added {len(checked_players)} legs to Bet Slip! Check Tab 1.")
                    
            with btn_col2:
                if st.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs"):
                    top5 = matrix_df.head(5)
                    for _, row in top5.iterrows():
                        st.session_state["nfl_bet_slip"].append(row.to_dict())
                    st.success("Auto-loaded top 5 highest-probability legs to Tab 1!")

# --- TAB 1: BET SLIP & COMPARATOR ---
with tab1:
    st.subheader("📝 Checked Players & Nexus Odds Comparator")
    
    if st.button("🗑️ Clear Bet Slip"):
        st.session_state["nfl_bet_slip"] = []
        st.rerun()
        
    if len(st.session_state["nfl_bet_slip"]) > 0:
        slip_df = pd.DataFrame(st.session_state["nfl_bet_slip"])
        if "Odds" not in slip_df.columns:
            slip_df["Odds"] = -110
            
        st.markdown("Enter your Sportsbook Odds below. True probabilities and compound parlay edges calculate live:")
        user_slip = st.data_editor(
            slip_df[["Player", "Clean_Team", "Opponent", "Market", "Line", "Odds"]],
            column_config={
                "Odds": st.column_config.NumberColumn("Odds", default=-110, step=5, format="%d")
            },
            use_container_width=True
        )
        
        dec_odds_list = []
        compound_true_prob = 1.0
        
        for i, row in user_slip.iterrows():
            o = row["Odds"]
            dec = (1 + o / 100.0) if o > 0 else (1 + 100.0 / abs(o))
            dec_odds_list.append(dec)
            prob = slip_df.loc[i, "Model_Over_Prob_%"] / 100.0
            compound_true_prob *= prob
            
        checked_parlay_dec = np.prod(dec_odds_list)
        boosted_dec = 1.0 + (checked_parlay_dec - 1.0) * (1.0 + (profit_boost / 100.0))
        
        checked_parlay_amer = f"+{int(round((checked_parlay_dec - 1) * 100))}" if checked_parlay_dec >= 2.0 else f"-{int(round(100 / (checked_parlay_dec - 1)))}"
        boosted_amer = f"+{int(round((boosted_dec - 1) * 100))}" if boosted_dec >= 2.0 else f"-{int(round(100 / (boosted_dec - 1)))}"
        
        breakeven_prob = 1.0 / boosted_dec
        compound_edge = (compound_true_prob - breakeven_prob) * 100
        
        st.markdown("### 🚀 Live Compound Slip & Profit Boost Calculator")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Checked Parlay Odds", checked_parlay_amer)
        m2.metric(f"Boosted (+{profit_boost}%)", boosted_amer)
        m3.metric("Model Slip True Prob", f"{round(compound_true_prob * 100, 1)}%")
        m4.metric("Compound Slip Edge", f"{round(compound_edge, 1)}%")
    else:
        st.info("Go to Tab 2, select your market and line, check your desired players, and click '+ Add Checked to Bet Slip'.")
