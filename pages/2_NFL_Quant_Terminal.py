import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from scipy.stats import poisson, norm

st.set_page_config(page_title="NFL Quant Terminal", page_icon="🏈", layout="wide")

st.title("🏈 NFL Quant Terminal: Production Suite")
st.markdown("Play-by-play data processing, schedule pace adjustments, matchup dampening, and alt-line prop accumulators.")

# -------------------------------------------------------------
# PERSISTENT SESSION STATE INITIALIZATION
# -------------------------------------------------------------
if "nfl_bet_slip" not in st.session_state:
    st.session_state["nfl_bet_slip"] = []

if "nfl_profit_boost" not in st.session_state:
    st.session_state["nfl_profit_boost"] = 30

if "nfl_min_gp" not in st.session_state:
    st.session_state["nfl_min_gp"] = 2

if "nfl_cached_tables" not in st.session_state:
    st.session_state["nfl_cached_tables"] = None

if "nfl_file_signature" not in st.session_state:
    st.session_state["nfl_file_signature"] = None

# Hardcoded model dampening (50% league baseline 1.0, 50% opponent rate)
PHASE_WEIGHT = 0.50

# -------------------------------------------------------------
# SIDEBAR CONFIGURATION (STREAMLINED & MINIMAL)
# -------------------------------------------------------------
st.sidebar.header("🏈 NFL Filters")
min_gp = st.sidebar.slider(
    "Minimum Games Played Filter",
    min_value=1,
    max_value=10,
    value=st.session_state["nfl_min_gp"],
    step=1,
    key="nfl_min_gp",
    help="Filters out players with fewer games played."
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Odds & Slip Filters")
profit_boost = st.sidebar.number_input(
    "Active Sportsbook Profit Boost (%)", 
    min_value=0, 
    max_value=100, 
    value=st.session_state["nfl_profit_boost"],
    step=5,
    key="nfl_profit_boost",
    help="Applied to compound parlays in Tab 1."
)

tab1, tab2 = st.tabs(["📋 Checked Slips & Odds Comparator", "📁 Slate Matrix & Projections"])

# -------------------------------------------------------------
# ROBUST TEAM NORMALIZER (HANDLES LA -> LAR & LAC ACCURATELY)
# -------------------------------------------------------------
def normalize_nfl_team(raw_name):
    if not raw_name or pd.isna(raw_name):
        return "NFL"
    cleaned = str(raw_name).strip().upper()
    cleaned = re.sub(r'[^A-Z0-9\s]', '', cleaned)

    # Explicit direct match priority to prevent LA/LAC overlap
    if cleaned in ["LAC", "CHARGERS", "LA CHARGERS", "SD"]:
        return "LAC"
    if cleaned in ["LA", "LAR", "RAMS", "LA RAMS", "STL"]:
        return "LAR"
    if cleaned in ["LV", "LVR", "RAIDERS", "OAK"]:
        return "LV"

    alias_map = {
        "ARI": ["ARI", "ARIZONA", "CARDINALS"],
        "ATL": ["ATL", "ATLANTA", "FALCONS"],
        "BAL": ["BAL", "BALTIMORE", "RAVENS"],
        "BUF": ["BUF", "BUFFALO", "BILLS"],
        "CAR": ["CAR", "CAROLINA", "PANTHERS"],
        "CHI": ["CHI", "CHICAGO", "BEARS"],
        "CIN": ["CIN", "CINCINNATI", "BENGALS"],
        "CLE": ["CLE", "CLEVELAND", "BROWNS"],
        "DAL": ["DAL", "DALLAS", "COWBOYS"],
        "DEN": ["DEN", "DENVER", "BRONCOS"],
        "DET": ["DET", "DETROIT", "LIONS"],
        "GB":  ["GB", "GNB", "GREEN BAY", "PACKERS"],
        "HOU": ["HOU", "HOUSTON", "TEXANS"],
        "IND": ["IND", "INDIANAPOLIS", "COLTS"],
        "JAX": ["JAX", "JAC", "JACKSONVILLE", "JAGUARS"],
        "KC":  ["KC", "KAN", "KANSAS CITY", "CHIEFS"],
        "LV":  ["LV", "LVR", "LAS VEGAS", "RAIDERS", "OAK"],
        "LAC": ["LAC", "LA CHARGERS", "CHARGERS", "SD"],
        "LAR": ["LAR", "LA", "LA RAMS", "RAMS"],
        "MIA": ["MIA", "MIAMI", "DOLPHINS"],
        "MIN": ["MIN", "MINNESOTA", "VIKINGS"],
        "NE":  ["NE", "NWE", "NEW ENGLAND", "PATRIOTS"],
        "NO":  ["NO", "NOR", "NEW ORLEANS", "SAINTS"],
        "NYG": ["NYG", "GIANTS", "NY GIANTS"],
        "NYJ": ["NYJ", "JETS", "NY JETS"],
        "PHI": ["PHI", "PHILADELPHIA", "EAGLES"],
        "PIT": ["PIT", "PITTSBURGH", "STEELERS"],
        "SF":  ["SF", "SFO", "SAN FRANCISCO", "49ERS"],
        "SEA": ["SEA", "SEATTLE", "SEAHAWKS"],
        "TB":  ["TB", "TAM", "TAMPA", "TAMPA BAY", "BUCCANEERS"],
        "TEN": ["TEN", "TENNESSEE", "TITANS"],
        "WAS": ["WAS", "WSH", "WASHINGTON", "COMMANDERS"]
    }
    for code, aliases in alias_map.items():
        if cleaned == code or any(cleaned == a for a in aliases) or any(a in cleaned for a in aliases):
            return code
    return cleaned[:3]

# -------------------------------------------------------------
# TAB 2: DATA INGESTION & MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Single Dropzone: NFL Savant Play-by-Play Ingestion")
    
    uploaded_file = st.file_uploader(
        "Drop your pbp-2026.csv file here", 
        type=["csv"], 
        key="nfl_uploader"
    )

    # FAST ONE-TIME PRE-COMPUTATION CACHE
    if uploaded_file is not None:
        file_sig = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("nfl_file_signature") != file_sig:
            with st.spinner("Processing play-by-play data..."):
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, low_memory=False)
                df["posteam"] = df["posteam"].apply(normalize_nfl_team)
                df["defteam"] = df["defteam"].apply(normalize_nfl_team)

                team_game_counts = df.groupby("posteam")["game_id"].nunique().to_dict()

                cached = {}
                # 1. Calculate All Defensive Factors with 50/50 Dampening
                def_factors = {}
                markets_list = ["Receiving Yards", "Receptions", "Anytime Touchdown", "Rushing Yards", "Passing Yards"]
                for m in markets_list:
                    if m in ["Receiving Yards", "Passing Yards"]:
                        d_stat = df[df["complete_pass"] == 1.0].groupby("defteam").agg(tot=("passing_yards", "sum"), g=("game_id", "nunique")).reset_index()
                    elif m == "Receptions":
                        d_stat = df[df["complete_pass"] == 1.0].groupby("defteam").agg(tot=("complete_pass", "count"), g=("game_id", "nunique")).reset_index()
                    elif m == "Rushing Yards":
                        d_stat = df[df["rushing_yards"].notna()].groupby("defteam").agg(tot=("rushing_yards", "sum"), g=("game_id", "nunique")).reset_index()
                    else:
                        d_stat = df[df["touchdown"] == 1.0].groupby("defteam").agg(tot=("touchdown", "count"), g=("game_id", "nunique")).reset_index()
                    
                    d_stat["rate"] = d_stat["tot"] / d_stat["g"].replace(0, 1)
                    m_mean = d_stat["rate"].mean() if not d_stat.empty else 1.0
                    d_stat["raw_f"] = d_stat["rate"] / m_mean
                    def_map = {}
                    for _, r in d_stat.iterrows():
                        def_map[r["defteam"]] = round(((1.0 - PHASE_WEIGHT) * 1.0) + (PHASE_WEIGHT * r["raw_f"]), 4)
                    def_factors[m] = def_map

                cached["def_factors"] = def_factors

                # 2. Vectorized Player Extraction Grouped by (Player, Clean_Team)
                # Receiving Yards
                rec_df = df[(df["complete_pass"] == 1.0) & df["receiver_player_name"].notna()]
                p_game_rec = rec_df.groupby(["receiver_player_name", "posteam", "game_id"])["receiving_yards"].sum().reset_index()
                m_rec_yds = p_game_rec.groupby(["receiver_player_name", "posteam"]).agg(
                    tot_stat=("receiving_yards", "sum"),
                    std_stat=("receiving_yards", "std")
                ).reset_index().rename(columns={"receiver_player_name": "Player", "posteam": "Clean_Team"})
                m_rec_yds["GP"] = m_rec_yds["Clean_Team"].map(team_game_counts).fillna(1)
                m_rec_yds["Baseline_Stat"] = (m_rec_yds["tot_stat"] / m_rec_yds["GP"]).round(1)
                m_rec_yds["Current_Stat"] = m_rec_yds["Baseline_Stat"]
                m_rec_yds["Std"] = m_rec_yds["std_stat"].fillna(15.0).clip(lower=5.0).round(1)
                cached["Receiving Yards"] = m_rec_yds

                # Receptions
                m_rec = rec_df.groupby(["receiver_player_name", "posteam"]).agg(
                    tot_stat=("complete_pass", "count")
                ).reset_index().rename(columns={"receiver_player_name": "Player", "posteam": "Clean_Team"})
                m_rec["GP"] = m_rec["Clean_Team"].map(team_game_counts).fillna(1)
                m_rec["Baseline_Stat"] = (m_rec["tot_stat"] / m_rec["GP"]).round(1)
                m_rec["Current_Stat"] = m_rec["Baseline_Stat"]
                m_rec["Std"] = None
                cached["Receptions"] = m_rec

                # Rushing Yards
                rush_df = df[df["rushing_yards"].notna() & df["rusher_player_name"].notna()]
                p_game_rush = rush_df.groupby(["rusher_player_name", "posteam", "game_id"])["rushing_yards"].sum().reset_index()
                m_rush = p_game_rush.groupby(["rusher_player_name", "posteam"]).agg(
                    tot_stat=("rushing_yards", "sum"),
                    std_stat=("rushing_yards", "std")
                ).reset_index().rename(columns={"rusher_player_name": "Player", "posteam": "Clean_Team"})
                m_rush["GP"] = m_rush["Clean_Team"].map(team_game_counts).fillna(1)
                m_rush["Baseline_Stat"] = (m_rush["tot_stat"] / m_rush["GP"]).round(1)
                m_rush["Current_Stat"] = m_rush["Baseline_Stat"]
                m_rush["Std"] = m_rush["std_stat"].fillna(15.0).clip(lower=5.0).round(1)
                cached["Rushing Yards"] = m_rush

                # Passing Yards
                pass_df = df[df["passing_yards"].notna() & df["passer_player_name"].notna()]
                p_game_pass = pass_df.groupby(["passer_player_name", "posteam", "game_id"])["passing_yards"].sum().reset_index()
                m_pass = p_game_pass.groupby(["passer_player_name", "posteam"]).agg(
                    tot_stat=("passing_yards", "sum"),
                    std_stat=("passing_yards", "std")
                ).reset_index().rename(columns={"passer_player_name": "Player", "posteam": "Clean_Team"})
                m_pass["GP"] = m_pass["Clean_Team"].map(team_game_counts).fillna(1)
                m_pass["Baseline_Stat"] = (m_pass["tot_stat"] / m_pass["GP"]).round(1)
                m_pass["Current_Stat"] = m_pass["Baseline_Stat"]
                m_pass["Std"] = m_pass["std_stat"].fillna(30.0).clip(lower=10.0).round(1)
                cached["Passing Yards"] = m_pass

                # Anytime Touchdown
                td_df = df[(df["touchdown"] == 1.0) & df["td_player_name"].notna()]
                m_td = td_df.groupby(["td_player_name", "posteam"]).agg(
                    tot_stat=("touchdown", "count")
                ).reset_index().rename(columns={"td_player_name": "Player", "posteam": "Clean_Team"})
                m_td["GP"] = m_td["Clean_Team"].map(team_game_counts).fillna(1)
                m_td["Baseline_Stat"] = (m_td["tot_stat"] / m_td["GP"]).round(2)
                m_td["Current_Stat"] = m_td["Baseline_Stat"]
                m_td["Std"] = None
                cached["Anytime Touchdown"] = m_td

                # Schedule fallback from CSV
                if "game_date" in df.columns:
                    cached["csv_schedule"] = df[["game_date", "away_team", "home_team"]].drop_duplicates()
                else:
                    cached["csv_schedule"] = pd.DataFrame()

                st.session_state["nfl_cached_tables"] = cached
                st.session_state["nfl_file_signature"] = file_sig

    col_market, col_line = st.columns([1, 1])
    with col_market:
        selected_market = st.selectbox(
            "Select Target Prop Market",
            ["Receiving Yards", "Receptions", "Anytime Touchdown", "Rushing Yards", "Passing Yards"],
            key="nfl_market_selector"
        )

    market_threshold_map = {
        "Receiving Yards": [24.5, 39.5, 49.5, 59.5, 69.5, 79.5, 89.5],
        "Receptions": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        "Anytime Touchdown": [0.5],
        "Rushing Yards": [24.5, 39.5, 49.5, 59.5, 69.5, 79.5, 89.5],
        "Passing Yards": [199.5, 224.5, 249.5, 274.5, 299.5]
    }
    default_indices = {
        "Receiving Yards": 0,
        "Receptions": 1,
        "Anytime Touchdown": 0,
        "Rushing Yards": 1,
        "Passing Yards": 1
    }

    with col_line:
        threshold_options = market_threshold_map.get(selected_market, [24.5, 39.5, 49.5])
        selected_line = st.selectbox(
            "Select Target Threshold Line", 
            threshold_options, 
            index=default_indices.get(selected_market, 0),
            key=f"nfl_line_selector_{selected_market}"
        )

    slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"), key="nfl_slate_date")

    # 1. LIVE SCHEDULE RESOLUTION
    date_str = slate_date.strftime("%Y-%m-%d")
    clean_date_num = date_str.replace("-", "")
    schedule_pairs = []
    schedule_map = {}
    opponent_team_map = {}

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={clean_date_num}"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            s_data = res.json()
            for ev in s_data.get("events", []):
                for comp in ev.get("competitions", []):
                    competitors = comp.get("competitors", [])
                    away_obj = next((c for c in competitors if c.get("homeAway") == "away"), None)
                    home_obj = next((c for c in competitors if c.get("homeAway") == "home"), None)
                    if away_obj and home_obj:
                        away = normalize_nfl_team(away_obj.get("team", {}).get("abbreviation"))
                        home = normalize_nfl_team(home_obj.get("team", {}).get("abbreviation"))
                        if away and home and (away, home) not in schedule_pairs:
                            schedule_pairs.append((away, home))
                            schedule_map[away] = f"@{home}"
                            schedule_map[home] = f"vs {away}"
                            opponent_team_map[away] = home
                            opponent_team_map[home] = away
    except Exception:
        pass

    # Schedule fallback from cached CSV
    if not schedule_pairs and st.session_state["nfl_cached_tables"] is not None:
        csv_sched = st.session_state["nfl_cached_tables"].get("csv_schedule", pd.DataFrame())
        if not csv_sched.empty and "game_date" in csv_sched.columns:
            matches = csv_sched[csv_sched["game_date"] == date_str]
            for _, r in matches.iterrows():
                away = normalize_nfl_team(r["away_team"])
                home = normalize_nfl_team(r["home_team"])
                if away and home and (away, home) not in schedule_pairs:
                    schedule_pairs.append((away, home))
                    schedule_map[away] = f"@{home}"
                    schedule_map[home] = f"vs {away}"
                    opponent_team_map[away] = home
                    opponent_team_map[home] = away

    # INSTANT MATRIX POPULATION
    if st.session_state["nfl_cached_tables"] is not None:
        try:
            cached = st.session_state["nfl_cached_tables"]
            team_def_factors = cached["def_factors"].get(selected_market, {})
            merged = cached.get(selected_market, pd.DataFrame()).copy()

            # Filter by Min Games Played from sidebar
            if not merged.empty:
                merged = merged[merged["GP"] >= min_gp].copy()

            # ---------------------------------------------------------
            # 3. SCHEDULE PILLS WITH COMBINED MATCHUP FACTOR
            # ---------------------------------------------------------
            game_pairs = []
            game_labels_display = {}

            for away, home in schedule_pairs:
                clean_pair = f"{away} @ {home}"
                game_pairs.append(clean_pair)

                away_factor = team_def_factors.get(away, 1.0)
                home_factor = team_def_factors.get(home, 1.0)
                combo = round(away_factor + home_factor, 2)
                icon = "🔥" if combo >= 2.10 else "⚡" if combo >= 2.00 else ""
                game_labels_display[clean_pair] = f"{clean_pair} [{combo} {icon}]".strip()

            sorted_clean_pairs = sorted(
                game_pairs, 
                key=lambda p: float(game_labels_display[p].split("[")[1].split()[0]), 
                reverse=True
            )

            saved_key = f"nfl_saved_pairs_{date_str}"
            init_flag_key = f"nfl_slate_init_{date_str}"
            widget_key = f"nfl_pairs_widget_{date_str}"

            if init_flag_key not in st.session_state:
                st.session_state[saved_key] = sorted_clean_pairs
                st.session_state[init_flag_key] = True

            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state.get(saved_key, sorted_clean_pairs)

            st.session_state[widget_key] = [p for p in st.session_state[widget_key] if p in sorted_clean_pairs]

            selected_matchups = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Combined Matchup Factor)",
                options=sorted_clean_pairs,
                format_func=lambda x: game_labels_display.get(x, x),
                key=widget_key
            )
            st.session_state[saved_key] = selected_matchups

            if not merged.empty:
                merged["Opponent"] = merged["Clean_Team"].map(schedule_map).fillna("@OPP")

                def get_opp_factor(row):
                    opp = opponent_team_map.get(row["Clean_Team"])
                    if opp and opp in team_def_factors:
                        return team_def_factors[opp]
                    return 1.0

                merged["Matchup_Factor"] = merged.apply(get_opp_factor, axis=1)
                merged["Matchup_Proj"] = (merged["Current_Stat"] * merged["Matchup_Factor"]).round(1)

                if not selected_matchups:
                    st.info("🎯 Select one or more game matchups above to populate the matrix.")
                else:
                    active_teams = []
                    for pair_str in selected_matchups:
                        parts = pair_str.split(" @ ")
                        if len(parts) == 2:
                            active_teams.extend([parts[0].strip(), parts[1].strip()])

                    merged = merged[merged["Clean_Team"].isin(active_teams)].copy()

                    # Exact distribution calculations: Normal for yardage, Poisson for counts
                    def calc_model_prob(row, line):
                        mu = row["Matchup_Proj"]
                        if selected_market in ["Receiving Yards", "Rushing Yards", "Passing Yards"]:
                            std_val = row.get("Std")
                            if pd.isna(std_val) or std_val is None or std_val <= 0:
                                std_val = max(mu * 0.4, 8.0)
                            prob = (1.0 - norm.cdf(line, loc=mu, scale=std_val)) * 100.0
                            return round(float(prob), 1)
                        else:
                            k = int(np.floor(line))
                            prob = (1.0 - poisson.cdf(k, mu)) * 100.0
                            return round(float(prob), 1)

                    def prob_to_american(prob):
                        if prob <= 0: return 9999
                        if prob >= 100: return -9999
                        p = prob / 100.0
                        return int(round(- (p / (1.0 - p)) * 100)) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

                    merged["Model_Over_Prob_%"] = merged.apply(lambda r: calc_model_prob(r, selected_line), axis=1)
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
                        key=f"nfl_matrix_editor_{selected_market}_{selected_line}_{date_str}"
                    )

                    # Action Buttons
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
                                    if not any(d["Player"] == new_item["Player"] and d["Market"] == new_item["Market"] for d in st.session_state["nfl_bet_slip"]):
                                        st.session_state["nfl_bet_slip"].append(new_item)
                                st.success(f"Added {len(selected_rows)} checked players to Tab 1!")
                            else:
                                st.warning("Please check at least one player in the matrix first.")

                    with col_auto_btn:
                        added_count = 0
                        if st.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs", use_container_width=True):
                            scored_df = merged.copy()
                            scored_df["Auto_Score"] = scored_df["Matchup_Proj"] * scored_df["Matchup_Factor"]
                            top_candidates = scored_df.sort_values(by="Auto_Score", ascending=False).head(5)
                            
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
                                if not any(d["Player"] == new_item["Player"] and d["Market"] == new_item["Market"] for d in st.session_state["nfl_bet_slip"]):
                                    st.session_state["nfl_bet_slip"].append(new_item)
                                    added_count += 1
                            st.success(f"Auto-loaded top {added_count} matchup-weighted players into Tab 1!")

            else:
                st.info("No player data available for this market.")

        except Exception as e:
            st.error(f"Error processing matrix: {str(e)}")
    else:
        st.info("Please drop your pbp-2026.csv file above to populate the matrix.")

# -------------------------------------------------------------
# TAB 1: BET SLIP & ODDS COMPARATOR
# -------------------------------------------------------------
with tab1:
    st.subheader("📝 Checked Players & Nexus Odds Comparator")
    st.caption("Select your Sportsbook and enter Nexus Odds. Real-time edges calculate automatically once entered.")

    if st.button("🗑️ Clear Bet Slip"):
        st.session_state["nfl_bet_slip"] = []
        st.rerun()

    if st.session_state["nfl_bet_slip"]:
        slip_df = pd.DataFrame(st.session_state["nfl_bet_slip"])
        
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
            key="nfl_slip_editor"
        )

        if edited_slip["Delete"].any():
            st.session_state["nfl_bet_slip"] = edited_slip[~edited_slip["Delete"]].to_dict(orient="records")
            st.rerun()

        st.session_state["nfl_bet_slip"] = edited_slip.to_dict(orient="records")

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

        for row in st.session_state["nfl_bet_slip"]:
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
                        "Market": row.get("Market", "Receiving Yards"),
                        "Line": row.get("Line", 24.5),
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
