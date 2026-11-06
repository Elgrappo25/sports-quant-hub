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
# PERSISTENT SESSION STATE INITIALIZATION
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
    key="cbb_hca"
)

max_spread_filter = st.sidebar.slider(
    "Max Spread Filter (Exclude Blowouts)",
    min_value=4.5,
    max_value=25.5,
    value=float(st.session_state["cbb_max_spread"]),
    step=1.0,
    key="cbb_max_spread"
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
# MASTER CANONICAL D1 ALIAS MAP & RESOLUTION ENGINE
# -------------------------------------------------------------
EXPLICIT_KENPOM_MAP = {
    # LIU / Long Island split
    "LIU": "LIU",
    "LONG ISLAND": "LIU",
    "LONG ISLAND UNIVERSITY": "LIU",
    "LIU SHARKS": "LIU",
    "RHODE ISLAND": "Rhode Island",

    # Illinois splits
    "NORTHERN ILLINOIS": "Northern Illinois",
    "N ILLINOIS": "Northern Illinois",
    "N. ILLINOIS": "Northern Illinois",
    "NIU": "Northern Illinois",
    "ILLINOIS CHICAGO": "Illinois Chicago",
    "UIC": "Illinois Chicago",
    "SOUTHERN ILLINOIS": "Southern Illinois",
    "S ILLINOIS": "Southern Illinois",
    "S. ILLINOIS": "Southern Illinois",
    "SIU": "Southern Illinois",
    "EASTERN ILLINOIS": "Eastern Illinois",
    "E ILLINOIS": "Eastern Illinois",
    "E. ILLINOIS": "Eastern Illinois",
    "EIU": "Eastern Illinois",
    "WESTERN ILLINOIS": "Western Illinois",
    "W ILLINOIS": "Western Illinois",
    "W. ILLINOIS": "Western Illinois",
    "WIU": "Western Illinois",
    "ILLINOIS STATE": "Illinois St.",
    "ILLINOIS ST": "Illinois St.",
    "ILLINOIS ST.": "Illinois St.",
    "ILLINOIS": "Illinois",

    # Connecticut splits
    "CENTRAL CONNECTICUT": "Central Connecticut",
    "CENTRAL CONNECTICUT STATE": "Central Connecticut",
    "CENTRAL CONN": "Central Connecticut",
    "CENT. CONN.": "Central Connecticut",
    "CENT. CONN. ST.": "Central Connecticut",
    "CENTRAL CONN. ST.": "Central Connecticut",
    "CENTRAL CONN STATE": "Central Connecticut",
    "CCSU": "Central Connecticut",
    "CONNECTICUT": "Connecticut",
    "UCONN": "Connecticut",
    "UCONN HUSKIES": "Connecticut",

    # Pennsylvania / Ivy / State splits
    "PENN STATE": "Penn St.",
    "PENN ST": "Penn St.",
    "PENN ST.": "Penn St.",
    "PENN": "Penn",
    "PENNSYLVANIA": "Penn",

    # Florida
    "SOUTH FLORIDA": "South Florida",
    "USF": "South Florida",
    "CENTRAL FLORIDA": "UCF",
    "UCF": "UCF",
    "FLORIDA ATLANTIC": "Florida Atlantic",
    "FAU": "Florida Atlantic",
    "FLORIDA GULF COAST": "Florida Gulf Coast",
    "FGCU": "Florida Gulf Coast",
    "FLORIDA": "Florida",
    "FLORIDA STATE": "Florida St.",
    "FLORIDA ST": "Florida St.",
    "FLORIDA ST.": "Florida St.",
    "FLORIDA A&M": "Florida A&M",
    "FAMU": "Florida A&M",
    "FLORIDA INTERNATIONAL": "FIU",
    "FIU": "FIU",

    # Texas
    "NORTH TEXAS": "North Texas",
    "UNT": "North Texas",
    "TEXAS": "Texas",
    "TEXAS STATE": "Texas St.",
    "TEXAS ST": "Texas St.",
    "TEXAS TECH": "Texas Tech",
    "TEXAS A&M": "Texas A&M",
    "TEXAS A&M-COMMERCE": "East Texas A&M",
    "TEXAS A&M COMMERCE": "East Texas A&M",
    "EAST TEXAS A&M": "East Texas A&M",
    "TEXAS A&M-CORPUS CHRISTI": "Texas A&M Corpus Chris",
    "TEXAS A&M CORPUS CHRISTI": "Texas A&M Corpus Chris",
    "TEXAS A&M-CC": "Texas A&M Corpus Chris",
    "A&M-CORPUS CHRISTI": "Texas A&M Corpus Chris",
    "UT RIO GRANDE VALLEY": "UT Rio Grande Valley",
    "UTRGV": "UT Rio Grande Valley",
    "RIO GRANDE VALLEY": "UT Rio Grande Valley",
    "UTEP": "UTEP",
    "TEXAS-EL PASO": "UTEP",
    "UTSA": "UTSA",
    "TEXAS-SAN ANTONIO": "UTSA",
    "TEXAS SOUTHERN": "Texas Southern",
    "STEPHEN F. AUSTIN": "Stephen F. Austin",
    "SFA": "Stephen F. Austin",
    "SAM HOUSTON": "Sam Houston St.",
    "SAM HOUSTON STATE": "Sam Houston St.",
    "SAM HOUSTON ST": "Sam Houston St.",
    "SAM HOUSTON ST.": "Sam Houston St.",

    # Louisiana
    "LOUISIANA MONROE": "Louisiana Monroe",
    "LA MONROE": "Louisiana Monroe",
    "UL MONROE": "Louisiana Monroe",
    "ULM": "Louisiana Monroe",
    "LOUISIANA LAFAYETTE": "Louisiana",
    "LA LAFAYETTE": "Louisiana",
    "UL LAFAYETTE": "Louisiana",
    "LOUISIANA": "Louisiana",
    "ULL": "Louisiana",
    "LSU": "LSU",
    "LOUISIANA TECH": "Louisiana Tech",
    "LA TECH": "Louisiana Tech",
    "SOUTHEASTERN LOUISIANA": "Southeastern Louisiana",
    "SE LOUISIANA": "Southeastern Louisiana",
    "NEW ORLEANS": "New Orleans",
    "UNO": "New Orleans",

    # Indiana / Missouri
    "SIU EDWARDSVILLE": "SIUE",
    "SIU-EDWARDSVILLE": "SIUE",
    "SIUE": "SIUE",
    "IU INDY": "IU Indianapolis",
    "IUPUI": "IU Indianapolis",
    "IU INDIANAPOLIS": "IU Indianapolis",
    "PURDUE FORT WAYNE": "Purdue Fort Wayne",
    "FORT WAYNE": "Purdue Fort Wayne",
    "PFW": "Purdue Fort Wayne",
    "KANSAS CITY": "Kansas City",
    "UMKC": "Kansas City",

    # Nebraska / Minnesota
    "OMAHA": "Omaha",
    "NEBRASKA OMAHA": "Omaha",
    "NEB. OMAHA": "Omaha",
    "NEBRASKA-OMAHA": "Omaha",
    "NEBRASKA": "Nebraska",
    "ST. THOMAS": "St. Thomas",
    "ST. THOMAS (MN)": "St. Thomas",
    "ST. THOMAS-MINNESOTA": "St. Thomas",
    "SAINT THOMAS": "St. Thomas",

    # Carolinas & Virginia
    "NC STATE": "N.C. State",
    "N.C. STATE": "N.C. State",
    "NORTH CAROLINA STATE": "N.C. State",
    "NORTH CAROLINA": "North Carolina",
    "UNC": "North Carolina",
    "UNC GREENSBORO": "UNC Greensboro",
    "UNCG": "UNC Greensboro",
    "UNC ASHEVILLE": "UNC Asheville",
    "UNCA": "UNC Asheville",
    "UNC WILMINGTON": "UNC Wilmington",
    "UNCW": "UNC Wilmington",
    "USC UPSTATE": "USC Upstate",
    "SOUTH CAROLINA UPSTATE": "USC Upstate",
    "SOUTH CAROLINA": "South Carolina",
    "SOUTH CAROLINA STATE": "South Carolina St.",
    "SC STATE": "South Carolina St.",
    "VCU": "VCU",
    "VIRGINIA COMMONWEALTH": "VCU",
    "VIRGINIA": "Virginia",
    "VIRGINIA TECH": "Virginia Tech",
    "VMI": "VMI",

    # Mississippi & Alabama
    "OLE MISS": "Mississippi",
    "MISSISSIPPI": "Mississippi",
    "MISSISSIPPI STATE": "Mississippi St.",
    "MISSISSIPPI ST": "Mississippi St.",
    "SOUTHERN MISS": "Southern Miss",
    "SOUTHERN MISSISSIPPI": "Southern Miss",
    "USM": "Southern Miss",

    # Miami splits
    "MIAMI FL": "Miami FL",
    "MIAMI (FL)": "Miami FL",
    "MIAMI": "Miami FL",
    "MIAMI HURRICANES": "Miami FL",
    "MIAMI OH": "Miami OH",
    "MIAMI (OH)": "Miami OH",
    "MIAMI REDHAWKS": "Miami OH",

    # Saints & Universities
    "ST. JOHN'S": "St. John's",
    "SAINT JOHN'S": "St. John's",
    "SAINT JOSEPH'S": "Saint Joseph's",
    "ST. JOSEPH'S": "Saint Joseph's",
    "ST. JOE'S": "Saint Joseph's",
    "SAINT MARY'S": "Saint Mary's",
    "ST. MARY'S": "Saint Mary's",
    "SAINT PETER'S": "Saint Peter's",
    "ST. PETER'S": "Saint Peter's",
    "SAINT LOUIS": "Saint Louis",
    "ST. LOUIS": "Saint Louis",

    # Other D1 Programs
    "BOSTON COLLEGE": "Boston College",
    "PRAIRIE VIEW": "Prairie View A&M",
    "PRAIRIE VIEW A&M": "Prairie View A&M",
    "SMU": "SMU",
    "BYU": "BYU",
    "TCU": "TCU",
    "UNLV": "UNLV",
    "UMASS": "Massachusetts",
    "UMASS LOWELL": "UMass Lowell",
    "MASSACHUSETTS LOWELL": "UMass Lowell",
    "ALBANY": "Albany",
    "SUNY ALBANY": "Albany",
    "BINGHAMTON": "Binghamton",
    "BUFFALO": "Buffalo",
    "STONY BROOK": "Stony Brook",
    "MCNEESE": "McNeese",
    "MCNEESE STATE": "McNeese",
    "MCNEESE ST": "McNeese",
    "MCNEESE ST.": "McNeese",
    "NICHOLLS": "Nicholls St.",
    "NICHOLLS STATE": "Nicholls St.",
    "GRAMBLING": "Grambling St.",
    "GRAMBLING STATE": "Grambling St.",
    "ALCORN": "Alcorn St.",
    "ALCORN STATE": "Alcorn St."
}

DIRECTIONALS = {
    "NORTH", "SOUTH", "EAST", "WEST", "CENTRAL",
    "NORTHERN", "SOUTHERN", "EASTERN", "WESTERN", "MIDDLE"
}

GENERIC_STOP_WORDS = {
    "THE", "OF", "AT", "UNIVERSITY", "COLLEGE", "STATE", "TECH", 
    "ISLAND", "CITY", "VALLEY", "COAST", "MEN", "MENS", "BASKETBALL"
}

def clean_name_tokens(name):
    s = str(name).upper().strip()
    s = s.replace("&", " AND ").replace("N.C.", "NC")
    s = s.replace("(OH)", " OH ").replace("(FL)", " FL ")
    s = re.sub(r'\(.*?\)', '', s)

    # Standardize directionals & common abbreviations
    s = re.sub(r'\bN\b\.?', 'NORTHERN', s)
    s = re.sub(r'\bS\b\.?', 'SOUTHERN', s)
    s = re.sub(r'\bE\b\.?', 'EASTERN', s)
    s = re.sub(r'\bW\b\.?', 'WESTERN', s)
    s = re.sub(r'\bCENT\b\.?', 'CENTRAL', s)
    s = re.sub(r'\bCONN\b\.?', 'CONNECTICUT', s)
    s = re.sub(r'\bST\b\.?', 'STATE', s)
    s = re.sub(r'\bUCONN\b', 'CONNECTICUT', s)
    s = re.sub(r'\bCCSU\b', 'CENTRAL CONNECTICUT', s)
    s = re.sub(r'\bNIU\b', 'NORTHERN ILLINOIS', s)
    s = re.sub(r'\bUIC\b', 'ILLINOIS CHICAGO', s)
    s = re.sub(r'\bSIU\b', 'SOUTHERN ILLINOIS', s)
    s = re.sub(r'\bPENNSYLVANIA\b', 'PENN', s)
    s = re.sub(r'\bUMKC\b', 'KANSAS CITY', s)
    s = re.sub(r'\bUTRGV\b', 'UT RIO GRANDE VALLEY', s)
    s = re.sub(r'\bSIUE\b', 'SIU EDWARDSVILLE', s)
    s = re.sub(r'\bULM\b', 'LOUISIANA MONROE', s)
    s = re.sub(r'\bULL\b', 'LOUISIANA', s)
    s = re.sub(r'\bIUPUI\b', 'IU INDIANAPOLIS', s)
    s = re.sub(r'\bIU INDY\b', 'IU INDIANAPOLIS', s)
    s = re.sub(r'\bPFW\b', 'PURDUE FORT WAYNE', s)

    tokens = [t for t in re.findall(r'[A-Z0-9]+', s) if t not in GENERIC_STOP_WORDS]
    return set(tokens)

def resolve_d1_team(raw_name, kp_df):
    raw_str = str(raw_name).strip()
    raw_upper = raw_str.upper()

    # 1. Canonical alias dictionary lookup
    if raw_upper in EXPLICIT_KENPOM_MAP:
        cand = EXPLICIT_KENPOM_MAP[raw_upper]
        if cand in kp_df["TeamName"].values:
            return cand
        if cand.endswith(" St.") and cand[:-4] in kp_df["TeamName"].values:
            return cand[:-4]
        if not cand.endswith(" St.") and (cand + " St.") in kp_df["TeamName"].values:
            return cand + " St."

    # 2. Direct string match
    if raw_str in kp_df["TeamName"].values:
        return raw_str

    raw_tokens = clean_name_tokens(raw_str)
    if not raw_tokens:
        return None

    best_match = None

    # 3. Guarded token resolution
    for kp_name in kp_df["TeamName"].unique():
        kp_tokens = clean_name_tokens(kp_name)
        if not kp_tokens:
            continue

        # Strict directional parity (North Texas != Texas)
        raw_dirs = raw_tokens.intersection(DIRECTIONALS)
        kp_dirs = kp_tokens.intersection(DIRECTIONALS)
        if raw_dirs != kp_dirs:
            continue

        core_raw = raw_tokens - DIRECTIONALS
        core_kp = kp_tokens - DIRECTIONALS

        if not core_raw or not core_kp:
            continue

        # Reject non-D1 teams that have distinct proper nouns (e.g. Wesleyan, Biblical, Monticello)
        # Any candidate must share the primary root
        if core_raw == core_kp or core_kp.issubset(core_raw):
            # If raw has extra words, verify they aren't un-matched school names
            extra_words = core_raw - core_kp
            known_mascots = {"HAWKS", "WILDCATS", "BULLDOGS", "TIGERS", "EAGLES", "PANTHERS", "BEARS", "PIRATES", "BLUE", "RED", "GOLDEN"}
            if extra_words and not extra_words.issubset(known_mascots):
                continue

            if best_match is None or len(kp_tokens) > len(clean_name_tokens(best_match)):
                best_match = kp_name

    return best_match

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
# TAB 2: DATA ENGINE & MARKET SCREENER
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
            # Anchor to Eastern Time so UTC servers don't prematurely flip dates at 7:00 PM EST
            eastern_today = pd.Timestamp.now(tz="US/Eastern").date()
            slate_date = st.date_input("Target Slate Date", value=eastern_today, key="cbb_slate_date")

        date_str = slate_date.strftime("%Y%m%d")

        # 1. LIVE ESPN SCHEDULE FETCH WITH ACCURATE HOME/AWAY AND START TIMES
        schedule_events = []
        schedule_labels = {}

        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}&groups=50&limit=400"
            res = requests.get(url, timeout=7).json()
            for event in res.get("events", []):
                comp = event["competitions"][0]
                competitors = comp["competitors"]
                neutral = comp.get("neutralSite", False)

                # Parse tip-off time in Eastern Time
                raw_date = event.get("date")
                start_dt = None
                tip_display = ""
                if raw_date:
                    try:
                        dt = pd.to_datetime(raw_date)
                        if dt.tzinfo is None:
                            dt = dt.tz_localize("UTC")
                        start_dt = dt.tz_convert("US/Eastern")
                        tip_display = start_dt.strftime("%I:%M %p").lstrip("0") + " EST"
                    except:
                        pass

                # Strict homeAway evaluation
                home_raw, away_raw = None, None
                for c in competitors:
                    t_name = (
                        c.get("team", {}).get("location")
                        or c.get("team", {}).get("displayName")
                        or c.get("team", {}).get("shortDisplayName")
                    )
                    if c.get("homeAway") == "home":
                        home_raw = t_name
                    elif c.get("homeAway") == "away":
                        away_raw = t_name

                if not home_raw and len(competitors) > 0:
                    home_raw = competitors[0].get("team", {}).get("location") or competitors[0].get("team", {}).get("displayName")
                if not away_raw and len(competitors) > 1:
                    away_raw = competitors[1].get("team", {}).get("location") or competitors[1].get("team", {}).get("displayName")

                home_kp = resolve_d1_team(home_raw, kp_df)
                away_kp = resolve_d1_team(away_raw, kp_df)

                # Strict D1 guard: both teams MUST resolve to valid KenPom D1 programs
                if not home_kp or not away_kp:
                    continue

                tag = f"{away_kp} vs {home_kp}" if neutral else f"{away_kp} @ {home_kp}"
                schedule_events.append({
                    "tag": tag,
                    "away": away_kp,
                    "home": home_kp,
                    "neutral": neutral,
                    "start_dt": start_dt if start_dt is not None else pd.Timestamp.max,
                    "tip_display": tip_display
                })
        except Exception as e:
            st.warning(f"ESPN schedule fetch notice: {str(e)}")

        # 2. MATCHUP EFFICIENCY & MARGIN PROJECTIONS
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
            time_prefix = f"[{g['tip_display']}] " if g['tip_display'] else ""
            display_tag = f"{time_prefix}{g['tag']} [{fair_total} {icon}]".strip()
            schedule_labels[g['tag']] = display_tag

            projected_rows.append({
                "Tag": g["tag"],
                "Away_Team": g["away"],
                "Home_Team": g["home"],
                "Neutral": g["neutral"],
                "Start_Time_DT": g["start_dt"],
                "Tip_Off": g["tip_display"],
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

        # 3. LIVE MULTI-BOOK EXTRACTION ENGINE
        book_key_map = {
            "fanduel": "FanDuel",
            "draftkings": "DraftKings",
            "betmgm": "BetMGM",
            "betrivers": "BetRivers",
            "espnbet": "theScore Bet"
        }

        def match_team_tokens(source_name, target_name):
            tok_a = clean_name_tokens(source_name)
            tok_b = clean_name_tokens(target_name)

            if tok_a.intersection(DIRECTIONALS) != tok_b.intersection(DIRECTIONALS):
                return False

            core_a = tok_a - DIRECTIONALS
            core_b = tok_b - DIRECTIONALS
            return bool(core_a.intersection(core_b))

        def get_game_market_odds(h_name, a_name, target_team=None):
            if not st.session_state["cbb_odds_cache"]:
                return None

            best_match_game = None
            for g in st.session_state["cbb_odds_cache"]:
                api_home = g.get("home_team", "")
                api_away = g.get("away_team", "")

                direct_match = match_team_tokens(h_name, api_home) and match_team_tokens(a_name, api_away)
                inverted_match = match_team_tokens(h_name, api_away) and match_team_tokens(a_name, api_home)

                if direct_match or inverted_match:
                    best_match_game = g
                    break

            if not best_match_game:
                return None

            best_spread = None
            best_ml = None
            best_total = None

            req_book = target_book_filter.lower().replace(" ", "")
            eval_target = target_team if target_team else h_name

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
                            if match_team_tokens(eval_target, o.get("name")):
                                if best_ml is None or p > best_ml[0]:
                                    best_ml = (p, book_disp)
                    elif mk == "spreads":
                        for o in outs:
                            pt = o.get("point")
                            pr = o.get("price", -110)
                            if match_team_tokens(eval_target, o.get("name")):
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

        # 4. MATRIX FORMATTING & AUTOMATIC VALUE FILTERING
        if not proj_df.empty:
            proj_df = proj_df[proj_df["Fair_Spread"].abs() <= max_spread_filter].copy()

            processed_rows = []
            for idx, r in proj_df.iterrows():
                if selected_market == "Spread (Cover)":
                    o_dict = get_game_market_odds(r["Home_Team"], r["Away_Team"], target_team=r["Home_Team"])
                    b_pt, b_pr, b_name = (None, None, "FanDuel")
                    if o_dict and o_dict.get("spread"):
                        b_pt, b_pr, b_name = o_dict["spread"]

                    target_spread = b_pt if b_pt is not None else r["Fair_Spread"]
                    z = (r["Proj_Margin"] - (-float(target_spread))) / SPREAD_SIGMA
                    cover_prob = round(norm.cdf(z) * 100.0, 1)

                    implied_pct = american_to_implied(b_pr) * 100.0 if b_pr else 52.38
                    edge_pct = round(cover_prob - implied_pct, 1) if b_pt is not None else 0.0
                    pt_diff = round(b_pt - r["Fair_Spread"], 1) if b_pt is not None else 0.0

                    processed_rows.append({
                        "Selection": f"{r['Home_Team']} {target_spread}",
                        "Tag": r["Tag"],
                        "Tip_Off": r["Tip_Off"],
                        "Start_Time_DT": r["Start_Time_DT"],
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
                    is_home_fav = r["Home_Win_Prob_%"] >= 50.0
                    fav_team = r["Home_Team"] if is_home_fav else r["Away_Team"]
                    win_prob = r["Home_Win_Prob_%"] if is_home_fav else r["Away_Win_Prob_%"]
                    fair_ml = r["Fair_Home_ML"] if is_home_fav else r["Fair_Away_ML"]

                    if fair_ml < -450:
                        continue

                    o_dict = get_game_market_odds(r["Home_Team"], r["Away_Team"], target_team=fav_team)
                    b_pr, b_name = (None, "FanDuel")
                    if o_dict and o_dict.get("ml"):
                        b_pr, b_name = o_dict["ml"]

                    implied_pct = american_to_implied(b_pr) * 100.0 if b_pr else (american_to_implied(fair_ml) * 100.0)
                    edge_pct = round(win_prob - implied_pct, 1) if b_pr is not None else 0.0

                    processed_rows.append({
                        "Selection": f"{fav_team} ML",
                        "Tag": r["Tag"],
                        "Tip_Off": r["Tip_Off"],
                        "Start_Time_DT": r["Start_Time_DT"],
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
                    o_dict = get_game_market_odds(r["Home_Team"], r["Away_Team"])
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
                        "Tip_Off": r["Tip_Off"],
                        "Start_Time_DT": r["Start_Time_DT"],
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
                sort_col = "Edge_%" if "Edge_%" in matrix_df.columns else "EV_Edge_%"
                matrix_df = matrix_df.sort_values(by=sort_col, ascending=False).reset_index(drop=True)

                # Chronological ordering for matchup multiselect options
                sorted_by_time = matrix_df.sort_values(by="Start_Time_DT", ascending=True)
                all_tags = sorted_by_time["Tag"].drop_duplicates().tolist()

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
                    "🎯 Filter Matchups (Excludes Blowouts > Max Spread - Sorted by Tip-Off)",
                    options=all_tags,
                    format_func=lambda x: schedule_labels.get(x, x),
                    key=widget_key
                )
                st.session_state[saved_key] = selected_matchups

                filtered_matrix = matrix_df[matrix_df["Tag"].isin(selected_matchups)].copy()

                st.markdown(f"### 📈 Slate Projections & Edge Matrix ({selected_market}):")

                display_cols = [c for c in filtered_matrix.columns if c not in ["Line", "Odds", "Proj_Margin", "Fair_Total_Val", "Start_Time_DT"]]
                display_table = filtered_matrix[display_cols].copy()
                display_table.insert(0, "Select", False)

                edited_df = st.data_editor(
                    display_table,
                    hide_index=True,
                    use_container_width=True,
                    column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                    key=f"cbb_matrix_editor_{selected_market}_{date_str}"
                )

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

        # LIVE DYNAMIC EDGE EVALUATION
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

        # LIVE COMPOUND SLIP & PROFIT BOOST CALCULATOR
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
