import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="NHL Quant Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("Dynamic Weighting, Matchup Adjustments, and Positive EV Slip Evaluator")

# -------------------------------------------------------------
# SIDEBAR CONFIGURATION
# -------------------------------------------------------------
st.sidebar.header("🏒 NHL Model Settings")

phase_weight = st.sidebar.slider(
    "Current Season Sample Weight (%)", 
    min_value=0, 
    max_value=100, 
    value=20, 
    step=5,
    help="Phase 1: 20%, Phase 2: 40%, Phase 3: 70%, Phase 4: 100%"
) / 100.0

min_gp = st.sidebar.slider(
    "Minimum Current Season GP Filter",
    min_value=1,
    max_value=15,
    value=3,
    step=1
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Market-Tailored Edge Filters")
profit_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

# Session state initialization
if "nhl_bet_slip" not in st.session_state:
    st.session_state["nhl_bet_slip"] = []

tab1, tab2 = st.tabs(["📋 Checked Slips & Odds Comparator", "📁 Slate Matrix & Projections"])

# -------------------------------------------------------------
# TAB 2: DATA INGESTION & MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Data Ingestion & Slate Filter")
    
    col_date, col_drop = st.columns([1, 3])
    with col_date:
        slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"))
    
    with col_drop:
        uploaded_files = st.file_uploader(
            "Drop all 4 Natural Stat Trick CSV files here", 
            type=["csv"], 
            accept_multiple_files=True
        )

    if uploaded_files:
        st.session_state["nhl_uploaded_files"] = uploaded_files

    active_files = st.session_state.get("nhl_uploaded_files", None)

    if active_files and len(active_files) >= 2:
        try:
            # File Categorization
            player_files = []
            game_files = []
            for f in active_files:
                name_lower = f.name.lower()
                if "game" in name_lower or "team" in name_lower:
                    game_files.append(f)
                else:
                    player_files.append(f)

            def read_csv_clean(f):
                f.seek(0)
                df = pd.read_csv(f)
                df.columns = df.columns.str.strip()
                return df

            # Process Players
            p_dfs = [read_csv_clean(f) for f in player_files]
            
            # Identify current vs prior by length or naming
            if len(p_dfs) >= 2:
                if len(p_dfs[0]) > len(p_dfs[1]):
                    df_base, df_curr = p_dfs[0], p_dfs[1]
                else:
                    df_base, df_curr = p_dfs[1], p_dfs[0]
            else:
                df_base = p_dfs[0]
                df_curr = p_dfs[0].copy()

            # Robust Column Renaming
            def find_col(df, possible_names):
                for col in possible_names:
                    match = [c for c in df.columns if c.lower() == col.lower()]
                    if match:
                        return match[0]
                return None

            p_name_col_base = find_col(df_base, ["Player", "Name", "Skater"])
            p_name_col_curr = find_col(df_curr, ["Player", "Name", "Skater"])

            if not p_name_col_base or not p_name_col_curr:
                st.error("Could not find 'Player' column in player CSVs.")
                st.stop()

            # Harmonize key columns
            df_base = df_base.rename(columns={p_name_col_base: "Player"})
            df_curr = df_curr.rename(columns={p_name_col_curr: "Player"})

            # Merge with suffixes
            merged_df = pd.merge(df_base, df_curr, on="Player", how="inner", suffixes=("_base", "_curr"))

            # Robust stat extraction
            target_candidates = ["Shots", "SOG", "iCF", "Shots on Goal"]
            
            # Helper to safely pull numeric values
            def get_stat_series(df, prefix_patterns):
                for pattern in prefix_patterns:
                    cols = [c for c in df.columns if pattern.lower() in c.lower()]
                    if cols:
                        return pd.to_numeric(df[cols[0]], errors="coerce").fillna(0)
                return pd.Series(0.0, index=df.index)

            # Get Baseline Stat
            base_stat = get_stat_series(merged_df, ["Shots_base", "SOG_base", "iCF_base", "Shots", "SOG"])
            # Get Current Stat
            curr_stat = get_stat_series(merged_df, ["Shots_curr", "SOG_curr", "iCF_curr", "Shots_y", "SOG_y"])
            
            # Games Played extraction
            gp_base = get_stat_series(merged_df, ["GP_base", "Games Played_base", "GP"])
            gp_curr = get_stat_series(merged_df, ["GP_curr", "Games Played_curr", "GP_y"])
            
            # Safe Division for Per-Game Baseline
            base_gp_safe = gp_base.replace(0, 82)
            curr_gp_safe = gp_curr.replace(0, 1)

            merged_df["Baseline_Stat"] = (base_stat / base_gp_safe).round(4)
            merged_df["Current_Stat"] = (curr_stat / curr_gp_safe).round(4)
            merged_df["GP_Curr"] = gp_curr

            # Apply GP filter
            merged_df = merged_df[merged_df["GP_Curr"] >= min_gp].copy()

            # Dynamic Phase Weight Blending
            w_curr = phase_weight
            w_base = 1.0 - w_curr
            merged_df["Blended_Rate"] = (w_base * merged_df["Baseline_Stat"] + w_curr * merged_df["Current_Stat"]).round(4)

            # Team resolution
            team_col = find_col(merged_df, ["Team_curr", "Team_base", "Team", "Clean_Team"])
            merged_df["Clean_Team"] = merged_df[team_col] if team_col else "NHL"
            
            # Default Matchup Factor & Opponent
            merged_df["Opponent"] = "@OPP"
            merged_df["Matchup_Factor"] = 1.0

            # Process Game / Matchup CSVs if available
            if game_files:
                try:
                    g_dfs = [read_csv_clean(f) for f in game_files]
                    gdf = g_dfs[0]
                    team_g_col = find_col(gdf, ["Team", "Clean_Team"])
                    ca_col = find_col(gdf, ["CA", "SA", "Shots Against", "Corsi Against"])
                    
                    if team_g_col and ca_col:
                        gdf["Def_Metric"] = pd.to_numeric(gdf[ca_col], errors="coerce").fillna(0)
                        mean_metric = gdf["Def_Metric"].mean()
                        if mean_metric > 0:
                            gdf["Factor"] = (gdf["Def_Metric"] / mean_metric).round(4)
                            factor_map = dict(zip(gdf[team_g_col], gdf["Factor"]))
                            # Apply matchup factor if match found
                            merged_df["Matchup_Factor"] = merged_df["Clean_Team"].map(factor_map).fillna(1.0)
                except Exception:
                    pass

            # Final Matchup Projection
            merged_df["Matchup_Proj"] = (merged_df["Blended_Rate"] * merged_df["Matchup_Factor"]).round(4)

            # Alt-Line Model Probabilities (Poisson)
            line_options = [1.5, 2.5, 3.5, 4.5]
            selected_line = st.selectbox("Select SOG Line Threshold", line_options, index=1)

            def calc_over_prob(mu, line):
                k = int(np.floor(line))
                prob_under_or_equal = poisson.cdf(k, mu)
                return round((1.0 - prob_under_or_equal) * 100, 1)

            def prob_to_american(prob):
                if prob <= 0:
                    return 9999
                if prob >= 100:
                    return -9999
                p = prob / 100.0
                if p >= 0.5:
                    return int(round(- (p / (1.0 - p)) * 100))
                else:
                    return int(round(((1.0 - p) / p) * 100))

            merged_df["Model_Over_Prob_%"] = merged_df["Matchup_Proj"].apply(lambda x: calc_over_prob(x, selected_line))
            merged_df["Fair_American_Odds"] = merged_df["Model_Over_Prob_%"].apply(prob_to_american)
            merged_df["Market"] = "Shots on Goal (SOG)"
            merged_df["Line"] = selected_line

            st.markdown(f"### 📈 Slate Alt-Line Matrix (Shots on Goal (SOG) > {selected_line}):")

            display_cols = [
                "Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_Stat",
                "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market"
            ]

            display_df = merged_df[display_cols].copy()
            display_df.insert(0, "Select", False)

            edited_df = st.data_editor(
                display_df,
                hide_index=True,
                use_container_width=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=True)}
            )

            # Add checked players to bet slip
            selected_rows = edited_df[edited_df["Select"] == True]
            if not selected_rows.empty:
                if st.button("➕ Add Selected to Odds Comparator Slip"):
                    for _, row in selected_rows.iterrows():
                        new_item = {
                            "Include in Parlay": True,
                            "Sportsbook": "FanDuel",
                            "Player": row["Player"],
                            "Opponent": row["Opponent"],
                            "Market": row["Market"],
                            "Line": selected_line,
                            "Nexus Odds (+/-)": 100,
                            "Model Prob (%)": row["Model_Over_Prob_%"],
                            "Delete": False
                        }
                        if not any(d["Player"] == new_item["Player"] for d in st.session_state["nhl_bet_slip"]):
                            st.session_state["nhl_bet_slip"].append(new_item)
                    st.success("Added to Checked Slips!")

        except Exception as e:
            st.error(f"Error processing files: {str(e)}")
    else:
        st.info("Please drop your 4 Natural Stat Trick CSVs above to populate the matrix.")

