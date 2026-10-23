import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from scipy.stats import poisson

st.set_page_config(page_title="NHL Quant Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("Dynamic Weighting, Multi-Market Prop Accumulators, and Compound Slip Evaluator")

# -------------------------------------------------------------
# PERSISTENT SESSION STATE INITIALIZATION
# -------------------------------------------------------------
if "nhl_bet_slip" not in st.session_state:
    st.session_state["nhl_bet_slip"] = []

if "nhl_sample_weight" not in st.session_state:
    st.session_state["nhl_sample_weight"] = 40  # Phase 2 (40%)

if "nhl_min_gp" not in st.session_state:
    st.session_state["nhl_min_gp"] = 3

if "nhl_profit_boost" not in st.session_state:
    st.session_state["nhl_profit_boost"] = 30

if "nhl_raw_p_base" not in st.session_state:
    st.session_state["nhl_raw_p_base"] = None

if "nhl_raw_p_curr" not in st.session_state:
    st.session_state["nhl_raw_p_curr"] = None

if "nhl_raw_t_base" not in st.session_state:
    st.session_state["nhl_raw_t_base"] = None

if "nhl_raw_t_curr" not in st.session_state:
    st.session_state["nhl_raw_t_curr"] = None

# -------------------------------------------------------------
# SIDEBAR CONFIGURATION (PERSISTENT VIA KEYS)
# -------------------------------------------------------------
st.sidebar.header("🏒 NHL Model Settings")

phase_weight = st.sidebar.slider(
    "Current Season Sample Weight (%)", 
    min_value=0, 
    max_value=100, 
    step=5,
    key="nhl_sample_weight",
    help="Phase 1 (1-5 GP): 20%, Phase 2 (6-12 GP): 40%, Phase 3 (13-20 GP): 70%, Phase 4 (20+ GP): 100%"
) / 100.0

min_gp = st.sidebar.slider(
    "Minimum Current Season GP Filter",
    min_value=1,
    max_value=15,
    step=1,
    key="nhl_min_gp"
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Market-Tailored Edge Filters")
profit_boost = st.sidebar.number_input(
    "Active Sportsbook Profit Boost (%)", 
    min_value=0, 
    max_value=100, 
    step=5,
    key="nhl_profit_boost"
)

tab1, tab2 = st.tabs(["📋 Checked Slips & Odds Comparator", "📁 Slate Matrix & Projections"])

# -------------------------------------------------------------
# ROBUST TEAM NORMALIZER (HANDLES PERIODS, DOTS & NICKNAMES)
# -------------------------------------------------------------
def normalize_team(raw_name):
    if not raw_name or pd.isna(raw_name):
        return "NHL"
    cleaned = str(raw_name).strip().upper()
    cleaned = re.sub(r'[^A-Z0-9\s]', '', cleaned)  # Strips periods & symbols (ST. -> ST)

    if "LOUIS" in cleaned or cleaned in ["STL", "ST LOUIS", "BLUES"]:
        return "STL"
    if "VEGAS" in cleaned or cleaned in ["VGK", "VEG", "GOLDEN KNIGHTS"]:
        return "VGK"
    if "TAMPA" in cleaned or cleaned in ["TBL", "TB", "LIGHTNING"]:
        return "TBL"
    if "FLORIDA" in cleaned or cleaned in ["FLA", "PANTHERS"]:
        return "FLA"
    if "SAN JOSE" in cleaned or cleaned in ["SJS", "SJ", "SHARKS"]:
        return "SJS"
    if "NEW JERSEY" in cleaned or cleaned in ["NJD", "NJ", "DEVILS"]:
        return "NJD"
    if "ISLANDERS" in cleaned or cleaned in ["NYI"]:
        return "NYI"
    if "RANGERS" in cleaned or cleaned in ["NYR"]:
        return "NYR"
    if "LOS ANGELES" in cleaned or cleaned in ["LAK", "LA", "KINGS"]:
        return "LAK"
    if "TORONTO" in cleaned or cleaned in ["TOR", "MAPLE LEAFS"]:
        return "TOR"
    if "MONTREAL" in cleaned or cleaned in ["MTL", "MON", "CANADIENS"]:
        return "MTL"
    if "OTTAWA" in cleaned or cleaned in ["OTT", "SENATORS"]:
        return "OTT"
    if "EDMONTON" in cleaned or cleaned in ["EDM", "OILERS"]:
        return "EDM"
    if "CALGARY" in cleaned or cleaned in ["CGY", "FLAMES"]:
        return "CGY"
    if "VANCOUVER" in cleaned or cleaned in ["VAN", "CANUCKS"]:
        return "VAN"
    if "WINNIPEG" in cleaned or cleaned in ["WPG", "JETS"]:
        return "WPG"
    if "COLORADO" in cleaned or cleaned in ["COL", "AVALANCHE"]:
        return "COL"
    if "DALLAS" in cleaned or cleaned in ["DAL", "STARS"]:
        return "DAL"
    if "BOSTON" in cleaned or cleaned in ["BOS", "BRUINS"]:
        return "BOS"
    if "CAROLINA" in cleaned or cleaned in ["CAR", "HURRICANES"]:
        return "CAR"
    if "CHICAGO" in cleaned or cleaned in ["CHI", "BLACKHAWKS"]:
        return "CHI"
    if "DETROIT" in cleaned or cleaned in ["DET", "RED WINGS"]:
        return "DET"
    if "MINNESOTA" in cleaned or cleaned in ["MIN", "WILD"]:
        return "MIN"
    if "NASHVILLE" in cleaned or cleaned in ["NSH", "PREDATORS"]:
        return "NSH"
    if "PHILADELPHIA" in cleaned or cleaned in ["PHI", "FLYERS"]:
        return "PHI"
    if "PITTSBURGH" in cleaned or cleaned in ["PIT", "PENGUINS"]:
        return "PIT"
    if "SEATTLE" in cleaned or cleaned in ["SEA", "KRAKEN"]:
        return "SEA"
    if "BUFFALO" in cleaned or cleaned in ["BUF", "SABRES"]:
        return "BUF"
    if "COLUMBUS" in cleaned or cleaned in ["CBJ", "BLUE JACKETS"]:
        return "CBJ"
    if "ANAHEIM" in cleaned or cleaned in ["ANA", "DUCKS"]:
        return "ANA"
    if "WASHINGTON" in cleaned or cleaned in ["WSH", "WAS", "CAPITALS"]:
        return "WSH"
    if "UTAH" in cleaned or cleaned in ["UTA", "ARI", "ARIZONA", "COYOTES"]:
        return "UTA"

    return cleaned[:3]

# -------------------------------------------------------------
# TAB 2: DATA INGESTION & MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Single Dropzone: Natural Stat Trick Ingestion")
    
    uploaded_files = st.file_uploader(
        "Drop all 4 Natural Stat Trick CSV files here", 
        type=["csv"], 
        accept_multiple_files=True,
        key="nhl_uploader"
    )

    def read_clean(f):
        f.seek(0)
        df = pd.read_csv(f)
        df.columns = df.columns.str.strip()
        return df

    # Ingest newly dropped files into persistent session state
    if uploaded_files and len(uploaded_files) >= 2:
        player_files = []
        team_files = []
        for f in uploaded_files:
            name_l = f.name.lower()
            if "game" in name_l or "team" in name_l:
                team_files.append(f)
            else:
                player_files.append(f)

        # 1. Player files: Prior baseline is larger (700-900+ rows) vs early-season (500-600 rows)
        if len(player_files) >= 2:
            p_dfs = [read_clean(f) for f in player_files]
            p_dfs_sorted = sorted(p_dfs, key=lambda d: len(d), reverse=True)
            st.session_state["nhl_raw_p_base"] = p_dfs_sorted[0]
            st.session_state["nhl_raw_p_curr"] = p_dfs_sorted[1]
        elif len(player_files) == 1:
            p_df = read_clean(player_files[0])
            if "25-26" in player_files[0].name:
                st.session_state["nhl_raw_p_base"] = p_df
            else:
                st.session_state["nhl_raw_p_curr"] = p_df

        # 2. Team files: Differentiate by filename keywords ('25-26') or file size
        if len(team_files) >= 2:
            t0 = read_clean(team_files[0])
            t1 = read_clean(team_files[1])
            if "25-26" in team_files[0].name.lower():
                st.session_state["nhl_raw_t_base"] = t0
                st.session_state["nhl_raw_t_curr"] = t1
            elif "25-26" in team_files[1].name.lower():
                st.session_state["nhl_raw_t_base"] = t1
                st.session_state["nhl_raw_t_curr"] = t0
            else:
                t_dfs_sorted = sorted([t0, t1], key=lambda d: len(d), reverse=True)
                st.session_state["nhl_raw_t_base"] = t_dfs_sorted[0]
                st.session_state["nhl_raw_t_curr"] = t_dfs_sorted[1]
        elif len(team_files) == 1:
            t_df = read_clean(team_files[0])
            if "25-26" in team_files[0].name.lower():
                st.session_state["nhl_raw_t_base"] = t_df
            else:
                st.session_state["nhl_raw_t_curr"] = t_df

    col_market, col_line = st.columns([1, 1])
    with col_market:
        selected_market = st.selectbox(
            "Select Target Prop Market",
            ["Shots on Goal (SOG)", "Player Points", "Anytime Goal Scorer", "Player Assists"],
            key="nhl_market_selector"
        )

    market_threshold_map = {
        "Shots on Goal (SOG)": [1.5, 2.5, 3.5, 4.5],
        "Player Points": [0.5, 1.5, 2.5],
        "Anytime Goal Scorer": [0.5],
        "Player Assists": [0.5, 1.5]
    }
    default_indices = {
        "Shots on Goal (SOG)": 1,
        "Player Points": 0,
        "Anytime Goal Scorer": 0,
        "Player Assists": 0
    }

    with col_line:
        threshold_options = market_threshold_map.get(selected_market, [0.5, 1.5, 2.5])
        selected_line = st.selectbox(
            "Select Target Threshold Line", 
            threshold_options, 
            index=default_indices.get(selected_market, 0),
            key=f"nhl_line_selector_{selected_market}"
        )

    slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"), key="nhl_slate_date")

    # 1. LIVE NHL SCHEDULE FETCH
    date_str = slate_date.strftime("%Y-%m-%d")
    schedule_pairs = []
    schedule_map = {}
    opponent_team_map = {}

    try:
        url = f"https://api-web.nhle.com/v1/schedule/{date_str}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            s_data = res.json()
            for day in s_data.get("gameWeek", []):
                if day.get("date") == date_str:
                    for g in day.get("games", []):
                        away = normalize_team(g.get("awayTeam", {}).get("abbrev"))
                        home = normalize_team(g.get("homeTeam", {}).get("abbrev"))
                        if away and home:
                            schedule_pairs.append((away, home))
                            schedule_map[away] = f"@{home}"
                            schedule_map[home] = f"vs {away}"
                            opponent_team_map[away] = home
                            opponent_team_map[home] = away
    except Exception:
        pass

    # Render matrix if session state contains cached tables
    if st.session_state["nhl_raw_p_curr"] is not None and st.session_state["nhl_raw_p_base"] is not None:
        try:
            df_t_base = st.session_state["nhl_raw_t_base"]
            df_t_curr = st.session_state["nhl_raw_t_curr"]

            # ---------------------------------------------------------
            # 2. DEFENSIVE MATCHUP WEIGHTING (PRIOR BASELINE + CURRENT)
            # ---------------------------------------------------------
            team_def_factors = {}
            if df_t_base is not None and df_t_curr is not None:
                try:
                    base_metric_col = "ga/60" if selected_market != "Shots on Goal (SOG)" else "sa/60"
                    curr_metric_col = "GA" if selected_market != "Shots on Goal (SOG)" else "SA"

                    rates_base = {}
                    for _, r in df_t_base.iterrows():
                        tm = normalize_team(r["Team"])
                        col = next((c for c in df_t_base.columns if c.lower() == base_metric_col or c.lower() in ["sa/60", "ca/60"]), None)
                        if col and pd.notna(r[col]):
                            rates_base[tm] = float(r[col])
                        else:
                            val = pd.to_numeric(r.get(curr_metric_col, r.get("SA", 0)), errors="coerce")
                            toi_val = pd.to_numeric(r.get("TOI", 60), errors="coerce")
                            if pd.notna(val) and pd.notna(toi_val) and toi_val > 0:
                                rates_base[tm] = (val / (toi_val / 60.0))

                    rates_curr = {}
                    for _, r in df_t_curr.iterrows():
                        tm = normalize_team(r["Team"])
                        val = pd.to_numeric(r.get(curr_metric_col, r.get("SA", 0)), errors="coerce")
                        toi_val = pd.to_numeric(r.get("TOI", 60), errors="coerce")
                        if pd.notna(val) and pd.notna(toi_val) and toi_val > 0:
                            rates_curr[tm] = (val / (toi_val / 60.0))

                    all_teams = set(list(rates_base.keys()) + list(rates_curr.keys()))
                    w_c = phase_weight
                    w_b = 1.0 - w_c

                    blended_rates = {}
                    for tm in all_teams:
                        rb = rates_base.get(tm, 28.5 if selected_market == "Shots on Goal (SOG)" else 2.9)
                        rc = rates_curr.get(tm, rb)
                        blended_rates[tm] = (w_b * rb) + (w_c * rc)

                    league_mean = np.mean(list(blended_rates.values())) if blended_rates else 1.0
                    for tm, val in blended_rates.items():
                        team_def_factors[tm] = round(val / league_mean, 4)

                except Exception as te:
                    st.warning(f"Team defense note: {str(te)}")

            # ---------------------------------------------------------
            # 3. SCHEDULE PILLS (PERSISTENT SELECTION ACROSS PROP MARKETS)
            # ---------------------------------------------------------
            game_pairs = []
            game_labels_display = {}

            for away, home in schedule_pairs:
                clean_pair = f"{away} @ {home}"
                game_pairs.append(clean_pair)

                away_factor = team_def_factors.get(away, 1.0)
                home_factor = team_def_factors.get(home, 1.0)
                combo = round(away_factor + home_factor, 2)
                icon = "🔥" if combo >= 2.05 else "⚡" if combo >= 1.95 else ""
                game_labels_display[clean_pair] = f"{clean_pair} [{combo} {icon}]".strip()

            sorted_clean_pairs = sorted(
                game_pairs, 
                key=lambda p: float(game_labels_display[p].split("[")[1].split()[0]), 
                reverse=True
            )

            state_pairs_key = f"nhl_active_pairs_{date_str}"
            if state_pairs_key not in st.session_state:
                st.session_state[state_pairs_key] = sorted_clean_pairs

            selected_matchups = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Pace Factor)",
                options=sorted_clean_pairs,
                default=st.session_state[state_pairs_key],
                format_func=lambda x: game_labels_display.get(x, x),
                key=f"nhl_pill_widget_{date_str}"
            )
            st.session_state[state_pairs_key] = selected_matchups

            # ---------------------------------------------------------
            # 4. SKATER STATS: MARKET EXTRACTION & BLENDING
            # ---------------------------------------------------------
            df_p_base = st.session_state["nhl_raw_p_base"].copy()
            df_p_curr = st.session_state["nhl_raw_p_curr"].copy()

            p_base_col = next((c for c in df_p_base.columns if c.strip().lower() in ["player", "name"]), None)
            p_curr_col = next((c for c in df_p_curr.columns if c.strip().lower() in ["player", "name"]), None)

            df_p_base = df_p_base.rename(columns={p_base_col: "Player"})
            df_p_curr = df_p_curr.rename(columns={p_curr_col: "Player"})

            if selected_market == "Shots on Goal (SOG)":
                base_rate_name = "Shots/60"
                curr_count_name = "Shots"
            elif selected_market == "Player Points":
                base_rate_name = "Total Points/60"
                curr_count_name = "Total Points"
            elif selected_market == "Anytime Goal Scorer":
                base_rate_name = "Goals/60"
                curr_count_name = "Goals"
            else:
                base_rate_name = "Total Assists/60"
                curr_count_name = "Total Assists"

            df_p_base["GP_Base"] = pd.to_numeric(df_p_base.get("GP", 82), errors="coerce").fillna(82)
            if base_rate_name in df_p_base.columns and "TOI/GP" in df_p_base.columns:
                r60 = pd.to_numeric(df_p_base[base_rate_name], errors="coerce").fillna(0)
                toi_gp = pd.to_numeric(df_p_base["TOI/GP"], errors="coerce").fillna(15)
                df_p_base["Baseline_Stat"] = (r60 * (toi_gp / 60.0)).round(4)
            else:
                raw_c = pd.to_numeric(df_p_base.get(curr_count_name, 0), errors="coerce").fillna(0)
                df_p_base["Baseline_Stat"] = (raw_c / df_p_base["GP_Base"].replace(0, 1)).round(4)

            df_p_curr["GP_Curr"] = pd.to_numeric(df_p_curr.get("GP", 1), errors="coerce").fillna(1)
            raw_curr = pd.to_numeric(df_p_curr.get(curr_count_name, 0), errors="coerce").fillna(0)
            df_p_curr["Current_Stat"] = (raw_curr / df_p_curr["GP_Curr"].replace(0, 1)).round(4)

            tm_curr_col = next((c for c in ["Team", "Clean_Team"] if c in df_p_curr.columns), "Team")
            df_p_curr["Clean_Team"] = df_p_curr[tm_curr_col].apply(normalize_team)

            merged = pd.merge(
                df_p_base[["Player", "Baseline_Stat", "GP_Base"]],
                df_p_curr[["Player", "Clean_Team", "Current_Stat", "GP_Curr"]],
                on="Player",
                how="inner"
            )

            merged["Baseline_Stat"] = np.where(merged["GP_Base"] < 10, merged["Current_Stat"], merged["Baseline_Stat"])
            merged = merged[merged["GP_Curr"] >= min_gp].copy()

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

            # STRICT SLATE FILTER: Only display skaters from selected active matchups
            active_teams = []
            target_selection = selected_matchups if selected_matchups else sorted_clean_pairs
            for pair_str in target_selection:
                parts = pair_str.split(" @ ")
                if len(parts) == 2:
                    active_teams.extend([parts[0].strip(), parts[1].strip()])

            merged = merged[merged["Clean_Team"].isin(active_teams)].copy()

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
            merged["Market"] = selected_market
            merged["Line"] = selected_line

            merged = merged.sort_values(by="Matchup_Proj", ascending=False).reset_index(drop=True)

            st.markdown(f"### 📈 Slate Alt-Line Matrix ({selected_market} > {selected_line}):")

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
                column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                key=f"nhl_matrix_editor_{selected_market}_{selected_line}_{date_str}"
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
                                "Nexus Odds (+/-)": None,
                                "Model Prob (%)": row["Model_Over_Prob_%"],
                                "Delete": False
                            }
                            if not any(d["Player"] == new_item["Player"] and d["Market"] == new_item["Market"] for d in st.session_state["nhl_bet_slip"]):
                                st.session_state["nhl_bet_slip"].append(new_item)
                        st.success(f"Added {len(selected_rows)} checked players to Tab 1!")
                    else:
                        st.warning("Please check at least one player in the matrix first.")

            with col_auto_btn:
                if st.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs", use_container_width=True):
                    scored_df = merged.copy()
                    scored_df["Auto_Score"] = scored_df["Matchup_Proj"] * scored_df["Matchup_Factor"]
                    top_candidates = scored_df.sort_values(by="Auto_Score", ascending=False).head(5)
                    
                    added_count = 0
                    for _, row in top_candidates.iterrows():
                        new_item = {
                            "Include in Parlay": True,
                            "Sportsbook": "FanDuel",
                            "Player": row["Player"],
                            "Opponent": row["Opponent"],
                            "Market": row["Market"],
                            "Line": row["Line"],
                            "Nexus Odds (+/-)": None,
                            "Model Prob (%)": row["Model_Over_Prob_%"],
                            "Delete": False
                        }
                        if not any(d["Player"] == new_item["Player"] and d["Market"] == new_item["Market"] for d in st.session_state["nhl_bet_slip"]):
                            st.session_state["nhl_bet_slip"].append(new_item)
                            added_count += 1
                    st.success(f"Auto-loaded top {added_count} matchup-weighted players into Tab 1!")

        except Exception as e:
            st.error(f"Error processing files: {str(e)}")
    else:
        st.info("Please drop your 4 Natural Stat Trick CSVs above to populate the matrix.")

