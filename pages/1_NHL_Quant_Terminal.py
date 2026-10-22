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
            # Categorize files
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

            # ---------------------------------------------------------
            # 1. PROCESS GAMES & SCHEDULE / OPPONENT MATCHUPS
            # ---------------------------------------------------------
            schedule_map = {} # Team -> Opponent display (e.g. '@OTT' or 'vs FLA')
            matchup_factors = {} # Team -> Opponent SA Factor
            game_matchup_options = []

            if game_files:
                try:
                    # Pick current season games file (often has 25-26 or larger row count)
                    g_dfs = [read_csv_clean(f) for f in game_files]
                    # Sort so current season is prioritized
                    gdf = g_dfs[0]
                    for g in g_dfs:
                        if "25-26" in getattr(g, 'name', '') or len(g) < 1500:
                            gdf = g
                            break

                    # Standardize column names
                    cols = {c.lower(): c for c in gdf.columns}
                    game_col = cols.get("game", cols.get("matchup", None))
                    team_col = cols.get("team", None)
                    ca_col = cols.get("ca", cols.get("sa", cols.get("shots against", None)))
                    date_col = cols.get("date", None)

                    if game_col and team_col:
                        # Extract games for the selected date if date column exists
                        target_str = slate_date.strftime("%Y-%m-%d")
                        if date_col and target_str in gdf[date_col].astype(str).values:
                            slate_games = gdf[gdf[date_col].astype(str) == target_str]
                        else:
                            # Fallback: take most recent games or all listed matchups
                            slate_games = gdf

                        for _, row in slate_games.iterrows():
                            g_str = str(row[game_col])
                            # Parse "FLA @ OTT" or "FLA - OTT"
                            if "@" in g_str:
                                parts = [p.strip() for p in g_str.split("@")]
                                if len(parts) == 2:
                                    away, home = parts[0], parts[1]
                                    schedule_map[away] = f"@{home}"
                                    schedule_map[home] = f"vs {away}"
                                    label = f"{away} @ {home}"
                                    if label not in game_matchup_options:
                                        game_matchup_options.append(label)
                            elif " - " in g_str:
                                parts = [p.strip() for p in g_str.split(" - ")]
                                if len(parts) == 2:
                                    t1, t2 = parts[0], parts[1]
                                    schedule_map[t1] = f"vs {t2}"
                                    schedule_map[t2] = f"@{t1}"
                                    label = f"{t1} vs {t2}"
                                    if label not in game_matchup_options:
                                        game_matchup_options.append(label)

                    # Calculate Defensive Shot Suppression / Allowance Factors
                    if team_col and ca_col:
                        team_def = gdf.groupby(team_col)[ca_col].apply(lambda s: pd.to_numeric(s, errors='coerce').mean()).dropna()
                        league_avg = team_def.mean()
                        if league_avg > 0:
                            for tm, val in team_def.items():
                                # Matchup factor is how many shots the OPPONENT allows relative to league average
                                matchup_factors[tm] = round(val / league_avg, 4)
                except Exception as ge:
                    st.warning(f"Note: Schedule/matchup parsing warning: {str(ge)}")

            # Matchup Multi-Select Filter
            selected_matchups = []
            if game_matchup_options:
                selected_matchups = st.multiselect(
                    "🎯 Filter Specific Game Matchups (Sorted by Combined Factor)",
                    options=game_matchup_options,
                    default=game_matchup_options[:1] if len(game_matchup_options) > 0 else []
                )

            # ---------------------------------------------------------
            # 2. PROCESS PLAYERS (BASELINE VS CURRENT)
            # ---------------------------------------------------------
            p_dfs = [read_csv_clean(f) for f in player_files]
            
            # Identify current vs prior: baseline has larger file / more rows (full 82 game season)
            if len(p_dfs) >= 2:
                if len(p_dfs[0]) > len(p_dfs[1]):
                    df_base, df_curr = p_dfs[0], p_dfs[1]
                else:
                    df_base, df_curr = p_dfs[1], p_dfs[0]
            else:
                df_base = p_dfs[0]
                df_curr = p_dfs[0].copy()

            def get_col(df, candidates):
                for c in candidates:
                    for col in df.columns:
                        if c.lower() == col.lower().strip():
                            return col
                return None

            base_p_col = get_col(df_base, ["Player", "Name"])
            curr_p_col = get_col(df_curr, ["Player", "Name"])

            if not base_p_col or not curr_p_col:
                st.error("Could not find 'Player' column in player CSVs.")
                st.stop()

            # Align Player & Team names
            df_base = df_base.rename(columns={base_p_col: "Player"})
            df_curr = df_curr.rename(columns={curr_p_col: "Player"})

            base_team_col = get_col(df_base, ["Team"])
            curr_team_col = get_col(df_curr, ["Team"])

            # Merge baseline & current
            merged = pd.merge(df_base, df_curr, on="Player", how="inner", suffixes=("_base", "_curr"))

            # Robust helper to extract SOG and GP
            def extract_stat_per_game(df, suffix):
                gp_col = get_col(df, [f"GP_{suffix}", f"Games Played_{suffix}", "GP"])
                sog_col = get_col(df, [f"Shots_{suffix}", f"SOG_{suffix}", f"Shots on Goal_{suffix}", "Shots", "SOG"])
                s60_col = get_col(df, [f"S/60_{suffix}", f"Shots/60_{suffix}"])
                toi_col = get_col(df, [f"TOI/GP_{suffix}", f"TOI_{suffix}"])

                gp = pd.to_numeric(df[gp_col], errors="coerce").fillna(1) if gp_col else pd.Series(1, index=df.index)
                
                # If Shots total exists, compute Shots / GP
                if sog_col:
                    shots = pd.to_numeric(df[sog_col], errors="coerce").fillna(0)
                    gp_safe = gp.replace(0, 1)
                    # If the numbers are already small rates (e.g. 2.5), don't divide by 82
                    if shots.mean() < 10:
                        per_game = shots
                    else:
                        per_game = shots / gp_safe
                    return per_game, gp
                elif s60_col and toi_col:
                    s60 = pd.to_numeric(df[s60_col], errors="coerce").fillna(0)
                    toi = pd.to_numeric(df[toi_col], errors="coerce").fillna(15)
                    return (s60 * (toi / 60.0)), gp
                return pd.Series(0.0, index=df.index), gp

            merged["Baseline_Stat"], merged["GP_Base"] = extract_stat_per_game(merged, "base")
            merged["Current_Stat"], merged["GP_Curr"] = extract_stat_per_game(merged, "curr")

            # Filter minimum GP
            merged = merged[merged["GP_Curr"] >= min_gp].copy()

            # Clean Team
            t_col = f"{curr_team_col}_curr" if f"{curr_team_col}_curr" in merged.columns else ("Team_curr" if "Team_curr" in merged.columns else "Team_base")
            merged["Clean_Team"] = merged[t_col].astype(str).str.strip() if t_col in merged.columns else "NHL"

            # Clean Team abbreviation mapping (e.g. T.B -> TBL)
            team_fixes = {"T.B": "TBL", "N.J": "NJD", "S.J": "SJS", "L.A": "LAK"}
            merged["Clean_Team"] = merged["Clean_Team"].replace(team_fixes)

            # Assign Opponent from Schedule Map
            merged["Opponent"] = merged["Clean_Team"].map(schedule_map).fillna("@OPP")

            # Assign Matchup Factor: look up the opponent's defensive suppression factor
            def get_opponent_factor(row):
                opp = str(row["Opponent"]).replace("@", "").replace("vs", "").strip()
                return matchup_factors.get(opp, 1.0)

            merged["Matchup_Factor"] = merged.apply(get_opponent_factor, axis=1)

            # Dynamic Phase Weighting
            w_curr = phase_weight
            w_base = 1.0 - w_curr
            merged["Blended_Rate"] = (w_base * merged["Baseline_Stat"] + w_curr * merged["Current_Stat"]).round(4)
            merged["Matchup_Proj"] = (merged["Blended_Rate"] * merged["Matchup_Factor"]).round(4)

            # Filter by selected game matchups if user selected any
            if selected_matchups:
                valid_teams = []
                for gm in selected_matchups:
                    for t in gm.replace("@", " ").replace("vs", " ").split():
                        valid_teams.append(t.strip())
                merged = merged[merged["Clean_Team"].isin(valid_teams)].copy()

            # Alt-Line Threshold
            selected_line = st.selectbox("Select SOG Line Threshold", [1.5, 2.5, 3.5, 4.5], index=1)

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

            merged["Model_Over_Prob_%"] = merged["Matchup_Proj"].apply(lambda x: calc_over_prob(x, selected_line))
            merged["Fair_American_Odds"] = merged["Model_Over_Prob_%"].apply(prob_to_american)
            merged["Market"] = "Shots on Goal (SOG)"

            # Sort descending by projection
            merged = merged.sort_values(by="Matchup_Proj", ascending=False).reset_index(drop=True)

            st.markdown(f"### 📈 Slate Alt-Line Matrix (Shots on Goal (SOG) > {selected_line}):")

            display_cols = [
                "Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_Stat",
                "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market"
            ]

            display_df = merged[display_cols].round(4).copy()
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
