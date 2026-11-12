import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import numpy as np
import pandas as pd
import requests
from scipy.stats import nbinom, poisson


TEAM_ABBR_MAP = {
    "ARI": "ARI", "AZ": "ARI", "DIAMONDBACKS": "ARI", "ARIZONA DIAMONDBACKS": "ARI",
    "ATL": "ATL", "BRAVES": "ATL", "ATLANTA BRAVES": "ATL",
    "BAL": "BAL", "ORIOLES": "BAL", "BALTIMORE ORIOLES": "BAL",
    "BOS": "BOS", "RED SOX": "BOS", "BOSTON RED SOX": "BOS",
    "CHC": "CHC", "CUBS": "CHC", "CHICAGO CUBS": "CHC",
    "CHW": "CHW", "CWS": "CHW", "WHITE SOX": "CHW", "CHICAGO WHITE SOX": "CHW",
    "CIN": "CIN", "REDS": "CIN", "CINCINNATI REDS": "CIN",
    "CLE": "CLE", "GUARDIANS": "CLE", "CLEVELAND GUARDIANS": "CLE",
    "COL": "COL", "ROCKIES": "COL", "COLORADO ROCKIES": "COL",
    "DET": "DET", "TIGERS": "DET", "DETROIT TIGERS": "DET",
    "HOU": "HOU", "ASTROS": "HOU", "HOUSTON ASTROS": "HOU",
    "KC": "KC", "KCR": "KC", "ROYALS": "KC", "KANSAS CITY ROYALS": "KC",
    "LAA": "LAA", "ANGELS": "LAA", "LOS ANGELES ANGELS": "LAA",
    "LAD": "LAD", "DODGERS": "LAD", "LOS ANGELES DODGERS": "LAD",
    "MIA": "MIA", "MARLINS": "MIA", "MIAMI MARLINS": "MIA",
    "MIL": "MIL", "BREWERS": "MIL", "MILWAUKEE BREWERS": "MIL",
    "MIN": "MIN", "TWINS": "MIN", "MINNESOTA TWINS": "MIN",
    "NYM": "NYM", "METS": "NYM", "NEW YORK METS": "NYM",
    "NYY": "NYY", "YANKEES": "NYY", "NEW YORK YANKEES": "NYY",
    "OAK": "ATH", "ATH": "ATH", "ATHLETICS": "ATH", "OAKLAND ATHLETICS": "ATH",
    "PHI": "PHI", "PHILLIES": "PHI", "PHILADELPHIA PHILLIES": "PHI",
    "PIT": "PIT", "PIRATES": "PIT", "PITTSBURGH PIRATES": "PIT",
    "SD": "SD", "SDP": "SD", "PADRES": "SD", "SAN DIEGO PADRES": "SD",
    "SF": "SF", "SFG": "SF", "GIANTS": "SF", "SAN FRANCISCO GIANTS": "SF",
    "SEA": "SEA", "MARINERS": "SEA", "SEATTLE MARINERS": "SEA",
    "STL": "STL", "CARDINALS": "STL", "ST. LOUIS CARDINALS": "STL",
    "TB": "TB", "TBR": "TB", "RAYS": "TB", "TAMPA BAY RAYS": "TB",
    "TEX": "TEX", "RANGERS": "TEX", "TEXAS RANGERS": "TEX",
    "TOR": "TOR", "BLUE JAYS": "TOR", "TORONTO BLUE JAYS": "TOR",
    "WSH": "WSH", "WAS": "WSH", "NATIONALS": "WSH", "WASHINGTON NATIONALS": "WSH",
}


def normalize_team(raw: str) -> str:
    if pd.isna(raw):
        return "UNK"
    key = str(raw).strip().upper()
    return TEAM_ABBR_MAP.get(key, key)


def normalize_player_name(name: str) -> str:
    """Converts 'Alcantara, Sandy' or 'Sandy Alcantara' into normalized 'sandy alcantara'."""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        s = f"{parts[1]} {parts[0]}"
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = re.sub(r"[^a-zA-Z0-9\s]", "", s).lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(s.split())


def _parse_pct_col(series: pd.Series) -> pd.Series:
    """Parses '+6%' or '-11%' into numeric decimal (+6.0 -> 0.06)."""
    return (
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip()
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        / 100.0
    )


