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

TEAM_ABBREV_MAP = {
    "ANA": "ANA", "BOS": "BOS", "BUF": "BUF", "CAR": "CAR", "CBJ": "CBJ",
    "CGY": "CGY", "CHI": "CHI", "COL": "COL", "DAL": "DAL", "DET": "DET",
    "EDM": "EDM", "FLA": "FLA", "L.A": "LAK", "LAK": "LAK", "MIN": "MIN",
    "MTL": "MTL", "MON": "MTL", "N.J": "NJD", "NJD": "NJD", "NSH": "NSH",
    "NYI": "NYI", "NYR": "NYR", "OTT": "OTT", "PHI": "PHI", "PIT": "PIT",
    "S.J": "SJS", "SJS": "SJS", "SEA": "SEA", "STL": "STL", "T.B": "TBL",
    "TBL": "TBL", "TOR": "TOR", "UTA": "UTA", "VAN": "VAN", "VGK": "VGK",
    "VEG": "VGK", "WPG": "WPG", "WSH": "WSH", "WAS": "WSH"
}

# -------------------------------------------------------------
# TAB 2: DATA INGESTION & MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Single Dropzone: Natural Stat Trick Ingestion")
    
    uploaded_files = st.file_uploader(
        "Drop all 4 Natural Stat Trick CSV files here (2 Player files, 2 Game/Team files)", 
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

    # 1. LIVE NHL SCHEDULE FOR TARGET DATE
    date_str = slate_date.strftime("%Y-%m-%d")
    schedule_pairs = []
    schedule_map = {}
    opponent_team_map = {}

    try:
        url = f"https://api-web.nhle.com/v1/schedule/{date_str}"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            s_data = res.json()
            for day in s_data.get("gameWeek", []):
                if day.get("date") == date_str:
                    for g in day.get("games", []):
                        away = TEAM_ABBREV_MAP.get(g.get("awayTeam", {}).get("abbrev"), g.get("awayTeam", {}).get("abbrev"))
                        home = TEAM_ABBREV_MAP.get(g.get("homeTeam", {}).get("abbrev"), g.get("homeTeam", {}).get("abbrev"))
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
                name_l = f.name.lower()
                if "game" in name_l or "team" in name_l:
                    game_files.append(f)
                else:
                    player_files.append(f)

            def read_clean(f):
                f.seek(0)
                df = pd.read_csv(f)
                df.columns = df.columns.str.strip()
                return df

            # ---------------------------------------------------------
            # 2. DEFENSIVE MATCHUP WEIGHTING FROM TEAM CSVs
            # ---------------------------------------------------------
            team_def_factors = {}
            if game_files:
                try:
                    g_dfs = [read_clean(f) for f in game_files]
                    g_base = min(g_dfs, key=len) if len(g_dfs) >= 2 else g_dfs[0]
                    g_curr = max(g_dfs, key=len) if len(g_dfs) >= 2 else g_dfs[0]

                    def calc_team_rates(df):
                        cols = {c.lower(): c for c in df.columns}
                        tm_col = cols.get("team", cols.get("clean_team", None))
                        ca_col = cols.get("ca", cols.get("sa", cols.get("shots against", cols.get("ca/60", None))))
                        gp_col = cols.get("gp", cols.get("games played", None))
                        if tm_col and ca_col:
                            df[tm_col] = df[tm_col].astype(str).map(lambda x: TEAM_ABBREV_MAP.get(x.strip(), x.strip()))
                            df["Metric"] = pd.to_numeric(df[ca_col], errors="coerce").fillna(0)
                            if gp_col:
                                df["GP_Val"] = pd.to_numeric(df[gp_col], errors="coerce").replace(0, 1)
                                return df.groupby(tm_col).apply(lambda d: (d["Metric"] / d["GP_Val"]).mean()).to_dict()
                            else:
                                return df.groupby(tm_col)["Metric"].mean().to_dict()
                        return {}

                    rates_base = calc_team_rates(g_base)
                    rates_curr = calc_team_rates(g_curr) if len(g_dfs) >= 2 else rates_base

                    all_teams = set(list(rates_base.keys()) + list(rates_curr.keys()))
                    w_c = phase_weight
                    w_b = 1.0 - w_c

                    blended_def = {}
                    for tm in all_teams:
                        rb = rates_base.get(tm, 30.0)
                        rc = rates_curr.get(tm, rb)
                        blended_def[tm] = (w_b * rb) + (w_c * rc)

                    league_mean = np.mean(list(blended_def.values())) if blended_def else 1.0
                    for tm, val in blended_def.items():
                        team_def_factors[tm] = round(val / league_mean, 4)
                except Exception:
                    pass

            # ---------------------------------------------------------
            # 3. SCHEDULE PILLS WITH COMBO PACE FACTORS
            # ---------------------------------------------------------
            game_options_dict = {}
            for away, home in schedule_pairs:
                away_factor = team_def_factors.get(away, 1.0)
                home_factor = team_def_factors.get(home, 1.0)
                combo = round(away_factor + home_factor, 2)
                icon = "🔥" if combo >= 2.05 else "⚡" if combo >= 1.95 else ""
                label = f"{away} @ {home} [{combo} {icon}]".strip()
                game_options_dict[label] = {
                    "away": away,
                    "home": home,
                    "factor": combo
                }

            sorted_labels = sorted(
                game_options_dict.keys(), 
                key=lambda x: game_options_dict[x]["factor"], 
                reverse=True
            )

            selected_matchups = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Pace Factor)",
                options=sorted_labels,
                default=sorted_labels
            )

            # ---------------------------------------------------------
            # 4. SKATER STATS & MATCHUP MULTIPLIER
            # ---------------------------------------------------------
            p_dfs = [read_clean(f) for f in player_files]

            f0_name = getattr(player_files[0], 'name', '').lower()
            if "25-26" in f0_name or "curr" in f0_name:
                df_curr, df_base = p_dfs[0], p_dfs[1]
            elif len(p_dfs) >= 2 and ("25-26" in getattr(player_files[1], 'name', '').lower() or "curr" in getattr(player_files[1], 'name', '').lower()):
                df_curr, df_base = p_dfs[1], p_dfs[0]
            else:
                df_base, df_curr = (p_dfs[0], p_dfs[1]) if len(p_dfs[0]) > len(p_dfs[1]) else (p_dfs[1], p_dfs[0])

            def find_col(df, candidates):
                for cand in candidates:
                    for col in df.columns:
                        if cand.lower() == col.lower().strip():
                            return col
                return None

            p_base_col = find_col(df_base, ["Player", "Name"])
            p_curr_col = find_col(df_curr, ["Player", "Name"])

            if not p_base_col or not p_curr_col:
                st.error("Could not find 'Player' column in CSV files.")
                st.stop()

            df_base = df_base.rename(columns={p_base_col: "Player"})
            df_curr = df_curr.rename(columns={p_curr_col: "Player"})

            merged = pd.merge(df_base, df_curr, on="Player", how="inner", suffixes=("_base", "_curr"))

            def get_player_rates(df, suffix):
                gp_c = find_col(df, [f"GP_{suffix}", f"Games Played_{suffix}", "GP"])
                sog_c = find_col(df, [f"Shots_{suffix}", f"SOG_{suffix}", f"Shots on Goal_{suffix}", "Shots", "SOG"])
                s60_c = find_col(df, [f"S/60_{suffix}", f"Shots/60_{suffix}"])
                toi_c = find_col(df, [f"TOI/GP_{suffix}", f"TOI_{suffix}"])

                gp = pd.to_numeric(df[gp_c], errors="coerce").fillna(1) if gp_c else pd.Series(1, index=df.index)
                gp_safe = gp.replace(0, 1)

                if sog_c:
                    sog_vals = pd.to_numeric(df[sog_c], errors="coerce").fillna(0)
                    per_game = (sog_vals / gp_safe) if sog_vals.mean() > 10 else sog_vals
                    return per_game.round(4), gp
                elif s60_c and toi_c:
                    s60 = pd.to_numeric(df[s60_c], errors="coerce").fillna(0)
                    toi = pd.to_numeric(df[toi_c], errors="coerce").fillna(15)
                    return (s60 * (toi / 60.0)).round(4), gp
                return pd.Series(0.0, index=df.index), gp

            merged["Baseline_Stat"], merged["GP_Base"] = get_player_rates(merged, "base")
            merged["Current_Stat"], merged["GP_Curr"] = get_player_rates(merged, "curr")

            merged = merged[merged["GP_Curr"] >= min_gp].copy()

            tm_col = find_col(merged, ["Team_curr", "Team", "Team_base", "Clean_Team"])
            merged["Clean_Team"] = merged[tm_col].astype(str).str.strip().map(lambda x: TEAM_ABBREV_MAP.get(x, x)) if tm_col else "NHL"

            merged["Opponent"] = merged["Clean_Team"].map(schedule_map).fillna("@OPP")

            def get_opp_factor(row):
                opp = opponent_team_map.get(row["Clean_Team"])
                if opp and opp in team_def_factors:
                    return team_def_factors[opp]
                return 1.0

            merged["Matchup_Factor"] = merged.apply(get_opp_factor, axis=1)

            w_curr = phase_weight
            w_base = 1.0 - w_curr
            merged["Blended_Rate"] = (w_base * merged["Baseline_Stat"] + w_curr * merged["Current_Stat"]).round(4)
            merged["Matchup_Proj"] = (merged["Blended_Rate"] * merged["Matchup_Factor"]).round(4)

            # Matchup filter
            if selected_matchups:
                active_teams = []
                for label in selected_matchups:
                    meta = game_options_dict.get(label)
                    if meta:
                        active_teams.extend([meta["away"], meta["home"]])
                merged = merged[merged["Clean_Team"].isin(active_teams)].copy()

            # Poisson Model Probabilities
            def calc_over_prob(mu, line):
                k = int(np.floor(line))
                return round((1.0 - poisson.cdf(k, mu)) * 100, 1)

            def prob_to_american(prob):
                if prob <= 0: return 9999
                if prob >= 100: return -9999
                p = prob / 100.0
                return int(round(- (p / (1.0 - p)) * 100)) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

            merged["Model_Over_Prob_%"] = merged["Matchup_Proj"].apply(lambda x: calc_over_prob(x, selected_line))
            merged["Fair_American_Odds"] = merged["Model_Over_Prob_%"].apply(prob_to_american)
            merged["Market"] = "Shots on Goal (SOG)"
            merged["Line"] = selected_line

            # Sort by Matchup_Proj descending so highest matchup-weighted players are on top
            merged = merged.sort_values(by="Matchup_Proj", ascending=False).reset_index(drop=True)

            st.markdown(f"### 📈 Slate Alt-Line Matrix (Shots on Goal (SOG) > {selected_line}):")

            display_cols = [
                "Player", "Clean_Team", "Opponent", "Baseline_Stat", "Current_Stat",
                "Matchup_Factor", "Matchup_Proj", "Model_Over_Prob_%", "Fair_American_Odds", "Market", "Line"
            ]

            display_df = merged[display_cols].copy()
            display_df.insert(0, "Select", False)

            edited_df = st.data_editor(
                display_df,
                hide_index=True,
                use_container_width=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=True)}
            )

            # ---------------------------------------------------------
            # 5. DUAL ACTION BUTTONS (ADD CHECKED & AUTO-FEED TOP MATCHUPS)
            # ---------------------------------------------------------
            col_add_btn, col_auto_btn = st.columns(2)

            with col_add_btn:
                if st.button("➕ Add Checked Players to Bet Slip", use_container_width=True):
                    selected_rows = edited_df[edited_df["Select"] == True]
                    if not selected_rows.empty:
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
                        st.success(f"Added {len(selected_rows)} checked players to Tab 1!")
                    else:
                        st.warning("Please check at least one player in the matrix first.")

            with col_auto_btn:
                if st.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs", use_container_width=True):
                    # Filter for positive matchup environments (Factor >= 1.0) and sort by Matchup_Proj
                    matchup_boosted = merged[merged["Matchup_Factor"] >= 0.98].sort_values(by="Matchup_Proj", ascending=False)
                    top_candidates = matchup_boosted.head(5) if len(matchup_boosted) >= 5 else merged.head(5)
                    
                    added_count = 0
                    for _, row in top_candidates.iterrows():
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
                            added_count += 1
                    st.success(f"Auto-loaded top {added_count} matchup-weighted skaters into Tab 1!")

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
