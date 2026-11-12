import pandas as pd


def select_promo_legs(
    df: pd.DataFrame,
    min_prob: float = 72.0,
    max_prob: float = 84.0,
    target_count: int = 3,
    max_per_team: int = 1,
    team_col: str = "Clean_Team",
    prob_col: str = "Model_Over_Prob_%",
    score_col: str = "Matchup_Proj",
    matchup_factor_col: str = "Matchup_Factor",
    min_matchup_factor: float = 0.85
) -> pd.DataFrame:
    """
    Downstream read-only filter for Sportsbook Promo Boosts.
    Filters candidate legs within a viable probability band, enforces
    anti-correlation (team diversity), and returns the top scoring legs.
    """
    if df.empty:
        return df

    working_df = df.copy()

    # 1. Hard Filter: Probability Window (prevents juice traps & low floor legs)
    mask = (working_df[prob_col] >= min_prob) & (working_df[prob_col] <= max_prob)
    
    # 2. Matchup Factor Floor: Permits slight road/defensive dips (e.g. 0.95 - 0.99)
    # while continuing to block extreme trap spots (< 0.85).
    if matchup_factor_col in working_df.columns:
        mask = mask & (working_df[matchup_factor_col] >= min_matchup_factor)

    filtered = working_df[mask].copy()

    # Fallback: widen probability criteria slightly if slate is small
    if filtered.empty:
        filtered = working_df[(working_df[prob_col] >= min_prob - 5.0) & 
                              (working_df[prob_col] <= max_prob + 5.0)].copy()

    if filtered.empty:
        return filtered

    # 3. Composite Score: Prioritizes projection volume + pace
    if matchup_factor_col in filtered.columns:
        filtered["_auto_rank_score"] = filtered[score_col] * filtered[matchup_factor_col]
    else:
        filtered["_auto_rank_score"] = filtered[score_col]

    filtered = filtered.sort_values(by="_auto_rank_score", ascending=False)

    # 4. Anti-Correlation Loop (Max X Players Per Team)
    selected_indices = []
    seen_teams = {}

    for idx, row in filtered.iterrows():
        team = row.get(team_col, "UNKNOWN")
        current_count = seen_teams.get(team, 0)

        if max_per_team <= 0 or current_count < max_per_team:
            selected_indices.append(idx)
            seen_teams[team] = current_count + 1

        if len(selected_indices) >= target_count:
            break

    return filtered.loc[selected_indices].drop(columns=["_auto_rank_score"], errors="ignore")


def get_market_threshold_defaults(sport: str, market: str, line: float = None) -> tuple[float, float]:
    """
    Returns (min_prob, max_prob) tailored to the exact sport, market, and milestone line.
    Tiers:
      - Floor / Promo Parlay Rungs: 70.0% - 82.0% (or 68.0% - 80.0% for 3PM)
      - Mainline / Median Rungs:    56.0% - 68.0%
      - Alt-Ceiling / Plus-Money:   35.0% - 50.0%
    """
    sport = str(sport).strip().upper()
    market = str(market).strip()
    val = float(line) if line is not None else 0.0

    # ---------------------------------------------------------
    # 1. COLLEGE BASKETBALL (CBB)
    # ---------------------------------------------------------
    if sport == "CBB":
        if "Moneyline" in market:
            return (70.0, 82.0)
        return (56.0, 68.0)

    # ---------------------------------------------------------
    # 2. NFL PROPS
    # ---------------------------------------------------------
    if sport == "NFL":
        if "Touchdown" in market or market == "Anytime Touchdown":
            return (40.0, 56.0)
        if "Reception" in market:
            if val <= 2.5:
                return (70.0, 82.0)
            elif val <= 4.5:
                return (56.0, 68.0)
            else:
                return (38.0, 52.0)
        if "Receiving" in market or "Rushing" in market:
            if val <= 39.5:
                return (70.0, 82.0)
            elif val <= 59.5:
                return (56.0, 68.0)
            else:
                return (35.0, 50.0)
        if "Passing" in market:
            if val <= 224.5:
                return (70.0, 82.0)
            elif val <= 249.5:
                return (56.0, 68.0)
            else:
                return (38.0, 52.0)

    # ---------------------------------------------------------
    # 3. NBA PROPS
    # ---------------------------------------------------------
    if sport == "NBA":
        if "3" in market or "Three" in market:
            if val <= 1.5:
                return (68.0, 80.0)
            elif val <= 2.5:
                return (52.0, 64.0)
            else:
                return (32.0, 48.0)
        if "Point" in market:
            if val <= 19.5:
                return (70.0, 82.0)
            elif val <= 24.5:
                return (56.0, 68.0)
            else:
                return (36.0, 50.0)
        if "Rebound" in market:
            if val <= 5.5:
                return (70.0, 82.0)
            elif val <= 7.5:
                return (56.0, 68.0)
            else:
                return (35.0, 50.0)
        if "Assist" in market:
            if val <= 4.5:
                return (70.0, 82.0)
            elif val <= 6.5:
                return (56.0, 68.0)
            else:
                return (35.0, 50.0)
        if "PRA" in market:
            if val <= 24.5:
                return (70.0, 82.0)
            elif val <= 29.5:
                return (56.0, 68.0)
            else:
                return (36.0, 50.0)

    # ---------------------------------------------------------
    # 4. NHL PROPS (Check SOG before Goal so "Shots on Goal" doesn't match "Goal")
    # ---------------------------------------------------------
    if sport == "NHL":
        if "Shot" in market or "SOG" in market:
            if val <= 1.5:
                return (70.0, 82.0)
            elif val <= 2.5:
                return (56.0, 68.0)
            else:
                return (38.0, 52.0)
        if "Goal" in market:
            return (35.0, 50.0)
        if "Point" in market:
            return (70.0, 82.0) if val <= 0.5 else (35.0, 48.0)
        if "Assist" in market:
            return (64.0, 76.0) if val <= 0.5 else (32.0, 46.0)

    # Universal Fallback
    return (70.0, 82.0)