def _read_xlsx_stdlib(raw_bytes: bytes) -> pd.DataFrame:
    """Zero-dependency .xlsx reader using Python's built-in zipfile + xml parser."""
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
        shared_strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall(".//s:si", ns):
                texts = [t.text or "" for t in si.findall(".//s:t", ns)]
                shared_strings.append("".join(texts))

        sheets = sorted(
            [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        )
        if not sheets:
            return pd.DataFrame()
        sroot = ET.fromstring(z.read(sheets[0]))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        def col_to_idx(col_str: str) -> int:
            idx = 0
            for ch in col_str:
                if ch.isalpha():
                    idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
            return idx - 1

        rows_data = []
        for row in sroot.findall(".//s:sheetData/s:row", ns):
            row_dict = {}
            for c in row.findall("s:c", ns):
                ref = c.attrib.get("r", "")
                col_letters = "".join(ch for ch in ref if ch.isalpha())
                c_idx = col_to_idx(col_letters) if col_letters else len(row_dict)
                t_attr = c.attrib.get("t", "")
                v_el = c.find("s:v", ns)
                val = None
                if v_el is not None and v_el.text is not None:
                    if t_attr == "s":
                        val = shared_strings[int(v_el.text)]
                    elif t_attr == "b":
                        val = v_el.text == "1"
                    else:
                        try:
                            val = float(v_el.text)
                            if val.is_integer():
                                val = int(val)
                        except ValueError:
                            val = v_el.text
                else:
                    is_el = c.find("s:is/s:t", ns)
                    if is_el is not None:
                        val = is_el.text
                row_dict[c_idx] = val
            if row_dict:
                max_c = max(row_dict.keys())
                rows_data.append([row_dict.get(i, None) for i in range(max_c + 1)])

        if not rows_data:
            return pd.DataFrame()
        max_cols = max(len(r) for r in rows_data)
        padded = [r + [None] * (max_cols - len(r)) for r in rows_data]
        header = [str(h) if h is not None else f"Unnamed: {i}" for i, h in enumerate(padded[0])]
        df = pd.DataFrame(padded[1:], columns=header)
        if len(df.columns) > 0 and "Today's MLB Park Factors" in str(df.columns[0]) and len(df) > 0:
            df.columns = [str(c) if c is not None else f"Unnamed: {i}" for i, c in enumerate(df.iloc[0])]
            df = df.iloc[1:].reset_index(drop=True)
        return df


def _read_uploaded_file(file_obj) -> tuple[str, pd.DataFrame]:
    """Reads CSV or XLSX file object into a DataFrame cleanly without external Excel dependencies."""
    fname = getattr(file_obj, "name", "unknown")
    raw_bytes = file_obj.getvalue() if hasattr(file_obj, "getvalue") else file_obj.read()

    if fname.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw_bytes))
        return fname, df

    try:
        xls = pd.ExcelFile(io.BytesIO(raw_bytes))
        sheet = xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=sheet)
        if len(df.columns) > 0 and "Today's MLB Park Factors" in str(df.columns[0]):
            df = pd.read_excel(xls, sheet_name=sheet, header=1)
        return fname, df
    except Exception:
        df = _read_xlsx_stdlib(raw_bytes)
        return fname, df


def _prob_tb_over(line: float, lam_1b: float, lam_2b: float, lam_3b: float, lam_hr: float) -> float:
    """
    Exact discrete probability convolution for Total Bases:
    TB = 1*(1B) + 2*(2B) + 3*(3B) + 4*(HR).
    """
    target = int(np.floor(line)) + 1
    if target <= 0:
        return 1.0

    max_k = 10
    p1 = poisson.pmf(np.arange(max_k), max(lam_1b, 1e-6))
    p2 = poisson.pmf(np.arange(max_k), max(lam_2b, 1e-6))
    p3 = poisson.pmf(np.arange(max_k), max(lam_3b, 1e-6))
    p4 = poisson.pmf(np.arange(max_k), max(lam_hr, 1e-6))

    grid_size = 30
    pmf = np.zeros(grid_size)
    pmf[0] = 1.0
    for step, probs in [(1, p1), (2, p2), (3, p3), (4, p4)]:
        new_pmf = np.zeros(grid_size)
        for k, pk in enumerate(probs):
            if pk < 1e-9:
                continue
            shift = k * step
            if shift < grid_size:
                new_pmf[shift:] += pmf[: grid_size - shift] * pk
        pmf = new_pmf

    if target >= grid_size:
        return 0.0
    return float(np.clip(1.0 - np.sum(pmf[:target]), 0.0, 0.999))


