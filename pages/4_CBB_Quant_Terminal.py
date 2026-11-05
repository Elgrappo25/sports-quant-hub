import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from scipy.stats import norm

st.set_page_config(page_title="CBB Quant Terminal", page_icon="🏀", layout="wide")

st.title("🏀 CBB Quant Terminal: Production Suite")
st.markdown("KenPom Matchup Efficiency, Multi-Book Best-Line EV Scanner, and Compound Slip Evaluator")

# -------------------------------------------------------------
# PERSISTENT SESSION STATE INITIALIZATION (ISOLATED CBB NAMESPACE)
# -------------------------------------------------------------
if "cbb_bet_slip" not in st.session_state:
    st.session_state["cbb_bet_slip"] = []

if "cbb_raw_kp" not in st.session_state:
    st.session_state["cbb_raw_kp"] = None

if "cbb_hca" not in st.session_state:
    st.session_state["cbb_hca"] = 3.2

if "cbb_max_spread" not in st.session_state:
    st.session_state["cbb_max_spread"] = 10.5

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
    help="D1 national baseline is ~3.2 pts. High elevation venues (Utah St, Wyoming) can reach 4.5+."
)

max_spread_filter = st.sidebar.slider(
    "Max Spread Filter (Exclude Blowouts)",
    min_value=4.5,
    max_value=25.5,
    value=float(st.session_state["cbb_max_spread"]),
    step=1.0,
    key="cbb_max_spread",
    help="Filters out non-competitive games (e.g. Duke -35.5) where garbage time ruins spread covers."
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
st.sidebar.header("📡 The Odds API (Multi-Book Sync)")
default_api_key = st.secrets.get("ODDS_API_KEY", "") if hasattr(st, "secrets") else ""
api_key_input = st.sidebar.text_input("API Key", value=default_api_key, type="password", key="cbb_api_key")

if st.sidebar.button("🔄 Sync CBB Odds (Costs 3 Credits)", use_container_width=True):
    if not api_key_input:
        st.sidebar.error("Enter a valid Odds API Key first.")
    else:
        with st.sidebar.status("Querying FanDuel, DraftKings, BetMGM, BetRivers, theScore Bet..."):
            url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
            # Target your 5 API-accessible books (espnbet = theScore Bet engine)
            params = {
                "apiKey": api_key_input,
                "bookmakers": "fanduel,draftkings,betmgm,betrivers,espnbet",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american"
            }
            try:
                res = requests.get(url, params=params, timeout=12)
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
# ROBUST TEAM TOKEN RESOLVER
# -------------------------------------------------------------
KENPOM_ALIASES = {
    "PENN STATE": "Penn St.",
    "PENN ST": "Penn St.",
    "PENN ST.": "Penn St.",
    "UCONN": "Connecticut",
    "OLE MISS": "Mississippi",
    "NC STATE": "N.C. State",
    "N.C. STATE": "N.C. State",
    "MIAMI": "Miami FL",
    "ST. JOHN'S": "St. John's",
    "PENN": "Penn",
    "PITT": "Pittsburgh",
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
    "UMASS": "Massachusetts"
}

def normalize_cbb_tokens(name):
    s = str(name).upper().strip()
    s = s.replace("N.C.", "NC").replace("N.C", "NC")
    s = s.replace("ST.", "STATE").replace("ST ", "STATE ")
    if s.endswith(" ST"):
        s = s[:-3] + " STATE"
    tokens = re.findall(r'[A-Z0-9]+', s)
    tokens = ["STATE" if t == "ST" else t for t in tokens]
    return set(tokens)

def resolve_team(raw_name, candidates_dict):
    raw_upper = str(raw_name).upper().strip()
    if raw_upper in KENPOM_ALIASES and KENPOM_ALIASES[raw_upper] in candidates_dict.values():
        return KENPOM_ALIASES[raw_upper]

    raw_tokens = normalize_cbb_tokens(raw_name)
    best_cand = None
    best_overlap = 0

    for cand_clean, orig in candidates_dict.items():
        cand_tokens = normalize_cbb_tokens(orig)
        # Protect against Penn vs Penn State / Iowa vs Iowa State
        if ("STATE" in raw_tokens) != ("STATE" in cand_tokens):
            continue
        overlap = len(raw_tokens.intersection(cand_tokens))
        if overlap > best_overlap and overlap >= min(len(raw_tokens), 1):
            best_overlap = overlap
            best_cand = orig

    return best_cand if best_cand else raw_name

# Helper math functions
def american_to_implied(odds):
    try:
        odds = float(odds)
        return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)
    except:
        return None

