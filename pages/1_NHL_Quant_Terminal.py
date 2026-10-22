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

# Universal Team Mapping for all 32 NHL franchises
NHL_TEAM_DICT = {
    "ANA": ["ANA", "ANAHEIM", "DUCKS", "ANAHEIM DUCKS"],
    "BOS": ["BOS", "BOSTON", "BRUINS", "BOSTON BRUINS"],
    "BUF": ["BUF", "BUFFALO", "SABRES", "BUFFALO SABRES"],
    "CAR": ["CAR", "CAROLINA", "HURRICANES", "CAROLINA HURRICANES"],
    "CBJ": ["CBJ", "COLUMBUS", "BLUE JACKETS", "COLUMBUS BLUE JACKETS"],
    "CGY": ["CGY", "CALGARY", "FLAMES", "CALGARY FLAMES"],
    "CHI": ["CHI", "CHICAGO", "BLACKHAWKS", "CHICAGO BLACKHAWKS"],
    "COL": ["COL", "COLORADO", "AVALANCHE", "COLORADO AVALANCHE"],
    "DAL": ["DAL", "DALLAS", "STARS", "DALLAS STARS"],
    "DET": ["DET", "DETROIT", "RED WINGS", "DETROIT RED WINGS"],
    "EDM": ["EDM", "EDMONTON", "OILERS", "EDMONTON OILERS"],
    "FLA": ["FLA", "FLORIDA", "PANTHERS", "FLORIDA PANTHERS"],
    "LAK": ["LAK", "L.A", "LOS ANGELES", "KINGS", "LOS ANGELES KINGS", "LA"],
    "MIN": ["MIN", "MINNESOTA", "WILD", "MINNESOTA WILD"],
    "MTL": ["MTL", "MON", "MONTREAL", "CANADIENS", "MONTREAL CANADIENS"],
    "NJD": ["NJD", "N.J", "NEW JERSEY", "DEVILS", "NEW JERSEY DEVILS", "NJ"],
    "NSH": ["NSH", "NASHVILLE", "PREDATORS", "NASHVILLE PREDATORS"],
    "NYI": ["NYI", "NEW YORK ISLANDERS", "ISLANDERS", "NY ISLANDERS"],
    "NYR": ["NYR", "NEW YORK RANGERS", "RANGERS", "NY RANGERS"],
    "OTT": ["OTT", "OTTAWA", "SENATORS", "OTTAWA SENATORS"],
    "PHI": ["PHI", "PHILADELPHIA", "FLYERS", "PHILADELPHIA FLYERS"],
    "PIT": ["PIT", "PITTSBURGH", "PENGUINS", "PITTSBURGH PENGUINS"],
    "SEA": ["SEA", "SEATTLE", "KRAKEN", "SEATTLE KRAKEN"],
    "SJS": ["SJS", "S.J", "SAN JOSE", "SHARKS", "SAN JOSE SHARKS", "SJ"],
    "STL": ["STL", "ST. LOUIS", "ST LOUIS", "BLUES", "ST. LOUIS BLUES"],
    "TBL": ["TBL", "T.B", "TAMPA BAY", "LIGHTNING", "TAMPA BAY LIGHTNING", "TB"],
    "TOR": ["TOR", "TORONTO", "MAPLE LEAFS", "TORONTO MAPLE LEAFS"],
    "UTA": ["UTA", "UTAH", "UTAH HOCKEY CLUB", "UTAH HC", "ARI", "ARIZONA", "COYOTES"],
    "VAN": ["VAN", "VANCOUVER", "CANUCKS", "VANCOUVER CANUCKS"],
    "VGK": ["VGK", "VEG", "VEGAS", "GOLDEN KNIGHTS", "VEGAS GOLDEN KNIGHTS"],
    "WPG": ["WPG", "WINNIPEG", "JETS", "WINNIPEG JETS"],
    "WSH": ["WSH", "WAS", "WASHINGTON", "CAPITALS", "WASHINGTON CAPITALS"]
}

CLEAN_TEAM_LOOKUP = {}
for code, aliases in NHL_TEAM_DICT.items():
    CLEAN_TEAM_LOOKUP[code.upper()] = code
    for alias in aliases:
        CLEAN_TEAM_LOOKUP[alias.upper()] = code

def normalize_team(raw_name):
    if not raw_name or pd.isna(raw_name):
        return "NHL"
    cleaned = str(raw_name).strip().upper()
    return CLEAN_TEAM_LOOKUP.get(cleaned, cleaned[:3])

