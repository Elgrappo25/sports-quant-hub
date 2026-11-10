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
    min_matchup_factor: float = 1.00
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
    
    # 2. Hard Filter: Matchup Factor (neutral or positive pace spots only)
    if matchup_factor_col in working_df.columns:
        mask = mask & (working_df[matchup_factor_col] >= min_matchup_factor)

    filtered = working_df[mask].copy()

    # Fallback: widen criteria slightly if slate is small
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