def prob_to_american(p):
    if p <= 0: return 9999
    if p >= 100: return -9999
    prob_dec = p / 100.0
    return int(round(- (prob_dec / (1.0 - prob_dec)) * 100)) if prob_dec >= 0.5 else int(round(((1.0 - prob_dec) / prob_dec) * 100))

# -------------------------------------------------------------
# TAB 2: DATA DROPZONE, SLATE MATRICES & MULTI-BOOK SCANNER
# -------------------------------------------------------------
with tab2:
    st.subheader("Data Engine: KenPom Ingestion & Market Screener")

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
            st.error(f"Error reading KenPom file: {e}")

    if st.session_state["cbb_raw_kp"] is not None:
        kp_df = st.session_state["cbb_raw_kp"].copy()
        kp_dict = {re.sub(r'[^A-Z0-9]', '', str(t).upper()): t for t in kp_df["TeamName"].unique()}

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            selected_market = st.selectbox(
                "Target Main Market Selection",
                ["Spread (Cover)", "Moneyline (Win)", "Game Total (Over)"],
                key="cbb_market_selector"
            )
        with c2:
            target_book_filter = st.selectbox(
                "Compare Odds Against",
                ["Best of My Books", "FanDuel", "DraftKings", "BetMGM", "theScore Bet", "BetRivers"],
                key="cbb_target_book_filter"
            )
        with c3:
            slate_date = st.date_input("Target Slate Date", pd.to_datetime("today"), key="cbb_slate_date")

        date_str = slate_date.strftime("%Y%m%d")

        # ---------------------------------------------------------
        # 1. LIVE ESPN SCHEDULE FETCH
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
            st.warning(f"ESPN schedule fetch note: {str(e)}")

        # ---------------------------------------------------------
        # 2. MATCHUP EFFICIENCY & MARGIN PROJECTIONS
        # ---------------------------------------------------------
        D1_AVG_TEMPO = 71.37
        D1_AVG_EFF = 104.55
        SPREAD_SIGMA = 10.5
        TOTAL_SIGMA = 14.0

        projected_rows = []
        for g in schedule_events:
            away_match = kp_df[kp_df["TeamName"] == g["away"]]
            home_match = kp_df[kp_df["TeamName"] == g["home"]]

            if away_match.empty or home_match.empty:
                continue

            a_row = away_match.iloc[0]
            h_row = home_match.iloc[0]

            proj_pace = (float(a_row["AdjTempo"]) * float(h_row["AdjTempo"])) / D1_AVG_TEMPO
            a_pts_100 = (float(a_row["AdjOE"]) * float(h_row["AdjDE"])) / D1_AVG_EFF
            h_pts_100 = (float(h_row["AdjOE"]) * float(a_row["AdjDE"])) / D1_AVG_EFF

            venue_hca = 0.0 if g["neutral"] else hca_val

            a_proj_pts = (a_pts_100 * proj_pace / 100.0) - (venue_hca / 2.0)
            h_proj_pts = (h_pts_100 * proj_pace / 100.0) + (venue_hca / 2.0)
            margin = h_proj_pts - a_proj_pts
            proj_total = h_proj_pts + a_proj_pts

            home_win_prob = round(norm.cdf(margin / SPREAD_SIGMA) * 100.0, 1)
            away_win_prob = round(100.0 - home_win_prob, 1)

            fair_spread = -round(margin, 1)
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
                "Proj_Margin": round(margin, 1),
                "Fair_Spread": fair_spread,
                "Fair_Total": fair_total,
                "Home_Win_Prob_%": home_win_prob,
                "Away_Win_Prob_%": away_win_prob,
                "Fair_Home_ML": fair_home_ml,
                "Fair_Away_ML": fair_away_ml
            })

        proj_df = pd.DataFrame(projected_rows)

        # ---------------------------------------------------------
        # 3. LIVE MULTI-BOOK EXTRACTION & EV CALCULATION
        # ---------------------------------------------------------
        book_key_map = {
            "fanduel": "FanDuel",
            "draftkings": "DraftKings",
            "betmgm": "BetMGM",
            "betrivers": "BetRivers",
            "espnbet": "theScore Bet"
        }

        def get_game_market_odds(h_name, a_name):
            if not st.session_state["cbb_odds_cache"]:
                return None

            h_tokens = normalize_cbb_tokens(h_name)
            a_tokens = normalize_cbb_tokens(a_name)

            best_match_game = None
            for g in st.session_state["cbb_odds_cache"]:
                gh_tok = normalize_cbb_tokens(g.get("home_team", ""))
                ga_tok = normalize_cbb_tokens(g.get("away_team", ""))

                if len(h_tokens.intersection(gh_tok)) >= 1 and len(a_tokens.intersection(ga_tok)) >= 1:
                    best_match_game = g
                    break

            if not best_match_game:
                return None

            best_spread = None   # (point, price, book_name)
            best_ml = None       # (price, book_name)
            best_total = None    # (point, price, book_name)

            req_book = target_book_filter.lower().replace(" ", "")

            for bm in best_match_game.get("bookmakers", []):
                bm_key = bm.get("key", "").lower()
                if bm_key not in book_key_map:
                    continue
                book_disp = book_key_map[bm_key]
                if target_book_filter != "Best of My Books" and req_book != bm_key and req_book != book_disp.lower().replace(" ", ""):
                    continue

                for mkt in bm.get("markets", []):
                    mk = mkt.get("key")
                    outs = mkt.get("outcomes", [])
                    if mk == "h2h":
                        for o in outs:
                            p = o.get("price")
                            # Check home outcome
                            if len(h_tokens.intersection(normalize_cbb_tokens(o.get("name")))) >= 1:
                                if best_ml is None or p > best_ml[0]:
                                    best_ml = (p, book_disp)
                    elif mk == "spreads":
                        for o in outs:
                            pt = o.get("point")
                            pr = o.get("price", -110)
                            if len(h_tokens.intersection(normalize_cbb_tokens(o.get("name")))) >= 1:
                                if best_spread is None or pt > best_spread[0] or (pt == best_spread[0] and pr > best_spread[1]):
                                    best_spread = (pt, pr, book_disp)
                    elif mk == "totals":
                        for o in outs:
                            if o.get("name") == "Over":
                                pt = o.get("point")
                                pr = o.get("price", -110)
                                if best_total is None or pt < best_total[0] or (pt == best_total[0] and pr > best_total[1]):
                                    best_total = (pt, pr, book_disp)

            return {
                "spread": best_spread,
                "ml": best_ml,
                "total": best_total
            }

        # ---------------------------------------------------------
        # 4. MATRIX FORMATTING & AUTOMATIC VALUE FILTERING
        # ---------------------------------------------------------
        if not proj_df.empty:
            # Enforce max spread filter to remove garbage-time blowouts
            proj_df = proj_df[proj_df["Fair_Spread"].abs() <= max_spread_filter].copy()

            # Merge live odds if cached
            if st.session_state["cbb_odds_cache"]:
                odds_data = [get_game_market_odds(r["Home_Team"], r["Away_Team"]) for _, r in proj_df.iterrows()]
            else:
                odds_data = [None] * len(proj_df)

            processed_rows = []
            for idx, r in proj_df.iterrows():
                o_dict = odds_data[idx] if idx < len(odds_data) else None

                if selected_market == "Spread (Cover)":
                    b_pt, b_pr, b_name = (None, None, "FanDuel")
                    if o_dict and o_dict.get("spread"):
                        b_pt, b_pr, b_name = o_dict["spread"]

                    target_spread = b_pt if b_pt is not None else r["Fair_Spread"]
                    # Dynamic cover prob on target line: Z = (Margin - (-Spread)) / 10.5
                    z = (r["Proj_Margin"] - (-float(target_spread))) / SPREAD_SIGMA
                    cover_prob = round(norm.cdf(z) * 100.0, 1)

                    implied_pct = american_to_implied(b_pr) * 100.0 if b_pr else 52.38
                    edge_pct = round(cover_prob - implied_pct, 1) if b_pt is not None else 0.0
                    pt_diff = round(b_pt - r["Fair_Spread"], 1) if b_pt is not None else 0.0

                    processed_rows.append({
                        "Selection": f"{r['Home_Team']} {target_spread}",
                        "Tag": r["Tag"],
                        "Best_Book": b_name,
                        "Book_Spread": b_pt if b_pt is not None else "Sync Odds",
                        "Fair_Spread": r["Fair_Spread"],
                        "Spread_Diff_Pts": pt_diff,
                        "Cover_Prob_%": cover_prob,
                        "Edge_%": edge_pct,
                        "Line": target_spread,
                        "Odds": b_pr if b_pr is not None else -110,
                        "Proj_Margin": r["Proj_Margin"],
                        "Fair_Total": r["Fair_Total"]
                    })

                elif selected_market == "Moneyline (Win)":
                    b_pr, b_name = (None, "FanDuel")
                    if o_dict and o_dict.get("ml"):
                        b_pr, b_name = o_dict["ml"]

                    is_home_fav = r["Home_Win_Prob_%"] >= 50.0
                    fav_team = r["Home_Team"] if is_home_fav else r["Away_Team"]
                    win_prob = r["Home_Win_Prob_%"] if is_home_fav else r["Away_Win_Prob_%"]
                    fair_ml = r["Fair_Home_ML"] if is_home_fav else r["Fair_Away_ML"]

                    # Filter extreme juice traps (steeper than -450)
                    if fair_ml < -450:
                        continue

                    implied_pct = american_to_implied(b_pr) * 100.0 if b_pr else (american_to_implied(fair_ml) * 100.0)
                    edge_pct = round(win_prob - implied_pct, 1) if b_pr is not None else 0.0

                    processed_rows.append({
                        "Selection": f"{fav_team} ML",
                        "Tag": r["Tag"],
                        "Best_Book": b_name,
                        "Book_ML": f"{b_pr:+d}" if b_pr is not None else "Sync Odds",
                        "Fair_ML": fair_ml,
                        "Model_Win_Prob_%": win_prob,
                        "EV_Edge_%": edge_pct,
                        "Line": 0.0,
                        "Odds": b_pr if b_pr is not None else fair_ml,
                        "Proj_Margin": r["Proj_Margin"],
                        "Fair_Total": r["Fair_Total"]
                    })

                else:  # Game Total (Over)
                    b_pt, b_pr, b_name = (None, None, "FanDuel")
                    if o_dict and o_dict.get("total"):
                        b_pt, b_pr, b_name = o_dict["total"]

                    target_total = b_pt if b_pt is not None else r["Fair_Total"]
                    z = (r["Fair_Total"] - float(target_total)) / TOTAL_SIGMA
                    over_prob = round(norm.cdf(z) * 100.0, 1)

                    implied_pct = american_to_implied(b_pr) * 100.0 if b_pr else 52.38
                    edge_pct = round(over_prob - implied_pct, 1) if b_pt is not None else 0.0
                    pt_diff = round(r["Fair_Total"] - b_pt, 1) if b_pt is not None else 0.0

                    processed_rows.append({
                        "Selection": f"Over {target_total}",
                        "Tag": r["Tag"],
                        "Best_Book": b_name,
                        "Book_Total": b_pt if b_pt is not None else "Sync Odds",
                        "Fair_Total": r["Fair_Total"],
                        "Total_Diff_Pts": pt_diff,
                        "Over_Prob_%": over_prob,
                        "Edge_%": edge_pct,
                        "Line": target_total,
                        "Odds": b_pr if b_pr is not None else -110,
                        "Proj_Margin": r["Proj_Margin"],
                        "Fair_Total_Val": r["Fair_Total"]
                    })

            matrix_df = pd.DataFrame(processed_rows)

            if not matrix_df.empty:
                # Prioritize sorting by true edge if odds are live, else by confidence
                sort_col = "Edge_%" if "Edge_%" in matrix_df.columns else "EV_Edge_%"
                matrix_df = matrix_df.sort_values(by=sort_col, ascending=False).reset_index(drop=True)

                all_tags = matrix_df["Tag"].tolist()
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
                    "🎯 Filter Matchups (Excludes Blowouts > Max Spread)",
                    options=all_tags,
                    format_func=lambda x: schedule_labels.get(x, x),
                    key=widget_key
                )
                st.session_state[saved_key] = selected_matchups

                filtered_matrix = matrix_df[matrix_df["Tag"].isin(selected_matchups)].copy()

                st.markdown(f"### 📈 Slate Projections & Edge Matrix ({selected_market}):")

                # Build clean display table
                display_cols = [c for c in filtered_matrix.columns if c not in ["Line", "Odds", "Proj_Margin", "Fair_Total_Val"]]
                display_table = filtered_matrix[display_cols].copy()
                display_table.insert(0, "Select", False)

                edited_df = st.data_editor(
                    display_table,
                    hide_index=True,
                    use_container_width=True,
                    column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                    key=f"cbb_matrix_editor_{selected_market}_{date_str}"
                )

                # ---------------------------------------------------------
                # 5. DUAL ACTION BUTTONS (ADD TO SLIP / VALUE AUTO-LOAD)
                # ---------------------------------------------------------
                col_add_btn, col_auto_btn = st.columns(2)

                with col_add_btn:
                    if st.button("➕ Add Checked Games to Bet Slip", use_container_width=True):
                        selected_rows = edited_df[edited_df["Select"] == True]
                        if not selected_rows.empty:
                            added_count = 0
                            for _, r in selected_rows.iterrows():
                                match_orig = filtered_matrix[filtered_matrix["Selection"] == r["Selection"]].iloc[0]
                                prob_val = match_orig.get("Cover_Prob_%", match_orig.get("Model_Win_Prob_%", match_orig.get("Over_Prob_%", 50.0)))
                                new_item = {
                                    "Include in Parlay": True,
                                    "Sportsbook": match_orig["Best_Book"],
                                    "Matchup": match_orig["Tag"],
                                    "Selection": match_orig["Selection"],
                                    "Market": selected_market,
                                    "Line": match_orig["Line"],
                                    "Nexus Odds (+/-)": match_orig["Odds"],
                                    "Model Prob (%)": prob_val,
                                    "Proj_Margin": match_orig["Proj_Margin"],
                                    "Fair_Total": match_orig.get("Fair_Total_Val", match_orig.get("Fair_Total", 140.0)),
                                    "Delete": False
                                }
                                if not any(d["Selection"] == new_item["Selection"] and d["Market"] == new_item["Market"] for d in st.session_state["cbb_bet_slip"]):
                                    st.session_state["cbb_bet_slip"].append(new_item)
                                    added_count += 1
                            st.success(f"Added {added_count} selected plays to Tab 1 bet slip!")
                        else:
                            st.warning("Please check at least one game in the matrix first.")

                with col_auto_btn:
                    if st.button("⚡ Auto-Load Top 5 Highest-EV Value Plays", use_container_width=True):
                        top_candidates = filtered_matrix.sort_values(by=sort_col, ascending=False).head(5)
                        added_count = 0
                        for _, match_orig in top_candidates.iterrows():
                            prob_val = match_orig.get("Cover_Prob_%", match_orig.get("Model_Win_Prob_%", match_orig.get("Over_Prob_%", 50.0)))
                            new_item = {
                                "Include in Parlay": True,
                                "Sportsbook": match_orig["Best_Book"],
                                "Matchup": match_orig["Tag"],
                                "Selection": match_orig["Selection"],
                                "Market": selected_market,
                                "Line": match_orig["Line"],
                                "Nexus Odds (+/-)": match_orig["Odds"],
                                "Model Prob (%)": prob_val,
                                "Proj_Margin": match_orig["Proj_Margin"],
                                "Fair_Total": match_orig.get("Fair_Total_Val", match_orig.get("Fair_Total", 140.0)),
                                "Delete": False
                            }
                            if not any(d["Selection"] == new_item["Selection"] and d["Market"] == new_item["Market"] for d in st.session_state["cbb_bet_slip"]):
                                st.session_state["cbb_bet_slip"].append(new_item)
                                added_count += 1
                        st.success(f"Auto-loaded top {added_count} highest-EV plays into Tab 1!")
            else:
                st.info("No games match the current spread/juice criteria on this slate.")
        else:
            st.info("No games found for this slate date. Check your date selection above.")
    else:
        st.info("Please drop your KenPom summary27.csv file above to activate the CBB engine.")

# -------------------------------------------------------------
# TAB 1: BET SLIP & ODDS COMPARATOR
# -------------------------------------------------------------
with tab1:
    st.subheader("📝 Checked Games & Nexus Odds Comparator")
    st.caption("Select your Sportsbook and enter Nexus Odds. Real-time mathematical edges calculate automatically.")

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
        # LIVE DYNAMIC EDGE EVALUATION
        # ---------------------------------------------------------
        st.markdown("### 📈 Live Edge Evaluation:")
        edge_data = []

        parlay_mult = 1.0
        parlay_prob = 1.0
        active_legs = 0

        for row in st.session_state["cbb_bet_slip"]:
            odds_val = row.get("Nexus Odds (+/-)")
            market = row.get("Market")
            user_line = row.get("Line")
            proj_margin = row.get("Proj_Margin", 0.0)
            fair_total = row.get("Fair_Total", 140.0)

            # Recalculate model prob dynamically based on line typed
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
