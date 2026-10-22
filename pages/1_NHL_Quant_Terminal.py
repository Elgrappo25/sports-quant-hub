import streamlit as st
import pandas as pd
import numpy as np
import requests
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
    help="Phase 1 (1-5 GP): 20%, Phase 2 (6-12 GP): 40%, Phase 3 (13-20 GP): 70%, Phase 4 (20+ GP): 100%"
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
    
    col_drop = st.container()
    with col_drop:
        uploaded_files = st.file_uploader(
            "Drop all 4 Natural Stat Trick CSV files here", 
            type=["csv"], 
            accept_multiple_files=True
        )

    if uploaded_files:
        st.session_state["nhl_uploaded_files"] = uploaded_files

    active_files = st.session_state.get("nhl_uploaded_files", None)

    col_target_date, col_target_line = st.columns([1, 1])
    with col_target_date:
        slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"))
    with col_target_line:
        selected_line = st.selectbox("Select Target Threshold Line", [1.5, 2.5, 3.5, 4.5], index=1)

    # ---------------------------------------------------------
    # 1. LIVE OFFICIAL NHL SCHEDULE FETCHER
    # ---------------------------------------------------------
    date_str = slate_date.strftime("%Y-%m-%d")
    schedule_pairs = []       # list of tuples: (away_abbr, home_abbr)
    schedule_map = {}         # Team -> "@OPP" or "vs OPP"
    opponent_team_map = {}    # Team -> OPP_TEAM

    try:
        url = f"https://api-web.nhle.com/v1/schedule/{date_str}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for day in data.get("gameWeek", []):
                if day.get("date") == date_str:
                    for g in day.get("games", []):
                        away = g.get("awayTeam", {}).get("abbrev")
                        home = g.get("homeTeam", {}).get("abbrev")
                        if away and home:
                            schedule_pairs.append((away, home))
                            schedule_map[away] = f"@{home}"
                            schedule_map[home] = f"vs {away}"
                            opponent_team_map[away] = home
                            opponent_team_map[home] = away
    except Exception:
        pass

    if active_files and len(active_files) >= 2:
        try:
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
            # 2. OPPONENT DEFENSIVE MATCHUP FACTORS (CA / SA per game)
            # ---------------------------------------------------------
            team_defense_factor = {}
            if game_files:
                try:
                    g_dfs = [read_csv_clean(f) for f in game_files]
                    # Use team/game file with team totals
                    gdf = max(g_dfs, key=len)
                    
                    team_col = next((c for c in gdf.columns if c.lower() in ["team", "clean_team"]), None)
                    ca_col = next((c for c in gdf.columns if c.lower() in ["ca", "sa", "shots against", "corsi against"]), None)
                    gp_col = next((c for c in gdf.columns if c.lower() in ["gp", "games played"]), None)

                    if team_col and ca_col:
                        gdf["Def_Metric"] = pd.to_numeric(gdf[ca_col], errors="coerce").fillna(0)
                        if gp_col:
                            gdf["GP_Num"] = pd.to_numeric(gdf[gp_col], errors="coerce").replace(0, 1)
                            team_rates = gdf.groupby(team_col).apply(lambda d: (d["Def_Metric"] / d["GP_Num"]).mean())
                        else:
                            team_rates = gdf.groupby(team_col)["Def_Metric"].mean()

                        league_mean_defense = team_rates.mean()
                        if league_mean_defense > 0:
                            for tm, rate in team_rates.items():
                                # Ratio of shots/attempts allowed vs league average
                                team_defense_factor[str(tm).strip()] = round(rate / league_mean_defense, 4)
                except Exception:
                    pass

            # Standard team abbreviation mapping
            abbrev_fixes = {
                "T.B": "TBL", "N.J": "NJD", "S.J": "SJS", "L.A": "LAK", 
                "MON": "MTL", "WAS": "WSH", "VEG": "VGK", "UTA": "UTA"
            }
            # Remap defense factor dict with standard codes
            cleaned_def_factors = {}
            for k, v in team_defense_factor.items():
                clean_k = abbrev_fixes.get(k, k)
                cleaned_def_factors[clean_k] = v

            # ---------------------------------------------------------
            # 3. BUILD NFL-STYLE SCHEDULE BUTTONS (COMBINED FACTOR)
            # ---------------------------------------------------------
            game_options_dict = {}
            for away, home in schedule_pairs:
                away_def = cleaned_def_factors.get(away, 1.0)
                home_def = cleaned_def_factors.get(home, 1.0)
                # Combined game factor (pace of both defensive environments)
                combined_factor = round(away_def + home_def, 2)
                icon = "🔥" if combined_factor >= 2.05 else "⚡" if combined_factor >= 1.95 else ""
                label = f"{away} @ {home} [{combined_factor} {icon}]".strip()
                game_options_dict[label] = {
                    "away": away,
                    "home": home,
                    "factor": combined_factor
                }

            # Sort games by combined pace descending (just like NFL)
            sorted_game_labels = sorted(
                game_options_dict.keys(), 
                key=lambda x: game_options_dict[x]["factor"], 
                reverse=True
            )

            # Multiselect with ALL games selected by default
            selected_matchups = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Combined Factor)",
                options=sorted_game_labels,
                default=sorted_game_labels
            )

            # ---------------------------------------------------------
            # 4. SKATER STAT PROCESSING & MATCHUP PROJECTIONS
            # ---------------------------------------------------------
            p_dfs = [read_csv_clean(f) for f in player_files]
            
            # Baseline (82-game) is the file with more rows
            if len(p_dfs) >= 2:
                if len(p_dfs[0]) > len(p_dfs[1]):
                    df_base, df_curr = p_dfs[0], p_dfs[1]
                else:
                    df_base, df_curr = p_dfs[1], p_dfs[0]
            else:
                df_base = p_dfs[0]
                df_curr = p_dfs[0].copy()

            def find_col(df, candidates):
                for c in candidates:
                    for col in df.columns:
                        if c.lower() == col.lower().strip():
                            return col
                return None

            base_p_col = find_col(df_base, ["Player", "Name"])
            curr_p_col = find_col(df_curr, ["Player", "Name"])

            if not base_p_col or not curr_p_col:
                st.error("Could not locate 'Player' column in player CSVs.")
                st.stop()

            df_base = df_base.rename(columns={base_p_col: "Player"})
            df_curr = df_curr.rename(columns={curr_p_col: "Player"})

            merged = pd.merge(df_base, df_curr, on="Player", how="inner", suffixes=("_base", "_curr"))

            def get_stat_and_gp(df, suffix):
                gp_col = find_col(df, [f"GP_{suffix}", f"Games Played_{suffix}", "GP"])
                sog_col = find_col(df, [f"Shots_{suffix}", f"SOG_{suffix}", f"Shots on Goal_{suffix}", "Shots", "SOG"])
                s60_col = find_col(df, [f"S/60_{suffix}", f"Shots/60_{suffix}"])
                toi_col = find_col(df, [f"TOI/GP_{suffix}", f"TOI_{suffix}"])

                gp = pd.to_numeric(df[gp_col], errors="coerce").fillna(1) if gp_col else pd.Series(1, index=df.index)

                if sog_col:
                    raw_sog = pd.to_numeric(df[sog_col], errors="coerce").fillna(0)
                    gp_safe = gp.replace(0, 1)
                    # If total counts (>15 mean), divide by GP; if already per game rate, keep
                    per_game = (raw_sog / gp_safe) if raw_sog.mean() > 10 else raw_sog
                    return per_game, gp
                elif s60_col and toi_col:
                    s60 = pd.to_numeric(df[s60_col], errors="coerce").fillna(0)
                    toi = pd.to_numeric(df[toi_col], errors="coerce").fillna(15)
                    return (s60 * (toi / 60.0)), gp
                return pd.Series(0.0, index=df.index), gp

            merged["Baseline_Stat"], merged["GP_Base"] = get_stat_and_gp(merged, "base")
            merged["Current_Stat"], merged["GP_Curr"] = get_stat_and_gp(merged, "curr")

            # Apply minimum GP filter
            merged = merged[merged["GP_Curr"] >= min_gp].copy()

            # Clean Team
            t_col = find_col(merged, ["Team_curr", "Team", "Team_base", "Clean_Team"])
            merged["Clean_Team"] = merged[t_col].astype(str).str.strip() if t_col else "NHL"
            merged["Clean_Team"] = merged["Clean_Team"].replace(abbrev_fixes)

            # Assign Real Opponent
            merged["Opponent"] = merged["Clean_Team"].map(schedule_map).fillna("@OPP")

            # Resolve individual matchup factor: Opponent's defensive shot allowance
            def get_individual_factor(row):
                team = row["Clean_Team"]
                opp = opponent_team_map.get(team, None)
                if opp and opp in cleaned_def_factors:
                    return cleaned_def_factors[opp]
                return 1.0

            merged["Matchup_Factor"] = merged.apply(get_individual_factor, axis=1)

            # Dynamic Phase Weighting
            w_curr = phase_weight
            w_base = 1.0 - w_curr
            merged["Blended_Rate"] = (w_base * merged["Baseline_Stat"] + w_curr * merged["Current_Stat"]).round(4)
            merged["Matchup_Proj"] = (merged["Blended_Rate"] * merged["Matchup_Factor"]).round(4)

            # Filter skaters belonging only to the selected matchup pill buttons
            if selected_matchups:
                active_teams = []
                for label in selected_matchups:
                    game_meta = game_options_dict.get(label)
                    if game_meta:
                        active_teams.extend([game_meta["away"], game_meta["home"]])
                merged = merged[merged["Clean_Team"].isin(active_teams)].copy()

            # Poisson Win Probabilities
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
            merged["Line"] = selected_line

            merged = merged.sort_values(by="Matchup_Proj", ascending=False).reset_index(drop=True)

            st.markdown(f"### 📈 Slate Alt-Line Matrix (Shots on Goal (SOG) > {selected_line}):")

            display_cols = [
                "Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_Stat",
                "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market", "Line"
            ]

            display_df = merged[display_cols].round(4).copy()
            display_df.insert(0, "Select", False)

            edited_df = st.data_editor(
                display_df,
                hide_index=True,
                use_container_width=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=True)}
            )

            # Add to bet slip
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
                            "Line": row["Line"],
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

        # Live Edge Evaluation
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

        # Compound Slip & Boost Calculator
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