def process_mlb_files(uploaded_files: list) -> dict:
    """
    Auto-routes all 16 Ballpark Pal & Baseball Savant files (.csv and .xlsx)
    by column signature, joins on MLBAM PlayerId and Team, and builds unified
    batter and pitcher projection tables plus slate metadata.
    """
    bpp_batters = pd.DataFrame()
    bpp_pitchers = pd.DataFrame()
    bpp_games = pd.DataFrame()
    bpp_teams = pd.DataFrame()
    bpp_matchups = pd.DataFrame()
    park_factors_game = pd.DataFrame()
    park_factors_player = pd.DataFrame()
    sp_proj_csv = pd.DataFrame()

    savant_exp_list = []
    savant_ev_list = []
    savant_bb_list = []
    savant_bt_list = []
    loaded_tags = []

    for f in uploaded_files:
        try:
            fname, df = _read_uploaded_file(f)
        except Exception:
            continue
        if df is None or df.empty:
            continue

        cols = set(str(c).strip() for c in df.columns)

        # 1. BallparkPal_Batters
        if {"PlateAppearances", "Bases", "HitProbability", "HomeRunProbability"}.issubset(cols):
            bpp_batters = df.copy()
            loaded_tags.append("BallparkPal Batters")

        # 2. BallparkPal_Pitchers
        elif {"BattersFaced", "Innings", "QualityStart", "Strikeouts"}.issubset(cols):
            bpp_pitchers = df.copy()
            loaded_tags.append("BallparkPal Pitchers")

        # 3. BallparkPal_Games
        elif {"AwayTeam", "HomeTeam", "RunsAway", "RunsHome"}.issubset(cols):
            bpp_games = df.copy()
            loaded_tags.append("BallparkPal Games")

        # 4. BallparkPal_Teams
        elif {"WinPercent", "HomeRuns0", "RunsInning1"}.issubset(cols):
            bpp_teams = df.copy()
            loaded_tags.append("BallparkPal Teams")

        # 5. Matchups.xlsx
        elif {"RC", "HR Boost", "XB Boost", "1B Boost", "K Boost"}.issubset(cols):
            bpp_matchups = df.copy()
            loaded_tags.append("BallparkPal Matchups")

        # 6. ParkFactors.csv (Game Stadium + Weather)
        elif {"Venue", "HR %", "2B/3B %", "1B %", "Runs %"}.issubset(cols):
            park_factors_game = df.copy()
            loaded_tags.append("ParkFactors (Game/Weather)")

        # 7. Todays MLB Park Factors.xlsx (Directional Spray)
        elif {"Tm", "Player", "Park", "2B/3B"}.issubset(cols):
            park_factors_player = df.copy()
            loaded_tags.append("ParkFactors (Player Spray)")

        # 8. StartingPitchers_Projections.csv
        elif {"Pitcher", "Inn", "BF", "K", "BB"}.issubset(cols):
            sp_proj_csv = df.copy()
            loaded_tags.append("SP Projections CSV")

        # 9. Baseball Savant: Expected Stats (Batter or Pitcher)
        elif {"est_ba", "est_slg", "est_woba"}.issubset(cols):
            savant_exp_list.append(df.copy())
            tag = "Savant Expected (Pitcher)" if "xera" in cols else "Savant Expected (Batter)"
            loaded_tags.append(tag)

        # 10. Baseball Savant: Exit Velocity / Barrels
        elif {"brl_percent", "ev95percent", "avg_hit_speed"}.issubset(cols):
            savant_ev_list.append(df.copy())
            loaded_tags.append("Savant Exit Velo/Barrels")

        # 11. Baseball Savant: Batted Ball Profile
        elif {"pull_air_rate", "air_rate", "fb_rate", "ld_rate"}.issubset(cols):
            savant_bb_list.append(df.copy())
            loaded_tags.append("Savant Batted Ball")

        # 12. Baseball Savant: Bat Tracking
        elif {"avg_bat_speed", "hard_swing_rate", "blast_per_swing"}.issubset(cols):
            savant_bt_list.append(df.copy())
            loaded_tags.append("Savant Bat Tracking")

    # Combine duplicate Savant tables and deduplicate by MLBAM ID
    def _merge_savant(dfs: list, id_candidates: list[str]) -> pd.DataFrame:
        if not dfs:
            return pd.DataFrame()
        out = pd.concat(dfs, ignore_index=True)
        id_col = next((c for c in id_candidates if c in out.columns), None)
        if id_col:
            out[id_col] = pd.to_numeric(out[id_col], errors="coerce")
            out = out.dropna(subset=[id_col]).drop_duplicates(subset=[id_col], keep="first")
            out = out.rename(columns={id_col: "PlayerId"})
            out["PlayerId"] = out["PlayerId"].astype(int)
        return out

    sav_exp = _merge_savant(savant_exp_list, ["player_id", "id"])
    sav_ev = _merge_savant(savant_ev_list, ["player_id", "id"])
    sav_bb = _merge_savant(savant_bb_list, ["id", "player_id"])
    sav_bt = _merge_savant(savant_bt_list, ["id", "player_id"])

    # Build Team-level Park + Weather & Implied Run Total lookups
    team_env = {}
    if not bpp_games.empty:
        for _, g in bpp_games.iterrows():
            away = normalize_team(g.get("AwayTeam"))
            home = normalize_team(g.get("HomeTeam"))
            r_away = float(g.get("RunsAway", 4.4) or 4.4)
            r_home = float(g.get("RunsHome", 4.4) or 4.4)
            total_runs = r_away + r_home
            team_env[away] = {
                "Opp": home,
                "Matchup_Str": f"{away} @ {home}",
                "Implied_Team_Runs": r_away,
                "Implied_Game_Total": total_runs,
                "Side": "A",
            }
            team_env[home] = {
                "Opp": away,
                "Matchup_Str": f"{away} @ {home}",
                "Implied_Team_Runs": r_home,
                "Implied_Game_Total": total_runs,
                "Side": "H",
            }

    if not park_factors_game.empty:
        pf_g = park_factors_game.copy()
        pf_g["hr_adj"] = _parse_pct_col(pf_g["HR %"])
        pf_g["xb_adj"] = _parse_pct_col(pf_g["2B/3B %"])
        pf_g["single_adj"] = _parse_pct_col(pf_g["1B %"])
        pf_g["runs_adj"] = _parse_pct_col(pf_g["Runs %"])
        for _, row in pf_g.iterrows():
            game_txt = str(row.get("Game", ""))
            if "@" in game_txt:
                parts = [normalize_team(p) for p in game_txt.split("@")]
                for tm in parts:
                    team_env.setdefault(tm, {})
                    team_env[tm].update({
                        "Venue": str(row.get("Venue", "")),
                        "Game_Time": str(row.get("Time", "")),
                        "PF_HR_Adj": float(row["hr_adj"]),
                        "PF_XB_Adj": float(row["xb_adj"]),
                        "PF_1B_Adj": float(row["single_adj"]),
                        "PF_Runs_Adj": float(row["runs_adj"]),
                    })

    # ---------------------------------------------------------
    # BUILD MASTER PITCHER TABLE
    # ---------------------------------------------------------
    pitchers_df = pd.DataFrame()
    if not bpp_pitchers.empty:
        pitchers_df = bpp_pitchers.copy()
        pitchers_df["PlayerId"] = pd.to_numeric(pitchers_df["PlayerId"], errors="coerce").fillna(0).astype(int)
        pitchers_df["Clean_Team"] = pitchers_df["Team"].apply(normalize_team)
        pitchers_df["Clean_Opp"] = pitchers_df["Opponent"].apply(normalize_team)
        pitchers_df["Norm_Name"] = pitchers_df["FullName"].apply(normalize_player_name)

        if not sav_exp.empty:
            exp_cols = [c for c in ["PlayerId", "pa", "est_ba", "est_slg", "est_woba", "era", "xera"] if c in sav_exp.columns]
            pitchers_df = pitchers_df.merge(sav_exp[exp_cols], on="PlayerId", how="left")
        if not sav_ev.empty:
            ev_cols = [c for c in ["PlayerId", "brl_percent", "ev95percent", "avg_hit_speed"] if c in sav_ev.columns]
            pitchers_df = pitchers_df.merge(sav_ev[ev_cols], on="PlayerId", how="left")
        if not sav_bb.empty:
            bb_cols = [c for c in ["PlayerId", "gb_rate", "air_rate", "fb_rate"] if c in sav_bb.columns]
            pitchers_df = pitchers_df.merge(sav_bb[bb_cols], on="PlayerId", how="left")
        if not sav_bt.empty:
            bt_cols = [c for c in ["PlayerId", "whiff_per_swing", "squared_up_per_bat_contact"] if c in sav_bt.columns]
            pitchers_df = pitchers_df.merge(sav_bt[bt_cols], on="PlayerId", how="left")

        opp_k_map = {}
        if not bpp_teams.empty and "Strikeouts" in bpp_teams.columns:
            for _, t_row in bpp_teams.iterrows():
                opp_k_map[normalize_team(t_row["Team"])] = float(t_row["Strikeouts"])

        starter_k_boost = {}
        if not bpp_matchups.empty and "Starter" in bpp_matchups.columns:
            m_st = bpp_matchups[pd.to_numeric(bpp_matchups["Starter"], errors="coerce") == 1].copy()
            for (tm, pit_last), grp in m_st.groupby(["Team", "Pitcher"]):
                starter_k_boost[(normalize_team(tm), str(pit_last).strip().lower())] = float(
                    pd.to_numeric(grp["K Boost"], errors="coerce").mean()
                )

        m_factors = []
        adj_ks = []
        for _, p in pitchers_df.iterrows():
            base_k = float(pd.to_numeric(p.get("Strikeouts"), errors="coerce") or 4.5)
            opp_tm = p["Clean_Opp"]
            last_nm = str(p.get("LastName", "")).strip().lower()

            opp_team_k = opp_k_map.get(opp_tm, 8.6)
            team_k_mult = 1.0 + np.clip((opp_team_k - 8.6) / 35.0, -0.10, 0.12)

            k_bst = starter_k_boost.get((opp_tm, last_nm), 0.0)
            matchup_k_mult = 1.0 + np.clip(k_bst / 200.0, -0.08, 0.10)

            whiff = float(p.get("whiff_per_swing", 0.24) if pd.notna(p.get("whiff_per_swing")) else 0.24)
            whiff_mult = 1.0 + np.clip((whiff - 0.24) * 0.45, -0.06, 0.08)

            mf = float(np.clip(team_k_mult * matchup_k_mult * whiff_mult, 0.82, 1.25))
            final_k = base_k * (0.60 + 0.40 * mf)

            m_factors.append(round(mf, 3))
            adj_ks.append(round(final_k, 2))

        pitchers_df["Matchup_Factor"] = m_factors
        pitchers_df["Adj_Strikeouts"] = adj_ks
        pitchers_df["Sample_BF"] = (
            pd.to_numeric(pitchers_df.get("pa", pd.to_numeric(pitchers_df["BattersFaced"], errors="coerce") * 15), errors="coerce")
            .fillna(50)
            .astype(int)
        )

    # Lookup opposing starting pitcher vulnerability by defending team
    opp_pitcher_vuln = {}
    if not pitchers_df.empty:
        for _, p in pitchers_df.iterrows():
            defending_tm = p["Clean_Team"]
            xera = float(p.get("xera", 4.15) if pd.notna(p.get("xera")) else 4.15)
            brl = float(p.get("brl_percent", 7.8) if pd.notna(p.get("brl_percent")) else 7.8)
            vuln_score = 1.0 + np.clip((xera - 4.15) / 18.0, -0.10, 0.12) + np.clip((brl - 7.8) / 60.0, -0.06, 0.08)
            opp_pitcher_vuln[defending_tm] = {
                "Opp_Pitcher": p["FullName"],
                "Opp_Hand": p.get("PitcherHand", "R"),
                "Pitcher_Vuln_Mult": float(np.clip(vuln_score, 0.84, 1.22)),
            }

    # ---------------------------------------------------------
    # BUILD MASTER BATTER TABLE
    # ---------------------------------------------------------
    batters_df = pd.DataFrame()
    if not bpp_batters.empty:
        batters_df = bpp_batters.copy()
        batters_df["PlayerId"] = pd.to_numeric(batters_df["PlayerId"], errors="coerce").fillna(0).astype(int)
        batters_df["Clean_Team"] = batters_df["Team"].apply(normalize_team)
        batters_df["Clean_Opp"] = batters_df["Opponent"].apply(normalize_team)
        batters_df["Norm_Name"] = batters_df["FullName"].apply(normalize_player_name)

        if not sav_exp.empty:
            exp_cols = [c for c in ["PlayerId", "pa", "ba", "est_ba", "slg", "est_slg", "woba", "est_woba"] if c in sav_exp.columns]
            batters_df = batters_df.merge(sav_exp[exp_cols], on="PlayerId", how="left")
        if not sav_ev.empty:
            ev_cols = [c for c in ["PlayerId", "brl_percent", "ev95percent", "avg_hit_speed", "max_hit_speed", "anglesweetspotpercent"] if c in sav_ev.columns]
            batters_df = batters_df.merge(sav_ev[ev_cols], on="PlayerId", how="left")
        if not sav_bb.empty:
            bb_cols = [c for c in ["PlayerId", "pull_air_rate", "air_rate", "fb_rate", "ld_rate", "gb_rate"] if c in sav_bb.columns]
            batters_df = batters_df.merge(sav_bb[bb_cols], on="PlayerId", how="left")
        if not sav_bt.empty:
            bt_cols = [c for c in ["PlayerId", "avg_bat_speed", "hard_swing_rate", "blast_per_swing", "squared_up_per_bat_contact"] if c in sav_bt.columns]
            batters_df = batters_df.merge(sav_bt[bt_cols], on="PlayerId", how="left")

        matchup_lookup = {}
        if not bpp_matchups.empty:
            m_df = bpp_matchups.copy()
            if "Starter" in m_df.columns:
                m_df = m_df[pd.to_numeric(m_df["Starter"], errors="coerce") == 1]
            for _, m_row in m_df.iterrows():
                key = (normalize_team(m_row.get("Team")), normalize_player_name(m_row.get("Batter")))
                matchup_lookup[key] = {
                    "RC": float(pd.to_numeric(m_row.get("RC"), errors="coerce") or 0),
                    "HR_Boost": float(pd.to_numeric(m_row.get("HR Boost"), errors="coerce") or 0),
                    "XB_Boost": float(pd.to_numeric(m_row.get("XB Boost"), errors="coerce") or 0),
                    "1B_Boost": float(pd.to_numeric(m_row.get("1B Boost"), errors="coerce") or 0),
                    "vs_Grade": float(pd.to_numeric(m_row.get("vs Grade"), errors="coerce") or 0),
                }

        spray_lookup = {}
        if not park_factors_player.empty:
            for _, sp_row in park_factors_player.iterrows():
                key = (normalize_team(sp_row.get("Tm")), normalize_player_name(sp_row.get("Player")))
                spray_lookup[key] = {
                    "Spray_HR": float(pd.to_numeric(sp_row.get("HR"), errors="coerce") or 1.0),
                    "Spray_XB": float(pd.to_numeric(sp_row.get("2B/3B"), errors="coerce") or 1.0),
                    "Spray_1B": float(pd.to_numeric(sp_row.get("1B"), errors="coerce") or 1.0),
                }

        m_factors = []
        opp_names = []
        opp_hands = []
        game_labels = []
        adj_hrr_list = []
        adj_hits_list = []
        adj_1b_list = []
        adj_2b_list = []
        adj_3b_list = []
        adj_hr_list = []
        adj_tb_list = []

        for _, b in batters_df.iterrows():
            tm = b["Clean_Team"]
            opp = b["Clean_Opp"]
            n_name = b["Norm_Name"]

            env = team_env.get(tm, {})
            game_labels.append(env.get("Matchup_Str", f"{tm} vs {opp}"))

            pit_info = opp_pitcher_vuln.get(opp, {"Opp_Pitcher": "TBD", "Opp_Hand": "R", "Pitcher_Vuln_Mult": 1.0})
            opp_names.append(pit_info["Opp_Pitcher"])
            opp_hands.append(pit_info["Opp_Hand"])

            m_info = matchup_lookup.get((tm, n_name), {"RC": 0.0, "HR_Boost": 0.0, "XB_Boost": 0.0, "1B_Boost": 0.0, "vs_Grade": 0.0})
            sp_info = spray_lookup.get((tm, n_name), {"Spray_HR": 1.0, "Spray_XB": 1.0, "Spray_1B": 1.0})

            pf_runs = env.get("PF_Runs_Adj", 0.0)
            pf_hr = env.get("PF_HR_Adj", 0.0)
            pf_xb = env.get("PF_XB_Adj", 0.0)
            pf_1b = env.get("PF_1B_Adj", 0.0)

            rc_mult = 1.0 + np.clip(m_info["RC"] / 150.0, -0.08, 0.10)
            env_mult = 1.0 + np.clip(pf_runs * 0.5, -0.08, 0.10)
            mf = float(np.clip(pit_info["Pitcher_Vuln_Mult"] * rc_mult * env_mult, 0.80, 1.25))
            m_factors.append(round(mf, 3))

            base_1b = float(pd.to_numeric(b.get("Singles"), errors="coerce") or 0.5)
            base_2b = float(pd.to_numeric(b.get("Doubles"), errors="coerce") or 0.15)
            base_3b = float(pd.to_numeric(b.get("Triples"), errors="coerce") or 0.01)
            base_hr = float(pd.to_numeric(b.get("HomeRuns"), errors="coerce") or 0.10)
            base_rbi = float(pd.to_numeric(b.get("RBIs"), errors="coerce") or 0.40)
            base_runs = float(pd.to_numeric(b.get("Runs"), errors="coerce") or 0.45)

            est_ba = float(b.get("est_ba", 0.250) if pd.notna(b.get("est_ba")) else 0.250)
            brl_pct = float(b.get("brl_percent", 8.0) if pd.notna(b.get("brl_percent")) else 8.0)
            pull_air = float(b.get("pull_air_rate", 0.16) if pd.notna(b.get("pull_air_rate")) else 0.16)

            contact_nudge = 1.0 + np.clip((est_ba - 0.250) * 0.6, -0.05, 0.06)
            power_nudge = 1.0 + np.clip((brl_pct - 8.0) / 80.0, -0.06, 0.10) + np.clip((pull_air - 0.16) * 0.4, -0.04, 0.06)

            hr_mult = (1.0 + np.clip(pf_hr * 0.4, -0.08, 0.12)) * (1.0 + np.clip(m_info["HR_Boost"] / 250.0, -0.06, 0.08)) * power_nudge
            xb_mult = (1.0 + np.clip(pf_xb * 0.4, -0.08, 0.12)) * (1.0 + np.clip(m_info["XB_Boost"] / 250.0, -0.06, 0.08)) * power_nudge
            s1_mult = (1.0 + np.clip(pf_1b * 0.4, -0.06, 0.08)) * (1.0 + np.clip(m_info["1B_Boost"] / 250.0, -0.05, 0.06)) * contact_nudge

            spray_hr_nudge = 0.75 + 0.25 * np.clip(sp_info["Spray_HR"], 0.75, 1.35)
            spray_xb_nudge = 0.75 + 0.25 * np.clip(sp_info["Spray_XB"], 0.75, 1.35)

            adj_1b = base_1b * s1_mult * (0.75 + 0.25 * mf)
            adj_2b = base_2b * xb_mult * spray_xb_nudge * (0.75 + 0.25 * mf)
            adj_3b = base_3b * xb_mult * (0.75 + 0.25 * mf)
            adj_hr = base_hr * hr_mult * spray_hr_nudge * (0.70 + 0.30 * mf)

            adj_hits = adj_1b + adj_2b + adj_3b + adj_hr
            adj_tb = adj_1b + 2.0 * adj_2b + 3.0 * adj_3b + 4.0 * adj_hr
            adj_hrr = adj_hits + (base_runs + base_rbi) * (0.65 + 0.35 * mf)

            adj_1b_list.append(round(adj_1b, 3))
            adj_2b_list.append(round(adj_2b, 3))
            adj_3b_list.append(round(adj_3b, 3))
            adj_hr_list.append(round(adj_hr, 3))
            adj_hits_list.append(round(adj_hits, 3))
            adj_tb_list.append(round(adj_tb, 3))
            adj_hrr_list.append(round(adj_hrr, 3))

        batters_df["Matchup_Factor"] = m_factors
        batters_df["Opp_Pitcher"] = opp_names
        batters_df["Opp_Hand"] = opp_hands
        batters_df["Game_Label"] = game_labels
        batters_df["Adj_1B"] = adj_1b_list
        batters_df["Adj_2B"] = adj_2b_list
        batters_df["Adj_3B"] = adj_3b_list
        batters_df["Adj_HR"] = adj_hr_list
        batters_df["Adj_Hits"] = adj_hits_list
        batters_df["Adj_TB"] = adj_tb_list
        batters_df["Adj_HRR"] = adj_hrr_list
        batters_df["Sample_PA"] = pd.to_numeric(batters_df.get("pa", 50), errors="coerce").fillna(50).astype(int)

    slate_date = None
    if not bpp_games.empty and "GameDate" in bpp_games.columns:
        slate_date = str(bpp_games["GameDate"].iloc[0])[:10]
    elif not bpp_batters.empty and "GameDate" in bpp_batters.columns:
        slate_date = str(bpp_batters["GameDate"].iloc[0])[:10]

    return {
        "batters": batters_df,
        "pitchers": pitchers_df,
        "games": bpp_games,
        "team_env": team_env,
        "slate_date": slate_date,
        "loaded_tags": sorted(set(loaded_tags)),
    }


