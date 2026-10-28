import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson, norm

# ==========================================
# 1. MASTER TEAM TRANSLATION & LIVE SCHEDULE
# ==========================================
TEAM_MAP = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BRK": "Brooklyn Nets",
    "CHO": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHO": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards"
}
REV_TEAM_MAP = {v: k for k, v in TEAM_MAP.items()}

# Translation map for ESPN API team codes to Basketball-Reference codes
ESPN_ABBREV_MAP = {
    "BKN": "BRK", "CHA": "CHO", "PHX": "PHO", "WSH": "WAS",
    "GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA"
}

def fetch_live_nba_schedule(date_str):
    """
    Fetches official daily NBA schedule dynamically from ESPN API for any date (YYYY-MM-DD).
    Zero API keys needed.
    """
    clean_date = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={clean_date}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code != 200:
            return []
        data = resp.json()
        
        games = []
        for event in data.get("events", []):
            comp = event.get("competitions", [])[0]
            competitors = comp.get("competitors", [])
            
            home_raw = next(c["team"]["abbreviation"] for c in competitors if c["homeAway"] == "home")
            away_raw = next(c["team"]["abbreviation"] for c in competitors if c["homeAway"] == "away")
            
            home = ESPN_ABBREV_MAP.get(home_raw, home_raw)
            away = ESPN_ABBREV_MAP.get(away_raw, away_raw)
            
            games.append({
                "date": date_str,
                "away": away,
                "home": home,
                "matchup": f"{away} @ {home}"
            })
        return games
    except Exception:
        return []

# ==========================================
# 2. DATA INGESTION & NORMALIZATION
# ==========================================
def load_nba_datasets(player_csv_source, team_csv_source):
    df_p = pd.read_csv(player_csv_source)
    df_p = df_p[df_p["Player"] != "Player"].dropna(subset=["Player", "Team", "G", "MP"])
    
    numeric_cols = ["G", "GS", "MP", "3P", "3PA", "TRB", "ORB", "DRB", "AST", "PTS"]
    for col in numeric_cols:
        if col in df_p.columns:
            df_p[col] = pd.to_numeric(df_p[col], errors="coerce").fillna(0.0)
    
    df_p["MPG"] = df_p["MP"] / df_p["G"]
    df_p["PRA"] = df_p["PTS"] + df_p["TRB"] + df_p["AST"]
    
    df_t = pd.read_csv(team_csv_source, header=1)
    df_t = df_t.dropna(subset=["Team", "Pace", "DRtg"])
    
    for col in ["Pace", "DRtg", "ORtg", "eFG%.1", "DRB%"]:
        if col in df_t.columns:
            df_t[col] = pd.to_numeric(df_t[col], errors="coerce")
            
    lg_row = df_t[df_t["Team"] == "League Average"]
    lg_pace = float(lg_row["Pace"].iloc[0]) if not lg_row.empty else 101.3
    lg_drtg = float(lg_row["DRtg"].iloc[0]) if not lg_row.empty else 112.4
    lg_efg = float(lg_row["eFG%.1"].iloc[0]) if (not lg_row.empty and "eFG%.1" in lg_row) else 0.529
    lg_drb = float(lg_row["DRB%"].iloc[0]) if (not lg_row.empty and "DRB%" in lg_row) else 72.1
    
    df_t["Abbrev"] = df_t["Team"].map(REV_TEAM_MAP)
    team_dict = df_t.dropna(subset=["Abbrev"]).set_index("Abbrev").to_dict("index")
    
    baselines = {
        "pace": lg_pace,
        "drtg": lg_drtg,
        "efg": lg_efg,
        "drb": lg_drb
    }
    
    return df_p, team_dict, baselines

# ==========================================
# 3. PROJECTION & MATCHUP MATH ENGINE
# ==========================================
def calculate_matchup_factor(team_pace, opp_team_data, baselines, market):
    opp_pace = opp_team_data.get("Pace", baselines["pace"])
    opp_drtg = opp_team_data.get("DRtg", baselines["drtg"])
    opp_efg = opp_team_data.get("eFG%.1", baselines["efg"])
    opp_drb = opp_team_data.get("DRB%", baselines["drb"])
    
    game_pace = (team_pace + opp_pace) / 2.0
    pace_factor = game_pace / baselines["pace"]
    
    if market == "Points (PTS)":
        def_factor = opp_drtg / baselines["drtg"]
    elif market == "3-Pointers Made (3PM)":
        def_factor = opp_efg / baselines["efg"]
    elif market == "Rebounds (REB)":
        f_miss = (1.0 - opp_efg) / (1.0 - baselines["efg"])
        f_reb_vuln = (100.0 - opp_drb) / (100.0 - baselines["drb"])
        def_factor = (0.6 * f_miss) + (0.4 * f_reb_vuln)
    elif market == "Assists (AST)":
        def_factor = opp_drtg / baselines["drtg"]
    elif market == "PRA":
        pts_f = opp_drtg / baselines["drtg"]
        reb_f = ((1.0 - opp_efg) / (1.0 - baselines["efg"])) * 0.6 + ((100.0 - opp_drb) / (100.0 - baselines["drb"])) * 0.4
        def_factor = (0.5 * pts_f) + (0.3 * reb_f) + (0.2 * pts_f)
    else:
        def_factor = 1.0
        
    matchup_factor = pace_factor * def_factor
    return round(game_pace, 1), round(pace_factor, 4), round(matchup_factor, 4)

def calculate_projection_and_odds(per_100_stat, mpg, game_pace, matchup_factor, line, market):
    proj_poss = game_pace * (mpg / 48.0)
    proj_mean = (per_100_stat / 100.0) * proj_poss * matchup_factor
    
    if market in ["3-Pointers Made (3PM)", "Assists (AST)"]:
        prob_over = float(poisson.sf(int(np.floor(line)), proj_mean))
    else:
        sigma = max(proj_mean * 0.35, 2.0)
        prob_over = float(norm.sf(line, loc=proj_mean, scale=sigma))
        
    prob_pct = round(prob_over * 100.0, 1)
    
    if prob_over <= 0.001:
        fair_str = "+10000"
    elif prob_over >= 0.999:
        fair_str = "-10000"
    elif prob_over >= 0.5:
        fair_odds = int(round(- (prob_over / (1.0 - prob_over)) * 100.0))
        fair_str = f"{fair_odds}"
    else:
        fair_odds = int(round(((1.0 - prob_over) / prob_over) * 100.0))
        fair_str = f"+{fair_odds}"
        
    return round(proj_mean, 2), prob_pct, fair_str
