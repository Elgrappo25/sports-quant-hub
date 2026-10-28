import streamlit as st
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.nba_engine import (
    load_nba_datasets,
    calculate_matchup_factor,
    calculate_projection_and_odds,
    fetch_live_nba_schedule,
    TEAM_MAP,
    REV_TEAM_MAP
)

st.set_page_config(page_title="NBA Quant Terminal", layout="wide")

# ==========================================
# 1. ISOLATED SESSION STATE INITIALIZATION
# ==========================================
if "nba_bet_slip" not in st.session_state:
    st.session_state.nba_bet_slip = []

# ==========================================
# 2. SIDEBAR CONTROLS
# ==========================================
st.sidebar.title("🏀 NBA Quant Controls")
boost_pct = st.sidebar.slider("Active Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)
min_games = st.sidebar.slider("Min Games Played (G)", min_value=1, max_value=20, value=3, step=1)
min_mpg = st.sidebar.slider("Min Minutes / Game (MPG)", min_value=10.0, max_value=36.0, value=20.0, step=1.0)

# ==========================================
# 3. MAIN NAVIGATION TABS
# ==========================================
tab1, tab2 = st.tabs(["🚀 Live Compound Slip & Profit Boost Calculator", "📊 Slate Matrix & Projections"])

# ------------------------------------------
# TAB 1: BET SLIP & LIVE BOOST EVALUATOR
# ------------------------------------------
with tab1:
    if st.button("🗑️ Clear Bet Slip"):
        st.session_state.nba_bet_slip = []
        st.rerun()

    if not st.session_state.nba_bet_slip:
        st.info("Select your sportsbook and enter Nexus Odds. Real-time edges calculate automatically once entered.")
    else:
        df_slip = pd.DataFrame(st.session_state.nba_bet_slip)

        # Ensure correct column existence and defaults
        if "Include in Parlay" not in df_slip.columns:
            df_slip["Include in Parlay"] = True
        if "Sportsbook" not in df_slip.columns:
            df_slip["Sportsbook"] = "FanDuel"
        if "Nexus Odds (+/-)" not in df_slip.columns:
            df_slip["Nexus Odds (+/-)"] = None
        if "Delete" not in df_slip.columns:
            df_slip["Delete"] = False

        column_order = [
            "Include in Parlay",
            "Sportsbook",
            "Player",
            "Opponent",
            "Market",
            "Line",
            "Nexus Odds (+/-)",
            "Model Prob (%)",
            "Delete"
        ]
        df_slip = df_slip[[c for c in column_order if c in df_slip.columns]]

        sportsbook_options = ["FanDuel", "DraftKings", "bet365", "BetMGM", "theScore Bet", "BetRivers"]

        edited_slip = st.data_editor(
            df_slip,
            column_config={
                "Include in Parlay": st.column_config.CheckboxColumn("Include in Parlay", default=True),
                "Sportsbook": st.column_config.SelectboxColumn("Sportsbook", options=sportsbook_options, default="FanDuel", required=True),
                "Player": st.column_config.TextColumn("Player", disabled=True),
                "Opponent": st.column_config.TextColumn("Opponent", disabled=True),
                "Market": st.column_config.TextColumn("Market", disabled=True),
                "Line": st.column_config.NumberColumn("Line", disabled=True),
                "Nexus Odds (+/-)": st.column_config.NumberColumn("Nexus Odds (+/-)", step=1),
                "Model Prob (%)": st.column_config.NumberColumn("Model Prob (%)", format="%.1f", disabled=True),
                "Delete": st.column_config.CheckboxColumn("Delete", default=False),
            },
            hide_index=True,
            use_container_width=True
        )

        # Check for individual deletes
        if edited_slip["Delete"].any():
            remaining_slip = edited_slip[edited_slip["Delete"] == False].to_dict("records")
            st.session_state.nba_bet_slip = remaining_slip
            st.rerun()
        else:
            st.session_state.nba_bet_slip = edited_slip.to_dict("records")

        # Live Edge Evaluation
        active_legs = []
        dec_odds_list = []
        joint_model_prob = 1.0

        for idx, row in edited_slip.iterrows():
            if row["Include in Parlay"] and pd.notna(row["Nexus Odds (+/-)"]) and row["Nexus Odds (+/-)"] != 0:
                odds = int(row["Nexus Odds (+/-)"])
                m_prob = float(row["Model Prob (%)"]) / 100.0

                if odds < 0:
                    dec = 1.0 + (100.0 / abs(odds))
                    imp_prob = abs(odds) / (abs(odds) + 100.0)
                    odds_str = f"{odds}"
                else:
                    dec = 1.0 + (odds / 100.0)
                    imp_prob = 100.0 / (odds + 100.0)
                    odds_str = f"+{odds}"

                edge = (m_prob - imp_prob) * 100.0

                dec_odds_list.append(dec)
                joint_model_prob *= m_prob

                active_legs.append({
                    "Sportsbook": row["Sportsbook"],
                    "Player": row["Player"],
                    "Opponent": row["Opponent"],
                    "Market": row["Market"],
                    "Line": row["Line"],
                    "Odds": odds_str,
                    "Model Prob": f"{row['Model Prob (%)']:.1f}%",
                    "Edge %": f"{edge:+.1f}%"
                })

        st.subheader("📈 Live Edge Evaluation:")
        if active_legs:
            df_active = pd.DataFrame(active_legs)
            st.dataframe(df_active, hide_index=True, use_container_width=True)
        else:
            st.caption("Enter your Nexus Odds (+/-) in the table above to view live individual edge calculations.")

        st.divider()
        st.subheader("🚀 Live Compound Slip & Profit Boost Calculator")

        if dec_odds_list:
            parlay_dec = np.prod(dec_odds_list)
            if parlay_dec >= 2.0:
                unboosted_am = f"+{int(round((parlay_dec - 1.0) * 100))}"
                parlay_imp_prob = 100.0 / (float(unboosted_am[1:]) + 100.0)
            else:
                unboosted_am = f"{int(round(-100.0 / (parlay_dec - 1.0)))}"
                parlay_imp_prob = abs(float(unboosted_am)) / (abs(float(unboosted_am)) + 100.0)

            boosted_profit = (parlay_dec - 1.0) * (1.0 + (boost_pct / 100.0))
            boosted_dec = boosted_profit + 1.0
            if boosted_dec >= 2.0:
                boosted_am = f"+{int(round((boosted_dec - 1.0) * 100))}"
            else:
                boosted_am = f"{int(round(-100.0 / (boosted_dec - 1.0)))}"

            compound_edge = (joint_model_prob - parlay_imp_prob) * 100.0

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Checked Parlay Odds", unboosted_am)
            r2.metric(f"Boosted (+{boost_pct}%)", boosted_am)
            r3.metric("Model Slip True Prob", f"{joint_model_prob * 100:.1f}%")
            r4.metric("Compound Slip Edge", f"{compound_edge:+.1f}%")
        else:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Checked Parlay Odds", "--")
            r2.metric(f"Boosted (+{boost_pct}%)", "--")
            r3.metric("Model Slip True Prob", "--")
            r4.metric("Compound Slip Edge", "--")

# ------------------------------------------
# TAB 2: DATA INGESTION & SLATE MATRIX
# ------------------------------------------
with tab2:
    st.subheader("📁 Daily Data Ingestion")
    
    uploaded_files = st.file_uploader(
        "Upload NBA Data Files (Drag & drop both Player Per-100 & Team Ratings CSVs together)",
        type=["csv"],
        accept_multiple_files=True,
        key="nba_central_uploader"
    )

    player_file = None
    team_file = None

    if uploaded_files:
        for f in uploaded_files:
            fname = f.name.lower()
            if "player" in fname or "poss" in fname:
                player_file = f
            elif "team" in fname or "rating" in fname:
                team_file = f
        
        if player_file is None or team_file is None:
            for f in uploaded_files:
                f.seek(0)
                first_line = f.readline().decode("utf-8", errors="ignore").lower()
                f.seek(0)
                if "player" in first_line:
                    player_file = f
                elif "offense four factors" in first_line or "team" in first_line:
                    team_file = f

    if player_file is None and os.path.exists("nba_players_per_poss.csv"):
        player_file = "nba_players_per_poss.csv"
    if team_file is None and os.path.exists("nba_team_ratings.csv"):
        team_file = "nba_team_ratings.csv"

    if player_file is None or team_file is None:
        st.info("👆 Please drop your NBA CSV files into the upload box above to populate the slate matrix.")
        st.stop()

    try:
        df_players, team_dict, baselines = load_nba_datasets(player_file, team_file)
    except Exception as e:
        st.error(f"Error reading CSV files: {e}")
        st.stop()

    st.divider()

    selected_date = st.date_input("📅 Select Slate Date:", value=date.today())
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    slate_games = fetch_live_nba_schedule(selected_date_str)
    
    if not slate_games:
        st.warning(f"No scheduled NBA games found for {selected_date_str}. Please select another date on the calendar.")
        st.stop()

    # Pill Buttons normalized around 2.00 Combined Baseline (matching NFL & NHL)
    pill_labels = []
    pill_to_game = {}
    for g in slate_games:
        away = g["away"]
        home = g["home"]
        away_pace = team_dict.get(away, {}).get("Pace", baselines["pace"])
        home_pace = team_dict.get(home, {}).get("Pace", baselines["pace"])
        game_pace = (away_pace + home_pace) / 2.0
        
        # Combined Pace Index centered around 2.00
        combined_index = round((game_pace / baselines["pace"]) * 2.0, 2)
        
        icon = "🔥" if combined_index >= 2.03 else ("🧊" if combined_index < 1.98 else "⚡")
        label = f"{away} @ {home} [{combined_index:.2f} {icon}]"
        pill_labels.append(label)
        pill_to_game[label] = (away, home, game_pace)

    selected_pills = st.multiselect("Select Games to Analyze:", pill_labels, default=pill_labels)
    selected_matchups = [pill_to_game[p] for p in selected_pills]

    if not selected_matchups:
        st.info("Select at least one game pill above to view players.")
        st.stop()

    st.divider()

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

    edited_matrix = st.data_editor(
        matrix_df,
        column_config={"Select": st.column_config.CheckboxColumn(required=True)},
        disabled=["Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_MPG", "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market", "Line"],
        hide_index=True,
        use_container_width=True
    )

    st.write("")
    col_btn1, col_btn2 = st.columns([1, 1])
    
    # Left Column: Manual Add
    with col_btn1:
        if st.button("➕ Add Selected Players to Bet Slip"):
            selected_rows = edited_matrix[edited_matrix["Select"] == True].to_dict("records")
            added_count = 0
            for item in selected_rows:
                if not any(b["Player"] == item["Player"] and b["Market"] == item["Market"] and b["Line"] == item["Line"] for b in st.session_state.nba_bet_slip):
                    st.session_state.nba_bet_slip.append({
                        "Include in Parlay": True,
                        "Sportsbook": "FanDuel",
                        "Player": item["Player"],
                        "Opponent": item["Opponent"],
                        "Market": item["Market"],
                        "Line": item["Line"],
                        "Nexus Odds (+/-)": None,
                        "Model Prob (%)": item["Model_Over_Prob_%"],
                        "Delete": False
                    })
                    added_count += 1
            if added_count > 0:
                st.rerun()

    # Right Column: 3-Layer Weighted Auto-Add Engine
    with col_btn2:
        if st.button("⚡ Auto-Fill Top 5 Highest Probability Floor Plays"):
            # Layer 1: Target Sweet-Spot Floor Window (72% to 89%)
            floor_pool = matrix_df[
                (matrix_df["Model_Over_Prob_%"] >= 72.0) & 
                (matrix_df["Model_Over_Prob_%"] <= 89.0)
            ].copy()
            
            # Fallback if window is too restrictive on a small slate
            if len(floor_pool) < 5:
                floor_pool = matrix_df[matrix_df["Model_Over_Prob_%"] >= 65.0].copy()
            
            # Layer 2: Composite Weighting (Probability boosted by Matchup Factor)
            floor_pool["Weighted_Score"] = floor_pool["Model_Over_Prob_%"] * (floor_pool["Matchup_Factor"] ** 1.5)
            floor_pool = floor_pool.sort_values(by="Weighted_Score", ascending=False)
            
            # Layer 3: Zero Cannibalization (Enforce Max 1 player per team)
            top_5 = []
            teams_used = set()
            for _, row in floor_pool.iterrows():
                if row["Clean_Team"] not in teams_used:
                    top_5.append(row.to_dict())
                    teams_used.add(row["Clean_Team"])
                if len(top_5) == 5:
                    break
                    
            # Fallback fill if slate has fewer than 5 unique teams
            if len(top_5) < 5:
                for _, row in floor_pool.iterrows():
                    if not any(b["Player"] == row["Player"] for b in top_5):
                        top_5.append(row.to_dict())
                    if len(top_5) == 5:
                        break

            # Instant Transfer with rerun
            added_count = 0
            for item in top_5:
                if not any(b["Player"] == item["Player"] and b["Market"] == item["Market"] and b["Line"] == item["Line"] for b in st.session_state.nba_bet_slip):
                    st.session_state.nba_bet_slip.append({
                        "Include in Parlay": True,
                        "Sportsbook": "FanDuel",
                        "Player": item["Player"],
                        "Opponent": item["Opponent"],
                        "Market": item["Market"],
                        "Line": item["Line"],
                        "Nexus Odds (+/-)": None,
                        "Model Prob (%)": item["Model_Over_Prob_%"],
                        "Delete": False
                    })
                    added_count += 1
            if added_count > 0:
                st.rerun()