def evaluate_mlb_market(
    parsed_data: dict,
    market: str,
    line: float,
    min_sample: int = 25,
    selected_games: list[str] | None = None,
) -> pd.DataFrame:
    """
    Computes market-specific Matchup_Proj and Model_Over_Prob_% for the active
    MLB market and milestone line, returning a standardized matrix ready for
    Tab 2 display and modules/auto_selector.py.
    """
    market = str(market).strip()
    val = float(line)
    target_int = int(np.floor(val))

    if "Strikeout" in market or "Ks" in market:
        df = parsed_data.get("pitchers", pd.DataFrame()).copy()
        if df.empty:
            return pd.DataFrame()

        df = df[df["Sample_BF"] >= min_sample].copy()
        if df.empty:
            return pd.DataFrame()

        team_env = parsed_data.get("team_env", {})
        df["Game_Label"] = df["Clean_Team"].map(
            lambda t: team_env.get(t, {}).get("Matchup_Str", f"{t} vs Opp")
        )
        if selected_games:
            df = df[df["Game_Label"].isin(selected_games)].copy()
        if df.empty:
            return pd.DataFrame()

        probs = []
        for _, r in df.iterrows():
            lam_k = max(float(r["Adj_Strikeouts"]), 0.05)
            p_over = (1.0 - poisson.cdf(target_int, lam_k)) * 100.0
            probs.append(round(float(np.clip(p_over, 0.1, 99.5)), 1))

        df["Player"] = df["FullName"]
        df["Pos_Slot"] = df["PitcherHand"].astype(str) + "HP"
        df["Opponent_Info"] = "vs " + df["Clean_Opp"]
        df["Sample"] = df["Sample_BF"]
        df["Base_Proj"] = pd.to_numeric(df["Strikeouts"], errors="coerce").round(2)
        df["Matchup_Proj"] = df["Adj_Strikeouts"].round(2)
        df["Model_Over_Prob_%"] = probs
        df["Key_Stat"] = df.apply(
            lambda r: f"IP: {float(r.get('Innings', 0)):.1f} | xERA: {float(r.get('xera', 0)):.2f}"
            if pd.notna(r.get("xera"))
            else f"IP: {float(r.get('Innings', 0)):.1f}",
            axis=1,
        )
        return df.sort_values(by="Model_Over_Prob_%", ascending=False).reset_index(drop=True)

    df = parsed_data.get("batters", pd.DataFrame()).copy()
    if df.empty:
        return pd.DataFrame()

    df = df[df["Sample_PA"] >= min_sample].copy()
    if selected_games:
        df = df[df["Game_Label"].isin(selected_games)].copy()
    if df.empty:
        return pd.DataFrame()

    base_projs = []
    matchup_projs = []
    probs = []

    for _, r in df.iterrows():
        if "HRR" in market:
            b_proj = float(
                (pd.to_numeric(r.get("Hits"), errors="coerce") or 0)
                + (pd.to_numeric(r.get("Runs"), errors="coerce") or 0)
                + (pd.to_numeric(r.get("RBIs"), errors="coerce") or 0)
            )
            m_proj = float(r["Adj_HRR"])
            nb_r = 3.5
            nb_p = nb_r / (nb_r + max(m_proj, 0.05))
            p_over = (1.0 - nbinom.cdf(target_int, nb_r, nb_p)) * 100.0

        elif "Total Bases" in market or "TB" in market:
            b_proj = float(pd.to_numeric(r.get("Bases"), errors="coerce") or 0)
            m_proj = float(r["Adj_TB"])
            p_over = _prob_tb_over(val, r["Adj_1B"], r["Adj_2B"], r["Adj_3B"], r["Adj_HR"]) * 100.0

        elif "Home Run" in market or market == "HR":
            b_proj = float(pd.to_numeric(r.get("HomeRuns"), errors="coerce") or 0)
            m_proj = float(r["Adj_HR"])
            p_pois = 1.0 - poisson.cdf(target_int, max(m_proj, 0.005))
            bpp_hr_p = float(r.get("HomeRunProbability", p_pois) if pd.notna(r.get("HomeRunProbability")) else p_pois)
            p_over = (0.50 * bpp_hr_p + 0.50 * p_pois) * 100.0

        else:  # Hits
            b_proj = float(pd.to_numeric(r.get("Hits"), errors="coerce") or 0)
            m_proj = float(r["Adj_Hits"])
            p_pois = 1.0 - poisson.cdf(target_int, max(m_proj, 0.02))
            if val <= 0.5 and pd.notna(r.get("HitProbability")):
                bpp_hit_p = float(r["HitProbability"])
                p_over = (0.50 * bpp_hit_p + 0.50 * p_pois) * 100.0
            else:
                p_over = p_pois * 100.0

        base_projs.append(round(b_proj, 2))
        matchup_projs.append(round(m_proj, 2))
        probs.append(round(float(np.clip(p_over, 0.1, 99.5)), 1))

    df["Player"] = df["FullName"]
    df["Pos_Slot"] = df.apply(
        lambda r: f"#{int(r['BattingPosition'])} ({r['BatterStand']})" if pd.notna(r.get("BattingPosition")) else "-",
        axis=1,
    )
    df["Opponent_Info"] = df.apply(lambda r: f"vs {r['Opp_Pitcher']} ({r['Opp_Hand']})", axis=1)
    df["Sample"] = df["Sample_PA"]
    df["Base_Proj"] = base_projs
    df["Matchup_Proj"] = matchup_projs
    df["Model_Over_Prob_%"] = probs
    df["Key_Stat"] = df.apply(
        lambda r: f"PA: {float(r.get('PlateAppearances', 0)):.1f} | Brl: {float(r.get('brl_percent', 0)):.1f}% | xSLG: {float(r.get('est_slg', 0)):.3f}"
        if pd.notna(r.get("brl_percent"))
        else f"PA: {float(r.get('PlateAppearances', 0)):.1f}",
        axis=1,
    )

    return df.sort_values(by="Model_Over_Prob_%", ascending=False).reset_index(drop=True)


