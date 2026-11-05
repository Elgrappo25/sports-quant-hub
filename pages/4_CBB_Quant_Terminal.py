import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from scipy.stats import norm

st.set_page_config(page_title="CBB Quant Terminal", page_icon="🏀", layout="wide")

st.title("🏀 CBB Quant Terminal: Production Suite")
st.markdown("KenPom Possession Efficiency, Live Main-Market Deviations, and Compound Slip Evaluator")

# -------------------------------------------------------------
# PERSISTENT SESSION STATE INITIALIZATION
# -------------------------------------------------------------
if "cbb_bet_slip" not in st.session_state:
    st.session_state["cbb_bet_slip"] = []

if "cbb_raw_kp" not in st.session_state:
    st.session_state["cbb_raw_kp"] = None

if "cbb_hca" not in st.session_state:
    st.session_state["cbb_hca"] = 3.2

if "cbb_profit_boost" not in st.session_state:
    st.session_state["cbb_profit_boost"] = 30

if "cbb_odds_cache" not in st.session_state:
    st.session_state["cbb_odds_cache"] = None

if "cbb_last_fetch_time" not in st.session_state:
    st.session_state["cbb_last_fetch_time"] = None

if "cbb_credits_left" not in st.session_state:
    st.session_state["cbb_credits_left"] = None

# -------------------------------------------------------------
# SIDEBAR CONFIGURATION
# -------------------------------------------------------------
st.sidebar.header("🏀 CBB Model Settings")

hca_val = st.sidebar.slider(
    "Standard Home-Court Advantage (Pts)",
    min_value=0.0,
    max_value=6.0,
    value=float(st.session_state["cbb_hca"]),
    step=0.1,
    key="cbb_hca",
    help="D1 national average is ~3.2 pts. High elevation venues (Utah St, Wyoming) can reach 4.5+."
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Market-Tailored Edge Filters")
profit_boost = st.sidebar.number_input(
    "Active Sportsbook Profit Boost (%)",
    min_value=0,
    max_value=100,
    step=5,
    key="cbb_profit_boost"
)

st.sidebar.markdown("---")
st.sidebar.header("📡 The Odds API (Optional Sync)")
default_api_key = st.secrets.get("ODDS_API_KEY", "") if hasattr(st, "secrets") else ""
api_key_input = st.sidebar.text_input("API Key", value=default_api_key, type="password", key="cbb_api_key")

if st.sidebar.button("🔄 Sync CBB Odds (Costs 2 Credits)", use_container_width=True):
    if not api_key_input:
        st.sidebar.error("Enter a valid Odds API Key first.")
    else:
        with st.sidebar.status("Querying Division 1 Board..."):
            url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
            params = {
                "apiKey": api_key_input,
                "regions": "us",
                "markets": "h2h,spreads",
                "oddsFormat": "american"
            }
            try:
                res = requests.get(url, params=params, timeout=10)
                if res.status_code == 200:
                    st.session_state["cbb_odds_cache"] = res.json()
                    st.session_state["cbb_last_fetch_time"] = pd.Timestamp.now().strftime("%I:%M %p")
                    rem = res.headers.get("x-requests-remaining", "N/A")
                    st.session_state["cbb_credits_left"] = f"{rem} / 500"
                    st.sidebar.success(f"Synced {len(st.session_state['cbb_odds_cache'])} live games!")
                else:
                    st.sidebar.error(f"Error {res.status_code}: {res.text}")
            except Exception as e:
                st.sidebar.error(f"Sync failed: {e}")

if st.session_state["cbb_last_fetch_time"]:
    st.sidebar.caption(f"🕒 Odds Updated: **{st.session_state['cbb_last_fetch_time']}**")
if st.session_state["cbb_credits_left"]:
    st.sidebar.caption(f"💳 Monthly Credits Remaining: **{st.session_state['cbb_credits_left']}**")

tab1, tab2 = st.tabs(["📋 Checked Slips & Odds Comparator", "📁 Slate Matrix & Projections"])

# -------------------------------------------------------------
# TEAM NAME RESOLVER (ESPN SCOREBOARD TO KENPOM STANDARDS)
# -------------------------------------------------------------
KENPOM_ALIASES = {
    "UCONN": "CONNECTICUT",
    "OLE MISS": "MISSISSIPPI",
    "NC STATE": "N.C. STATE",
    "MIAMI": "MIAMI FL",
    "ST. JOHN'S": "ST. JOHN'S",
    "PENN": "PENNSYLVANIA",
    "PITT": "PITTSBURGH",
    "USC": "USC",
    "LSU": "LSU",
    "SMU": "SMU",
    "BYU": "BYU",
    "TCU": "TCU",
    "UCF": "UCF",
    "UTEP": "UTEP",
    "UTSA": "UTSA",
    "VCU": "VCU",
    "UNLV": "UNLV",
    "UMASS": "MASSACHUSETTS"
}

def clean_str(s):
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())

