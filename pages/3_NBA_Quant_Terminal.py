import streamlit as st
import pandas as pd
import numpy as np
import sys
import os

# Ensure modules folder is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.nba_engine import (
    load_nba_datasets,
    calculate_matchup_factor,
    calculate_projection_and_odds,
    NBA_SCHEDULE,
    TEAM_MAP,
    REV_TEAM_MAP
)

st.set_page_config(page_title="NBA Quant Terminal", layout="wide")

# ==========================================
# 1. ISOLATED SESSION STATE INITIALIZATION
# ==========================================
if "nba_bet_slip" not in st.session_state:
    st.session_state.nba_bet_slip = []
if "nba_odds_inputs" not in st.session_state:
    st.session_state.nba_odds_inputs = {}

# ==========================================
# 2. SIDEBAR CONTROLS
# ==========================================
st.sidebar.title("🏀 NBA Quant Controls")
boost_pct = st.sidebar.slider("Active Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)
min_games = st.sidebar.slider("Min Games Played (G)", min_value=1, max_value=20, value=3, step=1)
min_mpg = st.sidebar.slider("Min Minutes / Game (MPG)", min_value=10.0, max_value=36.0, value=20.0, step=1.0)

# ==========================================
# 3. DATA INGESTION
# ==========================================
try:
    df_players, team_dict, baselines = load_nba_datasets()
except Exception as e:
    st.error(f"Error loading CSV files: {e}. Please ensure 'nba_players_per_poss.csv' and 'nba_team_ratings.csv' are in the root directory.")
    st.stop()

# ==========================================
# 4. SCHEDULE & PACE PILL GENERATION
# ==========================================
available_dates = sorted(list(set(g["date"] for g in NBA_SCHEDULE)))
selected_date = st.selectbox("📅 Select Slate Date:", available_dates, index=0)

slate_games = [g for g in NBA_SCHEDULE if g["date"] == selected_date]

pill_labels = []
pill_to_game = {}
for g in slate_games:
    away = g["away"]
    home = g["home"]
    away_pace = team_dict.get(away, {}).get("Pace", baselines["pace"])
    home_pace = team_dict.get(home, {}).get("Pace", baselines["pace"])
    game_pace = (away_pace + home_pace) / 2.0
    
    icon = "🔥" if game_pace >= 102.5 else ("🧊" if game_pace < 99.5 else "⚡")
    label = f"{away} @ {home} [{game_pace:.1f} {icon}]"
    pill_labels.append(label)
    pill_to_game[label] = (away, home, game_pace)

selected_pills = st.multiselect("Select Games to Analyze:", pill_labels, default=pill_labels)
selected_matchups = [pill_to_game[p] for p in selected_pills]

# ==========================================
# 5. MAIN NAVIGATION TABS
# ==========================================
tab2, tab1 = st.tabs(["📊 Slate Matrix & Projections", "🚀 Live Compound Slip & Profit Boost Calculator"])

# ------------------------------------------
# TAB 2: SLATE MATRIX
# ------------------------------------------
with tab2:
    col_m, col_l = st.columns([1, 1])
    with col_m:
        market_choice = st.selectbox(
            "Target Prop Market:",
            ["3-Pointers Made (3PM)", "Assists (AST)", "Rebounds (REB)", "Points (PTS)", "PRA"]
        )
    
    line_options_map = {
        "3-Pointers Made (3PM)": [0.5, 1.5, 2.5, 3.5, 4.5],
        "Assists (AST)": [1.5, 2.5, 3.5, 4.5, 5.5, 7.5, 9.5],
        "Rebounds (REB)": [2.5, 3.5, 5.5, 7.5, 9.5, 11.5],
        "Points (PTS)": [9.5, 14.5, 19.5, 24.5, 29.5],
        "PRA": [14.5, 19.5, 24.5, 29.5, 34.5, 39.5]
    }
    with col_l:
        chosen_line = st.selectbox("Select Milestone Alt-Line Floor:", line_options_map[market_choice], index=1)

    active_teams = set()
    opp_map = {}
    for away, home, _ in selected_matchups:
        active_teams.add(away)
        active_teams.add(home)
        opp_map[away] = home
        opp_map[home] = away

    slate_players = df_players[
        (df_players["Team"].isin(active_teams)) &
        (df_players["G"] >= min_games) &
        (df_players["MPG"] >= min_mpg)
    ].copy()

    stat_col_map = {
        "3-Pointers Made (3PM)": "3P",
        "Assists (AST)": "AST",
        "Rebounds (REB)": "TRB",
        "Points (PTS)": "PTS",
        "PRA": "PRA"
    }
    stat_key = stat_col_map[market_choice]

    rows = []
    for _, p in slate_players.iterrows():
        team = p["Team"]
        opp = opp_map[team]
        team_pace = team_dict.get(team, {}).get("Pace", baselines["pace"])
        opp_data = team_dict.get(opp, {})
        
        g_pace, pace_factor, matchup_factor = calculate_matchup_factor(
            team_pace, opp_data, baselines, market_choice
        )
        
        proj_val, prob_pct, fair_odds = calculate_projection_and_odds(
            p[stat_key], p["MPG"], g_pace, matchup_factor, chosen_line, market_choice
        )
        
        is_away = any(g[0] == team and g[1] == opp for g in selected_matchups)
        opp_str = f"@{opp}" if is_away else f"vs {opp}"
        
        rows.append({
            "Select": False,
            "Player": p["Player"],
            "Clean_Team": team,
            "Opponent": opp_str,
            "Baseline_Stat": round(p[stat_key] * (32.0 / 48.0), 2),
            "Current_MPG": round(p["MPG"], 1),
            "Matchup_Factor": matchup_factor,
            "Matchup_Proj": proj_val,
            "Model_Over_Prob_%": prob_pct,
            "Fair_American_Odds": fair_odds,
            "Market": market_choice,
            "Line": chosen_line
        })

    matrix_df = pd.DataFrame(rows).sort_values(by="Model_Over_Prob_%", ascending=False)

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("⚡ Auto-Fill Top 5 Highest Probability Floor Plays"):
            top_5 = matrix_df.head(5).to_dict("records")
            for item in top_5:
                if not any(b["Player"] == item["Player"] and b["Market"] == item["Market"] and b["Line"] == item["Line"] for b in st.session_state.nba_bet_slip):
                    st.session_state.nba_bet_slip.append(item)
            st.success("Transferred Top 5 Floor Plays to Bet Slip!")

    edited_matrix = st.data_editor(
        matrix_df,
        column_config={"Select": st.column_config.CheckboxColumn(required=True)},
        disabled=["Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_MPG", "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market", "Line"],
        hide_index=True,
        use_container_width=True
    )

    with col_btn2:
        if st.button("➕ Add Selected Players to Bet Slip"):
            selected_rows = edited_matrix[edited_matrix["Select"] == True].to_dict("records")
            for item in selected_rows:
                if not any(b["Player"] == item["Player"] and b["Market"] == item["Market"] and b["Line"] == item["Line"] for b in st.session_state.nba_bet_slip):
                    st.session_state.nba_bet_slip.append(item)
            st.success(f"Added {len(selected_rows)} selections to Bet Slip!")

# ------------------------------------------
# TAB 1: BET SLIP & LIVE BOOST EVALUATOR
# ------------------------------------------
with tab1:
    st.subheader("📋 Active Bet Slip & Odds Comparator")
    
    if st.button("🗑️ Clear Entire Bet Slip"):
        st.session_state.nba_bet_slip = []
        st.session_state.nba_odds_inputs = {}
        st.rerun()

    if not st.session_state.nba_bet_slip:
        st.info("Your bet slip is empty. Select players in Tab 2 or click 'Auto-Fill Top 5'.")
    else:
        compound_joint_prob = 1.0
        dec_odds_list = []
        valid_odds = True

        for idx, leg in enumerate(st.session_state.nba_bet_slip):
            p_name = leg["Player"]
            m_prob = leg["Model_Over_Prob_%"] / 100.0
            compound_joint_prob *= m_prob
            
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            with c1:
                st.write(f"**{p_name}** ({leg['Clean_Team']} {leg['Opponent']})")
                st.caption(f"{leg['Market']} > {leg['Line']}")
            with c2:
                st.metric("Model Win %", f"{leg['Model_Over_Prob_%']}%")
            with c3:
                key = f"nba_odds_{p_name}_{leg['Market']}_{leg['Line']}"
                odds_val = st.text_input("Sportsbook Odds", value=st.session_state.nba_odds_inputs.get(key, "-400"), key=key)
                st.session_state.nba_odds_inputs[key] = odds_val
            
            try:
                numeric_odds = float(odds_val)
                if numeric_odds < 0:
                    dec = 1.0 + (100.0 / abs(numeric_odds))
                    imp_prob = abs(numeric_odds) / (abs(numeric_odds) + 100.0)
                else:
                    dec = 1.0 + (numeric_odds / 100.0)
                    imp_prob = 100.0 / (numeric_odds + 100.0)
                
                edge = (m_prob - imp_prob) * 100.0
                dec_odds_list.append(dec)
                
                with c4:
                    st.metric("Implied %", f"{imp_prob * 100:.1f}%")
                with c5:
                    st.metric("Edge %", f"{edge:+.1f}%")
            except:
                valid_odds = False
                st.warning("Enter valid American odds (e.g. -350 or +120)")

        st.divider()
        st.subheader("🚀 Live Compound Slip & Profit Boost Calculator")
        
        if valid_odds and len(dec_odds_list) > 0:
            parlay_dec = np.prod(dec_odds_list)
            if parlay_dec >= 2.0:
                unboosted_am = f"+{int(round((parlay_dec - 1.0) * 100))}"
            else:
                unboosted_am = f"{int(round(-100.0 / (parlay_dec - 1.0)))}"
            
            boosted_profit = (parlay_dec - 1.0) * (1.0 + (boost_pct / 100.0))
            boosted_dec = boosted_profit + 1.0
            if boosted_dec >= 2.0:
                boosted_am = f"+{int(round((boosted_dec - 1.0) * 100))}"
            else:
                boosted_am = f"{int(round(-100.0 / (boosted_dec - 1.0)))}"
            
            compound_edge = ((compound_joint_prob * boosted_dec) - 1.0) * 100.0

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Checked Parlay Odds", unboosted_am)
            r2.metric(f"Boosted (+{boost_pct}%)", boosted_am)
            r3.metric("Model Slip True Prob", f"{compound_joint_prob * 100:.1f}%")
            r4.metric("Compound Slip Edge", f"{compound_edge:+.1f}%")