# -------------------------------------------------------------
# TAB 1: BET SLIP & ODDS COMPARATOR
# -------------------------------------------------------------
with tab1:
    st.subheader("📝 Checked Players & Nexus Odds Comparator")
    st.caption("Select your Sportsbook and enter Nexus Odds. Real-time edges calculate automatically once entered.")

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
                "Sportsbook": st.column_config.SelectboxColumn(
                    "Sportsbook",
                    help="Select sportsbook offering this price",
                    options=[
                        "FanDuel",
                        "bet365",
                        "DraftKings",
                        "theScore Bet",
                        "BetMGM",
                        "BetRivers"
                    ],
                    required=True
                ),
                "Nexus Odds (+/-)": st.column_config.NumberColumn(
                    "Nexus Odds (+/-)",
                    help="Type American odds (e.g. -115 or +125)"
                ),
                "Delete": st.column_config.CheckboxColumn()
            },
            key="nhl_slip_editor"
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
                return None

        parlay_mult = 1.0
        parlay_prob = 1.0
        active_legs = 0

        for row in st.session_state["nhl_bet_slip"]:
            odds_val = row.get("Nexus Odds (+/-)")
            prob = row.get("Model Prob (%)", 50.0)
            
            if odds_val is not None and pd.notna(odds_val) and str(odds_val).strip() not in ["", "None"]:
                implied = american_to_implied(odds_val)
                if implied is not None:
                    implied_pct = implied * 100.0
                    edge = round(prob - implied_pct, 1)
                    edge_str = f"+{edge}%" if edge > 0 else f"{edge}%"
                    odds_display = f"+{int(odds_val)}" if float(odds_val) > 0 else f"{int(odds_val)}"

                    edge_data.append({
                        "Sportsbook": row.get("Sportsbook", "FanDuel"),
                        "Player": row.get("Player", ""),
                        "Opponent": row.get("Opponent", ""),
                        "Market": row.get("Market", "SOG"),
                        "Line": row.get("Line", 2.5),
                        "Odds": odds_display,
                        "Model Prob": f"{prob}%",
                        "Edge %": edge_str
                    })

                    if row.get("Include in Parlay", True):
                        active_legs += 1
                        o = float(odds_val)
                        mult = (o / 100.0 + 1.0) if o > 0 else (100.0 / abs(o) + 1.0)
                        parlay_mult *= mult
                        parlay_prob *= (prob / 100.0)

        if edge_data:
            st.dataframe(pd.DataFrame(edge_data), hide_index=True, use_container_width=True)
        else:
            st.info("Enter odds in the table above to calculate edges for your checked players.")

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
            c1.metric("Checked Parlay Odds", "Enter Odds")
            c2.metric("Boosted", "Enter Odds")
            c3.metric("Model Slip True Prob", "0.0%")
            c4.metric("Compound Slip Edge", "0.0%")
    else:
        st.info("Your bet slip is currently empty. Check players in Tab 2 to evaluate edges.")