def resolve_team(espn_name, kp_teams_dict):
    cleaned = clean_str(espn_name)
    if cleaned in kp_teams_dict:
        return kp_teams_dict[cleaned]
    if espn_name.upper() in KENPOM_ALIASES:
        alias_clean = clean_str(KENPOM_ALIASES[espn_name.upper()])
        if alias_clean in kp_teams_dict:
            return kp_teams_dict[alias_clean]
    for k_clean, orig in kp_teams_dict.items():
        if cleaned in k_clean or k_clean in cleaned:
            return orig
    return espn_name

# -------------------------------------------------------------
# TAB 2: MANUAL CSV INGESTION, SLATE FETCH & PROJECTION MATRIX
# -------------------------------------------------------------
with tab2:
    st.subheader("Single Dropzone: KenPom Ingestion")

    uploaded_kp = st.file_uploader(
        "Drop KenPom summary27.csv file here",
        type=["csv"],
        key="cbb_uploader"
    )

    if uploaded_kp is not None:
        try:
            uploaded_kp.seek(0)
            raw_df = pd.read_csv(uploaded_kp)
            raw_df.columns = raw_df.columns.str.strip()
            st.session_state["cbb_raw_kp"] = raw_df
        except Exception as e:
            st.error(f"Error reading file: {e}")

    # Render matrix only once session state contains the uploaded file
    if st.session_state["cbb_raw_kp"] is not None:
        kp_df = st.session_state["cbb_raw_kp"].copy()
        kp_dict = {clean_str(t): t for t in kp_df["TeamName"].unique()}

        col_market, col_view = st.columns([1, 1])
        with col_market:
            selected_market = st.selectbox(
                "Target Main Market Selection",
                ["Spread (Cover)", "Moneyline (Win)", "Game Total (Over)"],
                key="cbb_market_selector"
            )
        with col_view:
            st.metric("Division 1 Teams Tracked", len(kp_df))

        slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"), key="cbb_slate_date")
        date_str = slate_date.strftime("%Y%m%d")

        # ---------------------------------------------------------
        # 1. LIVE NCAA D1 SCHEDULE FETCH (ESPN SCOREBOARD)
        # ---------------------------------------------------------
        schedule_events = []
        schedule_labels = {}

        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}&groups=50&limit=400"
            res = requests.get(url, timeout=7).json()
            for event in res.get("events", []):
                comp = event["competitions"][0]
                competitors = comp["competitors"]
                home_raw = competitors[0]["team"]["shortDisplayName"]
                away_raw = competitors[1]["team"]["shortDisplayName"]
                neutral = comp.get("neutralSite", False)

                home_kp = resolve_team(home_raw, kp_dict)
                away_kp = resolve_team(away_raw, kp_dict)

                tag = f"{away_kp} vs {home_kp}" if neutral else f"{away_kp} @ {home_kp}"
                schedule_events.append({
                    "tag": tag,
                    "away": away_kp,
                    "home": home_kp,
                    "neutral": neutral
                })
        except Exception as e:
            st.warning(f"Live schedule fetch note: {str(e)}")

        # ---------------------------------------------------------
        # 2. MATCHUP EFFICIENCY & SPREAD PROJECTIONS
        # ---------------------------------------------------------
        D1_AVG_TEMPO = 71.37
        D1_AVG_EFF = 104.55
        SPREAD_SIGMA = 10.5

        projected_rows = []
        for g in schedule_events:
            away_match = kp_df[kp_df["TeamName"] == g["away"]]
            home_match = kp_df[kp_df["TeamName"] == g["home"]]

            if away_match.empty or home_match.empty:
                continue

            a_row = away_match.iloc[0]
            h_row = home_match.iloc[0]

            # Projected Pace
            proj_pace = (float(a_row["AdjTempo"]) * float(h_row["AdjTempo"])) / D1_AVG_TEMPO

            # Expected Points Per 100 Possessions
            a_pts_100 = (float(a_row["AdjOE"]) * float(h_row["AdjDE"])) / D1_AVG_EFF
            h_pts_100 = (float(h_row["AdjOE"]) * float(a_row["AdjDE"])) / D1_AVG_EFF

            # Venue Adjustment
            venue_hca = 0.0 if g["neutral"] else hca_val

            # Projected Scores & Totals
            a_proj_pts = (a_pts_100 * proj_pace / 100.0) - (venue_hca / 2.0)
            h_proj_pts = (h_pts_100 * proj_pace / 100.0) + (venue_hca / 2.0)
            margin = h_proj_pts - a_proj_pts  # Positive = Home Favorite
            proj_total = h_proj_pts + a_proj_pts

            # Probabilities
            home_win_prob = round(norm.cdf(margin / SPREAD_SIGMA) * 100.0, 1)
            away_win_prob = round(100.0 - home_win_prob, 1)

            def prob_to_american(p):
                if p <= 0: return 9999
                if p >= 100: return -9999
                prob_dec = p / 100.0
                return int(round(- (prob_dec / (1.0 - prob_dec)) * 100)) if prob_dec >= 0.5 else int(round(((1.0 - prob_dec) / prob_dec) * 100))

            fair_spread = -round(margin, 1)  # e.g., -4.5 for home favorite
            fair_total = round(proj_total, 1)
            fair_home_ml = prob_to_american(home_win_prob)
            fair_away_ml = prob_to_american(away_win_prob)

            icon = "🔥" if proj_total >= 152.0 else "⚡" if proj_pace >= 73.0 else "🧊" if proj_pace <= 66.0 else ""
            display_tag = f"{g['tag']} [{fair_total} {icon}]".strip()
            schedule_labels[g['tag']] = display_tag

            projected_rows.append({
                "Tag": g["tag"],
                "Away_Team": g["away"],
                "Home_Team": g["home"],
                "Neutral": g["neutral"],
                "Proj_Pace": round(proj_pace, 1),
                "Away_Proj_Pts": round(a_proj_pts, 1),
                "Home_Proj_Pts": round(h_proj_pts, 1),
                "Fair_Spread": fair_spread,
                "Fair_Total": fair_total,
                "Home_Win_Prob_%": home_win_prob,
                "Away_Win_Prob_%": away_win_prob,
                "Fair_Home_ML": fair_home_ml,
                "Fair_Away_ML": fair_away_ml
            })

        proj_df = pd.DataFrame(projected_rows)

        # ---------------------------------------------------------
        # 3. SCHEDULE PILLS MULTISELECT
        # ---------------------------------------------------------
        if not proj_df.empty:
            all_tags = proj_df["Tag"].tolist()
            saved_key = f"cbb_saved_pairs_{date_str}"
            init_flag_key = f"cbb_slate_init_{date_str}"
            widget_key = f"cbb_pairs_widget_{date_str}"

            if init_flag_key not in st.session_state:
                st.session_state[saved_key] = all_tags
                st.session_state[init_flag_key] = True

            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state.get(saved_key, all_tags)

            st.session_state[widget_key] = [t for t in st.session_state[widget_key] if t in all_tags]

            selected_matchups = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Slate Pace)",
                options=all_tags,
                format_func=lambda x: schedule_labels.get(x, x),
                key=widget_key
            )
            st.session_state[saved_key] = selected_matchups

            if not selected_matchups:
                st.info("🎯 Select one or more game matchups above to populate the matrix.")
            else:
                filtered_df = proj_df[proj_df["Tag"].isin(selected_matchups)].copy()

                if selected_market == "Spread (Cover)":
                    filtered_df["Selection"] = filtered_df.apply(lambda r: f"{r['Home_Team']} {r['Fair_Spread']}", axis=1)
                    filtered_df["Model_Prob_%"] = 50.0
                    filtered_df["Market_Line"] = filtered_df["Fair_Spread"]
                    display_cols = ["Selection", "Tag", "Home_Proj_Pts", "Away_Proj_Pts", "Fair_Spread", "Fair_Total", "Proj_Pace"]

                elif selected_market == "Moneyline (Win)":
                    filtered_df["Selection"] = filtered_df.apply(lambda r: f"{r['Home_Team']} ML" if r["Home_Win_Prob_%"] >= 50 else f"{r['Away_Team']} ML", axis=1)
                    filtered_df["Model_Prob_%"] = filtered_df.apply(lambda r: r["Home_Win_Prob_%"] if r["Home_Win_Prob_%"] >= 50 else r["Away_Win_Prob_%"], axis=1)
                    filtered_df["Market_Line"] = 0.0
                    display_cols = ["Selection", "Tag", "Home_Win_Prob_%", "Away_Win_Prob_%", "Fair_Home_ML", "Fair_Away_ML", "Proj_Pace"]

                else:  # Game Total
                    filtered_df["Selection"] = filtered_df.apply(lambda r: f"Over {r['Fair_Total']}", axis=1)
                    filtered_df["Model_Prob_%"] = 50.0
                    filtered_df["Market_Line"] = filtered_df["Fair_Total"]
                    display_cols = ["Selection", "Tag", "Fair_Total", "Proj_Pace", "Home_Proj_Pts", "Away_Proj_Pts"]

                st.markdown(f"### 📈 Slate Projections Matrix ({selected_market}):")

                display_matrix = filtered_df[display_cols].copy()
                display_matrix.insert(0, "Select", False)

                edited_df = st.data_editor(
                    display_matrix,
                    hide_index=True,
                    use_container_width=True,
                    column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                    key=f"cbb_matrix_editor_{selected_market}_{date_str}"
                )

                # ---------------------------------------------------------
                # 4. DUAL ACTION BUTTONS (ADD TO SLIP / AUTO-LOAD VALUE)
                # ---------------------------------------------------------
                col_add_btn, col_auto_btn = st.columns(2)

                with col_add_btn:
                    if st.button("➕ Add Checked Games to Bet Slip", use_container_width=True):
                        selected_rows = edited_df[edited_df["Select"] == True]
                        if not selected_rows.empty:
                            added_count = 0
                            for _, r in selected_rows.iterrows():
                                match_orig = filtered_df[filtered_df["Selection"] == r["Selection"]].iloc[0]
                                new_item = {
                                    "Include in Parlay": True,
                                    "Sportsbook": "FanDuel",
                                    "Matchup": match_orig["Tag"],
                                    "Selection": match_orig["Selection"],
                                    "Market": selected_market,
                                    "Line": match_orig["Market_Line"],
                                    "Nexus Odds (+/-)": None,
                                    "Model Prob (%)": match_orig["Model_Prob_%"],
                                    "Fair_Spread": match_orig["Fair_Spread"],
                                    "Proj_Margin": round(match_orig["Home_Proj_Pts"] - match_orig["Away_Proj_Pts"], 1),
                                    "Fair_Total": match_orig["Fair_Total"],
                                    "Delete": False
                                }
                                if not any(d["Selection"] == new_item["Selection"] and d["Market"] == new_item["Market"] for d in st.session_state["cbb_bet_slip"]):
                                    st.session_state["cbb_bet_slip"].append(new_item)
                                    added_count += 1
                            st.success(f"Added {added_count} selected plays to Tab 1!")
                        else:
                            st.warning("Please check at least one game in the matrix first.")

                with col_auto_btn:
                    if st.button("⚡ Auto-Load Top 5 Highest-Confidence Plays", use_container_width=True):
                        top_candidates = filtered_df.sort_values(by="Model_Prob_%", ascending=False).head(5)
                        added_count = 0
                        for _, match_orig in top_candidates.iterrows():
                            new_item = {
                                "Include in Parlay": True,
                                "Sportsbook": "FanDuel",
                                "Matchup": match_orig["Tag"],
                                "Selection": match_orig["Selection"],
                                "Market": selected_market,
                                "Line": match_orig["Market_Line"],
                                "Nexus Odds (+/-)": None,
                                "Model Prob (%)": match_orig["Model_Prob_%"],
                                "Fair_Spread": match_orig["Fair_Spread"],
                                "Proj_Margin": round(match_orig["Home_Proj_Pts"] - match_orig["Away_Proj_Pts"], 1),
                                "Fair_Total": match_orig["Fair_Total"],
                                "Delete": False
                            }
                            if not any(d["Selection"] == new_item["Selection"] and d["Market"] == new_item["Market"] for d in st.session_state["cbb_bet_slip"]):
                                st.session_state["cbb_bet_slip"].append(new_item)
                                added_count += 1
                        st.success(f"Auto-loaded top {added_count} plays into Tab 1!")
        else:
            st.info("No games found for this slate date. Check your date selection above.")
    else:
        st.info("Please drop your KenPom summary27.csv file above to populate the matrix.")