def fetch_mlb_schedule_with_fallback(parsed_data: dict, target_date: str | None = None) -> list[dict]:
    """
    Fetches today's live MLB schedule and probable pitchers from statsapi.mlb.com.
    If no live games exist (e.g., offseason testing with sample files), falls back
    seamlessly to the matchups extracted from the uploaded Ballpark Pal files.
    """
    query_date = target_date or parsed_data.get("slate_date") or datetime.now().strftime("%Y-%m-%d")
    team_env = parsed_data.get("team_env", {})
    pitchers_df = parsed_data.get("pitchers", pd.DataFrame())

    bpp_sp_map = {}
    if not pitchers_df.empty:
        for _, p in pitchers_df.iterrows():
            bpp_sp_map[p["Clean_Team"]] = p["FullName"]

    games_out = []
    try:
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={query_date}&hydrate=probablePitcher,team"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            for d_entry in data.get("dates", []):
                for g in d_entry.get("games", []):
                    away_name = (
                        g.get("teams", {}).get("away", {}).get("team", {}).get("abbreviation")
                        or g.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                    )
                    home_name = (
                        g.get("teams", {}).get("home", {}).get("team", {}).get("abbreviation")
                        or g.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
                    )
                    away_abbr = normalize_team(away_name)
                    home_abbr = normalize_team(home_name)

                    away_sp = g.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName") or bpp_sp_map.get(away_abbr, "TBD")
                    home_sp = g.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName") or bpp_sp_map.get(home_abbr, "TBD")

                    env = team_env.get(away_abbr, {})
                    tot = env.get("Implied_Game_Total", 8.5)
                    hr_adj = env.get("PF_HR_Adj", 0.0) * 100.0
                    icon = "🔥" if tot >= 8.8 or hr_adj >= 5.0 else ("🧊" if tot <= 7.6 else "⚾")

                    matchup_key = f"{away_abbr} @ {home_abbr}"
                    pill = f"{matchup_key} [{away_sp.split()[-1]} vs {home_sp.split()[-1]} | {icon} {tot:.1f}R | {hr_adj:+.0f}% HR]"
                    games_out.append({
                        "matchup_key": matchup_key,
                        "pill_label": pill,
                        "away": away_abbr,
                        "home": home_abbr,
                        "away_sp": away_sp,
                        "home_sp": home_sp,
                        "implied_total": tot,
                    })
    except Exception:
        pass

    if not games_out and team_env:
        seen_matchups = set()
        for tm, env in team_env.items():
            if env.get("Side") != "A":
                continue
            matchup_key = env.get("Matchup_Str", "")
            if not matchup_key or matchup_key in seen_matchups:
                continue
            seen_matchups.add(matchup_key)

            away_abbr = tm
            home_abbr = env.get("Opp", "")
            away_sp = bpp_sp_map.get(away_abbr, "TBD")
            home_sp = bpp_sp_map.get(home_abbr, "TBD")
            tot = env.get("Implied_Game_Total", 8.5)
            hr_adj = env.get("PF_HR_Adj", 0.0) * 100.0
            icon = "🔥" if tot >= 8.8 or hr_adj >= 5.0 else ("🧊" if tot <= 7.6 else "⚾")

            pill = f"{matchup_key} [{away_sp.split()[-1]} vs {home_sp.split()[-1]} | {icon} {tot:.1f}R | {hr_adj:+.0f}% HR]"
            games_out.append({
                "matchup_key": matchup_key,
                "pill_label": pill,
                "away": away_abbr,
                "home": home_abbr,
                "away_sp": away_sp,
                "home_sp": home_sp,
                "implied_total": tot,
            })

    return games_out
