import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

# 2026 Week 7 Schedule Reference
WEEK_7_SCHEDULE = [
    {"date": "2026-10-22", "away": "NE", "home": "CHI", "matchup": "NE @ CHI"},
    {"date": "2026-10-25", "away": "PIT", "home": "NO", "matchup": "PIT @ NO"},
    {"date": "2026-10-25", "away": "SF", "home": "ATL", "matchup": "SF @ ATL"},
    {"date": "2026-10-25", "away": "TB", "home": "CAR", "matchup": "TB @ CAR"},
    {"date": "2026-10-25", "away": "CIN", "home": "BAL", "matchup": "CIN @ BAL"},
    {"date": "2026-10-25", "away": "NYG", "home": "HOU", "matchup": "NYG @ HOU"},
    {"date": "2026-10-25", "away": "IND", "home": "MIN", "matchup": "IND @ MIN"},
    {"date": "2026-10-25", "away": "CLE", "home": "TEN", "matchup": "CLE @ TEN"},
    {"date": "2026-10-25", "away": "MIA", "home": "NYJ", "matchup": "MIA @ NYJ"},
    {"date": "2026-10-25", "away": "DEN", "home": "ARI", "matchup": "DEN @ ARI"},
    {"date": "2026-10-25", "away": "LAR", "home": "LV", "matchup": "LAR @ LV"},
    {"date": "2026-10-25", "away": "GB", "home": "DET", "matchup": "GB @ DET"},
    {"date": "2026-10-25", "away": "KC", "home": "SEA", "matchup": "KC @ SEA"},
    {"date": "2026-10-26", "away": "DAL", "home": "PHI", "matchup": "DAL @ PHI"}
]

def prob_to_american_odds(prob):
    if prob <= 0.0 or prob >= 1.0 or np.isnan(prob):
        return 0
    if prob > 0.50:
        return int(round(-100 * prob / (1 - prob)))
    else:
        return int(round(100 * (1 - prob) / prob))

def compute_nfl_team_baselines(df):
    def_pass = df.groupby('defteam')['passing_yards'].sum() / df.groupby('defteam')['game_id'].nunique()
    def_rush = df.groupby('defteam')['rushing_yards'].sum() / df.groupby('defteam')['game_id'].nunique()
    def_td = df[df['touchdown'] == 1].groupby('defteam')['touchdown'].count() / df.groupby('defteam')['game_id'].nunique()
    
    off_pass = df.groupby('posteam')['passing_yards'].sum() / df.groupby('posteam')['game_id'].nunique()
    off_rush = df.groupby('posteam')['rushing_yards'].sum() / df.groupby('posteam')['game_id'].nunique()
    
    league_pass_avg = def_pass.mean()
    league_rush_avg = def_rush.mean()
    league_td_avg = def_td.mean()
    
    return {
        'def_pass': def_pass,
        'def_rush': def_rush,
        'def_td': def_td,
        'off_pass': off_pass,
        'off_rush': off_rush,
        'league_pass_avg': league_pass_avg,
        'league_rush_avg': league_rush_avg,
        'league_td_avg': league_td_avg
    }

def calculate_matchup_factors_for_slate(schedule_games, baselines):
    factors = []
    l_pass = baselines['league_pass_avg']
    l_rush = baselines['league_rush_avg']
    
    for g in schedule_games:
        home, away = g['home'], g['away']
        home_tot = baselines['off_pass'].get(home, l_pass) + baselines['off_rush'].get(home, l_rush)
        away_tot = baselines['off_pass'].get(away, l_pass) + baselines['off_rush'].get(away, l_rush)
        league_median = l_pass + l_rush
        combined_factor = round((home_tot + away_tot) / (2 * league_median), 2)
        
        factors.append({
            'matchup': g['matchup'],
            'date': g['date'],
            'home': home,
            'away': away,
            'combined_factor': combined_factor,
            'is_fire': combined_factor >= 2.05
        })
    
    factors.sort(key=lambda x: x['combined_factor'], reverse=True)
    return factors