# -------------------------------------------------------------
# TAB 1: BET SLIP & ODDS COMPARATOR
# -------------------------------------------------------------
with tab1:
    st.subheader("📝 Checked Games & Nexus Odds Comparator")
    st.caption("Enter your book line and Nexus Odds. Live mathematical edge and compound boost calculate in real time.")

    if st.button("🗑️ Clear Bet Slip"):
        st.session_state["cbb_bet_slip"] = []
        st.rerun()

    if st.session_state["cbb_bet_slip"]:
        slip_df = pd.DataFrame(st.session_state["cbb_bet_slip"])

        columns_for_editor = ["Include in Parlay", "Sportsbook", "Matchup", "Selection", "Market", "Line", "Nexus Odds (+/-)", "Delete"]
        for c in columns_for_editor:
            if c not in slip_df.columns:
                slip_df[c] = None

        edited_slip = st.data_editor(
            slip_df[columns_for_editor],
            hide_index=True,
            use_container_width=True,
            column_config={
                "Include in Parlay": st.column_config.CheckboxColumn(),
                "Sportsbook": st.column_config.SelectboxColumn(
                    "Sportsbook",
                    help="Select sportsbook offering this line",
                    options=["FanDuel", "bet365", "DraftKings", "theScore Bet", "BetMGM", "BetRivers"],
                    required=True
                ),
                "Line": st.column_config.NumberColumn(
                    "Line / Spread",
                    help="Adjust book spread (e.g. -3.5) or Total (e.g. 149.5)"
                ),
                "Nexus Odds (+/-)": st.column_config.NumberColumn(
                    "Nexus Odds (+/-)",
                    help="Type American odds (e.g. -110 or +135)"
                ),
                "Delete": st.column_config.CheckboxColumn()
            },
            key="cbb_slip_editor"
        )

        if edited_slip["Delete"].any():
            surviving_selections = edited_slip[~edited_slip["Delete"]]["Selection"].tolist()
            st.session_state["cbb_bet_slip"] = [d for d in st.session_state["cbb_bet_slip"] if d["Selection"] in surviving_selections]
            st.rerun()

        for idx, row in edited_slip.iterrows():
            st.session_state["cbb_bet_slip"][idx]["Include in Parlay"] = row["Include in Parlay"]
            st.session_state["cbb_bet_slip"][idx]["Sportsbook"] = row["Sportsbook"]
            st.session_state["cbb_bet_slip"][idx]["Line"] = row["Line"]
            st.session_state["cbb_bet_slip"][idx]["Nexus Odds (+/-)"] = row["Nexus Odds (+/-)"]

        # ---------------------------------------------------------
        # LIVE EDGE EVALUATION (DYNAMIC NORMAL DISTRIBUTION MATH)
        # ---------------------------------------------------------
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

        for row in st.session_state["cbb_bet_slip"]:
            odds_val = row.get("Nexus Odds (+/-)")
            market = row.get("Market")
            user_line = row.get("Line")
            proj_margin = row.get("Proj_Margin", 0.0)
            fair_total = row.get("Fair_Total", 140.0)

            if "Spread" in market and user_line is not None and pd.notna(user_line):
                z = (float(proj_margin) - (-float(user_line))) / 10.5
                model_prob = round(norm.cdf(z) * 100.0, 1)
            elif "Total" in market and user_line is not None and pd.notna(user_line):
                z = (float(fair_total) - float(user_line)) / 14.0
                model_prob = round(norm.cdf(z) * 100.0, 1)
            else:
                model_prob = row.get("Model Prob (%)", 50.0)

            if odds_val is not None and pd.notna(odds_val) and str(odds_val).strip() not in ["", "None"]:
                implied = american_to_implied(odds_val)
                if implied is not None:
                    implied_pct = implied * 100.0
                    edge = round(model_prob - implied_pct, 1)
                    edge_str = f"+{edge}%" if edge > 0 else f"{edge}%"
                    odds_display = f"+{int(odds_val)}" if float(odds_val) > 0 else f"{int(odds_val)}"

                    edge_data.append({
                        "Sportsbook": row.get("Sportsbook", "FanDuel"),
                        "Matchup": row.get("Matchup", ""),
                        "Selection": row.get("Selection", ""),
                        "Market": market,
                        "Line": user_line,
                        "Odds": odds_display,
                        "Model Prob": f"{model_prob}%",
                        "Edge %": edge_str
                    })

                    if row.get("Include in Parlay", True):
                        active_legs += 1
                        o = float(odds_val)
                        mult = (o / 100.0 + 1.0) if o > 0 else (100.0 / abs(o) + 1.0)
                        parlay_mult *= mult
                        parlay_prob *= (model_prob / 100.0)

        if edge_data:
            st.dataframe(pd.DataFrame(edge_data), hide_index=True, use_container_width=True)
        else:
            st.info("Enter lines and Nexus Odds in the table above to calculate edges for your checked games.")

        # ---------------------------------------------------------
        # LIVE COMPOUND SLIP & PROFIT BOOST CALCULATOR
        # ---------------------------------------------------------
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
        st.info("Your bet slip is currently empty. Check games in Tab 2 to evaluate edges.")