# -------------------------------------------------------------
# TAB 2: DATA INGESTION & MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Single Dropzone: Natural Stat Trick Ingestion")
    
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

    if active_files and len(active_files) >= 2:
        try:
            player_files = []
            team_files = []
            for f in active_files:
                name_l = f.name.lower()
                if "game" in name_l or "team" in name_l:
                    team_files.append(f)
                else:
                    player_files.append(f)

            def read_clean(f):
                f.seek(0)
                df = pd.read_csv(f)
                df.columns = df.columns.str.strip()
                return df

            # ---------------------------------------------------------
            # 2. DEFENSIVE MATCHUP WEIGHTING (PRIOR BASELINE + CURRENT)
            # ---------------------------------------------------------
            team_def_factors = {}
            if team_files:
                try:
                    t_dfs = [read_clean(f) for f in team_files]
                    
                    # games 25-26.csv has SA/60 (Baseline 82 games)
                    # games.csv has SA and TOI counts (Current season)
                    df_t_base = None
                    df_t_curr = None
                    for t_df in t_dfs:
                        if "sa/60" in [c.lower() for c in t_df.columns]:
                            df_t_base = t_df
                        else:
                            df_t_curr = t_df

                    if df_t_base is None: df_t_base = t_dfs[0]
                    if df_t_curr is None: df_t_curr = t_dfs[-1]

                    rates_base = {}
                    for _, r in df_t_base.iterrows():
                        tm = normalize_team(r["Team"])
                        sa_col = next((c for c in df_t_base.columns if c.lower() in ["sa/60", "ca/60", "sa"]), None)
                        if sa_col and pd.notna(r[sa_col]):
                            rates_base[tm] = float(r[sa_col])

                    rates_curr = {}
                    for _, r in df_t_curr.iterrows():
                        tm = normalize_team(r["Team"])
                        sa_val = pd.to_numeric(r.get("SA", r.get("CA", 0)), errors="coerce")
                        toi_val = pd.to_numeric(r.get("TOI", 60), errors="coerce")
                        if pd.notna(sa_val) and pd.notna(toi_val) and toi_val > 0:
                            # Convert count to rate per 60
                            rates_curr[tm] = (sa_val / (toi_val / 60.0))

                    all_teams = set(list(rates_base.keys()) + list(rates_curr.keys()))
                    w_c = phase_weight
                    w_b = 1.0 - w_c

                    blended_rates = {}
                    for tm in all_teams:
                        rb = rates_base.get(tm, 28.5)
                        rc = rates_curr.get(tm, rb)
                        blended_rates[tm] = (w_b * rb) + (w_c * rc)

                    league_mean = np.mean(list(blended_rates.values())) if blended_rates else 28.5
                    for tm, val in blended_rates.items():
                        team_def_factors[tm] = round(val / league_mean, 4)

                except Exception as te:
                    st.warning(f"Team defense note: {str(te)}")

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
            # 4. SKATER STATS: PRECISE RATE & COUNT SEPARATION
            # ---------------------------------------------------------
            p_dfs = [read_clean(f) for f in player_files]

            # Player Season Totals - Natural Stat Trick 25-26.csv has "Shots/60" and "TOI/GP" (Baseline)
            # Player Season Totals - Natural Stat Trick.csv has "Shots" and "GP" (Current Season)
            df_p_base = None
            df_p_curr = None
            for p_df in p_dfs:
                if "shots/60" in [c.lower() for c in p_df.columns]:
                    df_p_base = p_df
                else:
                    df_p_curr = p_df

            if df_p_base is None: df_p_base = p_dfs[0]
            if df_p_curr is None: df_p_curr = p_dfs[-1]

            # Standardize Player & Team Columns
            p_base_col = next((c for c in df_p_base.columns if c.strip().lower() in ["player", "name"]), None)
            p_curr_col = next((c for c in df_p_curr.columns if c.strip().lower() in ["player", "name"]), None)

            df_p_base = df_p_base.rename(columns={p_base_col: "Player"})
            df_p_curr = df_p_curr.rename(columns={p_curr_col: "Player"})

            # Calculate True Baseline SOG/game: (Shots/60) * (TOI/GP / 60)
            df_p_base["GP_Base"] = pd.to_numeric(df_p_base.get("GP", 82), errors="coerce").fillna(82)
            if "Shots/60" in df_p_base.columns and "TOI/GP" in df_p_base.columns:
                s60 = pd.to_numeric(df_p_base["Shots/60"], errors="coerce").fillna(0)
                toi_gp = pd.to_numeric(df_p_base["TOI/GP"], errors="coerce").fillna(15)
                df_p_base["Baseline_Stat"] = (s60 * (toi_gp / 60.0)).round(4)
            else:
                shots_raw = pd.to_numeric(df_p_base.get("Shots", 0), errors="coerce").fillna(0)
                df_p_base["Baseline_Stat"] = (shots_raw / df_p_base["GP_Base"].replace(0, 1)).round(4)

            # Calculate True Current Season SOG/game: Shots / GP
            df_p_curr["GP_Curr"] = pd.to_numeric(df_p_curr.get("GP", 1), errors="coerce").fillna(1)
            shots_curr_raw = pd.to_numeric(df_p_curr.get("Shots", 0), errors="coerce").fillna(0)
            df_p_curr["Current_Stat"] = (shots_curr_raw / df_p_curr["GP_Curr"].replace(0, 1)).round(4)

            # Team Column
            tm_base_col = next((c for c in ["Team", "Clean_Team"] if c in df_p_base.columns), "Team")
            tm_curr_col = next((c for c in ["Team", "Clean_Team"] if c in df_p_curr.columns), "Team")
            df_p_base["Clean_Team"] = df_p_base[tm_base_col].apply(normalize_team)
            df_p_curr["Clean_Team"] = df_p_curr[tm_curr_col].apply(normalize_team)

            # Merge on Player
            merged = pd.merge(
                df_p_base[["Player", "Baseline_Stat", "GP_Base"]],
                df_p_curr[["Player", "Clean_Team", "Current_Stat", "GP_Curr"]],
                on="Player",
                how="inner"
            )

            # Outlier protection: If player had < 10 GP in baseline, use current season stat
            merged["Baseline_Stat"] = np.where(merged["GP_Base"] < 10, merged["Current_Stat"], merged["Baseline_Stat"])

            # Filter minimum current season GP
            merged = merged[merged["GP_Curr"] >= min_gp].copy()

            # Assign Opponent from Schedule Map
            merged["Opponent"] = merged["Clean_Team"].map(schedule_map).fillna("@OPP")

            # Matchup Factor: Opponent defense multiplier
            def get_opp_factor(row):
                opp = opponent_team_map.get(row["Clean_Team"])
                if opp and opp in team_def_factors:
                    return team_def_factors[opp]
                return 1.0

            merged["Matchup_Factor"] = merged.apply(get_opp_factor, axis=1)

            # Dynamic Phase Weighting
            w_curr = phase_weight
            w_base = 1.0 - w_curr
            merged["Blended_Rate"] = (w_base * merged["Baseline_Stat"] + w_curr * merged["Current_Stat"]).round(4)
            merged["Matchup_Proj"] = (merged["Blended_Rate"] * merged["Matchup_Factor"]).round(4)

            # Filter by Selected Game Matchups
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

            # Sort descending by Matchup_Proj
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
                                "Nexus Odds (+/-)": None,
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
                    help="Select the book offering this line",
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
                return None

        parlay_mult = 1.0
        parlay_prob = 1.0
        active_legs = 0

        for row in st.session_state["nhl_bet_slip"]:
            odds_val = row.get("Nexus Odds (+/-)")
            prob = row.get("Model Prob (%)", 50.0)
            
            if odds_val is not None and pd.notna(odds_val) and odds_val != "":
                implied = american_to_implied(odds_val)
                if implied is not None:
                    implied_pct = implied * 100.0
                    edge = round(prob - implied_pct, 1)
                    edge_str = f"+{edge}%" if edge > 0 else f"{edge}%"
                    odds_display = f"+{int(odds_val)}" if float(odds_val) > 0 else f"{int(odds_val)}"

                    if row.get("Include in Parlay", True):
                        active_legs += 1
                        o = float(odds_val)
                        mult = (o / 100.0 + 1.0) if o > 0 else (100.0 / abs(o) + 1.0)
                        parlay_mult *= mult
                        parlay_prob *= (prob / 100.0)
                else:
                    edge_str = "Enter Odds"
                    odds_display = "None"
            else:
                edge_str = "Enter Odds"
                odds_display = "None"

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
            c1.metric("Checked Parlay Odds", "Enter Odds")
            c2.metric("Boosted", "Enter Odds")
            c3.metric("Model Slip True Prob", "0.0%")
            c4.metric("Compound Slip Edge", "0.0%")
    else:
        st.info("Your bet slip is currently empty. Check players in Tab 2 to evaluate edges.")