# -------------------------------------------------------------
# TAB 1: BET SLIP & ODDS COMPARATOR
# -------------------------------------------------------------
with tab1:
    st.subheader("📝 Checked Players & Nexus Odds Comparator")
    st.caption("Type your Nexus Odds in the table. Real-time edges and compound parlay odds calculate live below.")

    if st.button("🗑️ Clear Bet Slip"):
        st.session_state["nhl_bet_slip"] = []
        st.rerun()

    if st.session_state["nhl_bet_slip"]:
        slip_df = pd.DataFrame(st.session_state["nhl_bet_slip"])
        
        edited_slip = st.data_editor(
            slip_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Include in Parlay": st.column_config.CheckboxColumn(),
                "Delete": st.column_config.CheckboxColumn()
            }
        )

        # Handle deletes
        if edited_slip["Delete"].any():
            st.session_state["nhl_bet_slip"] = edited_slip[~edited_slip["Delete"]].to_dict(orient="records")
            st.rerun()

        st.session_state["nhl_bet_slip"] = edited_slip.to_dict(orient="records")

        # Edge Evaluation
        st.markdown("### 📈 Live Edge Evaluation:")
        edge_data = []

        def american_to_implied(odds):
            try:
                odds = float(odds)
                if odds > 0:
                    return 100.0 / (odds + 100.0)
                else:
                    return abs(odds) / (abs(odds) + 100.0)
            except:
                return 0.5

        parlay_mult = 1.0
        parlay_prob = 1.0
        active_legs = 0

        for row in st.session_state["nhl_bet_slip"]:
            odds = row.get("Nexus Odds (+/-)", 100)
            prob = row.get("Model Prob (%)", 50.0)
            implied = american_to_implied(odds) * 100.0
            edge = round(prob - implied, 1)

            edge_data.append({
                "Sportsbook": row.get("Sportsbook", "FanDuel"),
                "Player": row.get("Player", ""),
                "Opponent": row.get("Opponent", ""),
                "Market": row.get("Market", "SOG"),
                "Line": row.get("Line", 2.5),
                "Odds": odds,
                "Model Prob": f"{prob}%",
                "Edge %": f"+{edge}%" if edge > 0 else f"{edge}%"
            })

            if row.get("Include in Parlay", True):
                active_legs += 1
                try:
                    o = float(odds)
                    mult = (o / 100.0 + 1.0) if o > 0 else (100.0 / abs(o) + 1.0)
                except:
                    mult = 1.91
                parlay_mult *= mult
                parlay_prob *= (prob / 100.0)

        st.dataframe(pd.DataFrame(edge_data), hide_index=True, use_container_width=True)

        # Live Compound Slip Calculator
        st.markdown("### 🚀 Live Compound Slip & Profit Boost Calculator")
        c1, c2, c3, c4 = st.columns(4)

        if active_legs > 0:
            if parlay_mult >= 2.0:
                calc_parlay_odds = int(round((parlay_mult - 1.0) * 100))
                calc_parlay_str = f"+{calc_parlay_odds}"
            else:
                calc_parlay_odds = int(round(-100.0 / (parlay_mult - 1.0))) if parlay_mult > 1.0 else 100
                calc_parlay_str = f"{calc_parlay_odds}"

            boost_dec = (parlay_mult - 1.0) * (1.0 + profit_boost / 100.0) + 1.0
            boost_odds = int(round((boost_dec - 1.0) * 100)) if boost_dec >= 2.0 else int(round(-100.0 / (boost_dec - 1.0)))
            boost_str = f"+{boost_odds}" if boost_odds > 0 else f"{boost_odds}"

            true_prob_pct = round(parlay_prob * 100.0, 1)
            implied_base = (1.0 / parlay_mult) * 100.0
            compound_edge = round(true_prob_pct - implied_base, 1)

            c1.metric("Checked Parlay Odds", calc_parlay_str)
            c2.metric(f"Boosted (+{profit_boost}%)", boost_str)
            c3.metric("Model Slip True Prob", f"{true_prob_pct}%")
            c4.metric("Compound Slip Edge", f"+{compound_edge}%" if compound_edge > 0 else f"{compound_edge}%")
        else:
            c1.metric("Checked Parlay Odds", "None")
            c2.metric("Boosted", "None")
            c3.metric("Model Slip True Prob", "0.0%")
            c4.metric("Compound Slip Edge", "0.0%")
    else:
        st.info("Your bet slip is currently empty. Check players in Tab 2 to evaluate edges.")