def process_nfl_player_matrix(df, baselines, selected_matchups, market, threshold_line, min_gp=3):
    matrix_rows = []
    
    active_teams = set()
    team_opp_map = {}
    for m in selected_matchups:
        home, away = m['home'], m['away']
        active_teams.add(home)
        active_teams.add(away)
        team_opp_map[home] = f"vs {away}"
        team_opp_map[away] = f"@{home}"
        
    l_pass = baselines['league_pass_avg']
    l_rush = baselines['league_rush_avg']
    l_td = baselines['league_td_avg']
    
    if market == "Passing Yards":
        qb_logs = df[df['pass_attempt'] == 1].groupby(['passer_player_name', 'posteam', 'game_id'])['passing_yards'].sum().reset_index()
        gp_series = qb_logs.groupby('passer_player_name')['game_id'].nunique()
        eligible_qbs = gp_series[gp_series >= min_gp].index
        
        for player in eligible_qbs:
            player_df = qb_logs[qb_logs['passer_player_name'] == player]
            team = player_df['posteam'].iloc[0]
            if team not in active_teams:
                continue
                
            opp = team_opp_map[team].replace("vs ", "").replace("@", "")
            opp_allowed = baselines['def_pass'].get(opp, l_pass)
            matchup_factor = round(opp_allowed / l_pass, 4)
            
            mean_yds = player_df['passing_yards'].mean()
            std_yds = player_df['passing_yards'].std()
            if np.isnan(std_yds) or std_yds < 15:
                std_yds = 35.0
                
            proj = round(mean_yds * matchup_factor, 1)
            z = (threshold_line - proj) / std_yds
            over_prob = round((1.0 - norm.cdf(z)) * 100, 1)
            fair_odds = prob_to_american_odds(over_prob / 100.0)
            
            matrix_rows.append({
                "Player": player,
                "Clean_Team": team,
                "Opponent": team_opp_map[team],
                "Baseline_Stat": round(mean_yds, 1),
                "Current_Stat": round(mean_yds, 1),
                "Matchup_Factor": matchup_factor,
                "Matchup_Proj": proj,
                "Model_Over_Prob_%": over_prob,
                "Fair_American_Odds": fair_odds,
                "Market": market,
                "Line": threshold_line
            })
            
    elif market == "Rushing Yards":
        rb_logs = df[df['rush_attempt'] == 1].groupby(['rusher_player_name', 'posteam', 'game_id'])['rushing_yards'].sum().reset_index()
        gp_series = rb_logs.groupby('rusher_player_name')['game_id'].nunique()
        eligible_rbs = gp_series[gp_series >= min_gp].index
        
        for player in eligible_rbs:
            player_df = rb_logs[rb_logs['rusher_player_name'] == player]
            team = player_df['posteam'].iloc[0]
            if team not in active_teams:
                continue
                
            opp = team_opp_map[team].replace("vs ", "").replace("@", "")
            opp_allowed = baselines['def_rush'].get(opp, l_rush)
            matchup_factor = round(opp_allowed / l_rush, 4)
            
            mean_yds = player_df['rushing_yards'].mean()
            std_yds = player_df['rushing_yards'].std()
            if np.isnan(std_yds) or std_yds < 10:
                std_yds = 18.0
                
            proj = round(mean_yds * matchup_factor, 1)
            z = (threshold_line - proj) / std_yds
            over_prob = round((1.0 - norm.cdf(z)) * 100, 1)
            fair_odds = prob_to_american_odds(over_prob / 100.0)
            
            matrix_rows.append({
                "Player": player,
                "Clean_Team": team,
                "Opponent": team_opp_map[team],
                "Baseline_Stat": round(mean_yds, 1),
                "Current_Stat": round(mean_yds, 1),
                "Matchup_Factor": matchup_factor,
                "Matchup_Proj": proj,
                "Model_Over_Prob_%": over_prob,
                "Fair_American_Odds": fair_odds,
                "Market": market,
                "Line": threshold_line
            })
            
    elif market == "Receiving Yards":
        wr_logs = df[df['pass_attempt'] == 1].groupby(['receiver_player_name', 'posteam', 'game_id'])['receiving_yards'].sum().reset_index()
        gp_series = wr_logs.groupby('receiver_player_name')['game_id'].nunique()
        eligible_wrs = gp_series[gp_series >= min_gp].index
        
        for player in eligible_wrs:
            player_df = wr_logs[wr_logs['receiver_player_name'] == player]
            team = player_df['posteam'].iloc[0]
            if team not in active_teams:
                continue
                
            opp = team_opp_map[team].replace("vs ", "").replace("@", "")
            opp_allowed = baselines['def_pass'].get(opp, l_pass)
            matchup_factor = round(opp_allowed / l_pass, 4)
            
            mean_yds = player_df['receiving_yards'].mean()
            std_yds = player_df['receiving_yards'].std()
            if np.isnan(std_yds) or std_yds < 10:
                std_yds = 20.0
                
            proj = round(mean_yds * matchup_factor, 1)
            z = (threshold_line - proj) / std_yds
            over_prob = round((1.0 - norm.cdf(z)) * 100, 1)
            fair_odds = prob_to_american_odds(over_prob / 100.0)
            
            matrix_rows.append({
                "Player": player,
                "Clean_Team": team,
                "Opponent": team_opp_map[team],
                "Baseline_Stat": round(mean_yds, 1),
                "Current_Stat": round(mean_yds, 1),
                "Matchup_Factor": matchup_factor,
                "Matchup_Proj": proj,
                "Model_Over_Prob_%": over_prob,
                "Fair_American_Odds": fair_odds,
                "Market": market,
                "Line": threshold_line
            })
            
    elif market == "Receptions":
        rec_logs = df[df['complete_pass'] == 1].groupby(['receiver_player_name', 'posteam', 'game_id'])['complete_pass'].sum().reset_index()
        gp_series = rec_logs.groupby('receiver_player_name')['game_id'].nunique()
        eligible_wrs = gp_series[gp_series >= min_gp].index
        
        for player in eligible_wrs:
            player_df = rec_logs[rec_logs['receiver_player_name'] == player]
            team = player_df['posteam'].iloc[0]
            if team not in active_teams:
                continue
                
            opp = team_opp_map[team].replace("vs ", "").replace("@", "")
            opp_allowed = baselines['def_pass'].get(opp, l_pass)
            matchup_factor = round(opp_allowed / l_pass, 4)
            
            mean_rec = player_df['complete_pass'].mean()
            lambda_val = mean_rec * matchup_factor
            k = int(np.floor(threshold_line))
            over_prob = round((1.0 - poisson.cdf(k, lambda_val)) * 100, 1)
            fair_odds = prob_to_american_odds(over_prob / 100.0)
            
            matrix_rows.append({
                "Player": player,
                "Clean_Team": team,
                "Opponent": team_opp_map[team],
                "Baseline_Stat": round(mean_rec, 1),
                "Current_Stat": round(mean_rec, 1),
                "Matchup_Factor": matchup_factor,
                "Matchup_Proj": round(lambda_val, 2),
                "Model_Over_Prob_%": over_prob,
                "Fair_American_Odds": fair_odds,
                "Market": market,
                "Line": threshold_line
            })
            
    elif market == "Anytime Touchdown Scorer":
        td_logs = df[df['touchdown'] == 1].groupby(['td_player_name', 'td_team', 'game_id'])['touchdown'].sum().reset_index()
        team_games = df.groupby('posteam')['game_id'].nunique()
        
        for player in td_logs['td_player_name'].unique():
            player_df = td_logs[td_logs['td_player_name'] == player]
            team = player_df['td_team'].iloc[0]
            if team not in active_teams:
                continue
                
            total_tds = player_df['touchdown'].sum()
            t_gp = team_games.get(team, 6)
            if t_gp < min_gp or total_tds < 1:
                continue
                
            opp = team_opp_map[team].replace("vs ", "").replace("@", "")
            opp_td_allowed = baselines['def_td'].get(opp, l_td)
            matchup_factor = round(opp_td_allowed / l_td, 4)
            
            base_lambda = total_tds / t_gp
            lambda_val = base_lambda * matchup_factor
            over_prob = round((1.0 - np.exp(-lambda_val)) * 100, 1)
            fair_odds = prob_to_american_odds(over_prob / 100.0)
            
            matrix_rows.append({
                "Player": player,
                "Clean_Team": team,
                "Opponent": team_opp_map[team],
                "Baseline_Stat": round(base_lambda, 2),
                "Current_Stat": round(base_lambda, 2),
                "Matchup_Factor": matchup_factor,
                "Matchup_Proj": round(lambda_val, 2),
                "Model_Over_Prob_%": over_prob,
                "Fair_American_Odds": fair_odds,
                "Market": market,
                "Line": 0.5
            })
            
    result_df = pd.DataFrame(matrix_rows)
    if not result_df.empty:
        result_df.sort_values(by="Model_Over_Prob_%", ascending=False, inplace=True)
        result_df.reset_index(drop=True, inplace=True)
    return result_df
