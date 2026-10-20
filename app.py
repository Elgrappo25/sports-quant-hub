import streamlit as st
import pandas as pd
import requests
import math
from datetime import date
import itertools

st.set_page_config(page_title="Sports Quant Hub - Multi-Sport Terminal", page_icon="🏒", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #0e1117; }
        .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
        .stDataFrame { border-radius: 10px; overflow: hidden; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# MASTER SPORT SELECTOR
# ==========================================
st.sidebar.header("🏆 Master Sport Terminal")
active_sport = st.sidebar.selectbox(
    "Select Active Sport", 
    ["🏒 NHL (Active)", "🏈 NFL (Paused)"],
    key="master_sport_switch"
)
st.sidebar.divider()

# ==========================================
# DYNAMIC SPORT-SPECIFIC SIDEBAR CONTROLS
# ==========================================
if "NHL" in active_sport:
    st.sidebar.header("⚙️ NHL Model Settings")
    season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=15, step=5)
    min_gp = st.sidebar.slider("Minimum Current Season GP Filter", min_value=1, max_value=15, value=3, step=1)
    st.sidebar.divider()
else:
    season_weight, min_gp = 0, 0

# Global Settings Shared Across Both Sports
st.sidebar.header("🎯 Market-Tailored Edge Filters")
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

st.sidebar.divider()
st.sidebar.header("🔌 Live Props & Line Shopping")
available_books = ["FanDuel", "DraftKings", "BetMGM", "Bet365", "BetRivers", "ESPN BET", "Pinnacle"]

# Shared Math Functions
def poisson_prob(lam, k):
    if lam <= 0: return 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)

def poisson_over_prob(lam, threshold):
    k_min = int(math.floor(threshold)) + 1
    prob_under = sum(poisson_prob(lam, i) for i in range(k_min))
    return max(0.0, min(1.0, 1.0 - prob_under))

def prob_to_american(p):
    if p <= 0: return "+99999"
    if p >= 1: return "-99999"
    if p >= 0.5:
        dec = 1.0 / p
        return int(-100 / (dec - 1))
    else:
        dec = 1.0 / p
        return int((dec - 1) * 100)

def american_to_decimal(am_odds):
    if am_odds > 0:
        return 1.0 + (am_odds / 100.0)
    else:
        return 1.0 + (100.0 / abs(am_odds))

def decimal_to_american(dec):
    if dec is None or dec <= 1.0: return "N/A"
    if dec >= 2.0:
        val = int((dec - 1) * 100)
        return f"+{val}"
    else:
        val = int(-100 / (dec - 1))
        return f"{val}"

# ==============================================================================
# HOCKEY (NHL) PIPELINE
# ==============================================================================
if "NHL" in active_sport:
    st.title("🏒 NHL Quant Terminal: Production Suite")
    st.markdown("### Multi-Market Accumulator, NST Matchup Projections, and Compound Parlay Generator.")

    tab1, tab2 = st.tabs([
        "📊 Checked Slips & Nexus Odds Comparator", 
        "📁 Multi-File NST Uploader & Master Slate Matrix"
    ])

    team_to_abbrev = {
        'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF',
        'Carolina Hurricanes': 'CAR', 'Columbus Blue Jackets': 'CBJ', 'Calgary Flames': 'CGY',
        'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL', 'Dallas Stars': 'DAL',
        'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA',
        'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL',
        'New Jersey Devils': 'NJD', 'Nashville Predators': 'NSH', 'New York Islanders': 'NYI',
        'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
        'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS', 'Seattle Kraken': 'SEA',
        'St Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
        'Utah Mammoth': 'UTA', 'Utah Hockey Club': 'UTA', 'Utah': 'UTA', 'Vancouver Canucks': 'VAN',
        'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH',
        'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ',
        'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET',
        'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'LAK': 'LAK', 'MIN': 'MIN',
        'MTL': 'MTL', 'N.J': 'NJD', 'NJD': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI',
        'NYR': 'NYR', 'OTT': 'OTT', 'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS',
        'SJS': 'SJS', 'SEA': 'SEA', 'STL': 'STL', 'T.B': 'TBL', 'TBL': 'TBL',
        'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK', 'WPG': 'WPG', 'WSH': 'WSH'
    }

    if 'bet_slip_queue' not in st.session_state:
        st.session_state['bet_slip_queue'] = []

    with tab1:
        st.subheader("📝 Checked Players & Nexus Odds Comparator")
        st.write("Type your Nexus Odds in the table. Real-time edges and compound parlay odds calculate live below.")

        col_clr1, col_clr2 = st.columns([4, 1])
        if col_clr2.button("🗑️ Clear Bet Slip", use_container_width=True):
            st.session_state['bet_slip_queue'] = []
            st.rerun()

        if len(st.session_state['bet_slip_queue']) > 0:
            queue_data = st.session_state['bet_slip_queue']
            
            display_rows = []
            for item in queue_data:
                display_rows.append({
                    "Include": item.get('Include', True),
                    "Sportsbook": item.get('Sportsbook', "FanDuel"),
                    "Player": item['Player'],
                    "Opponent": item['Opponent'],
                    "Market": item['Market'],
                    "Line": float(item['Line']),
                    "Nexus Odds (+/-)": item.get('Nexus Odds (+/-)', None),
                    "Model Prob (%)": item['Model_Over_Prob_%'],
                    "Delete": False
                })
            
            df_slip = pd.DataFrame(display_rows)
            
            edited_df = st.data_editor(
                df_slip,
                use_container_width=True,
                height=300,
                key="unified_bet_slip_editor",
                column_config={
                    "Include": st.column_config.CheckboxColumn("Include in Parlay", default=True),
                    "Sportsbook": st.column_config.SelectboxColumn("Sportsbook", options=available_books, required=True),
                    "Player": st.column_config.TextColumn("Player", disabled=True),
                    "Opponent": st.column_config.TextColumn("Opponent", disabled=True),
                    "Market": st.column_config.TextColumn("Market", disabled=True),
                    "Line": st.column_config.NumberColumn("Line", disabled=True, format="%.1f"),
                    "Nexus Odds (+/-)": st.column_config.NumberColumn("Nexus Odds (+/-)", help="Enter American odds e.g. -200 or 115", format="%d", step=1),
                    "Model Prob (%)": st.column_config.NumberColumn("Model Prob (%)", disabled=True, format="%.1f%%"),
                    "Delete": st.column_config.CheckboxColumn("Delete", help="Check to remove this leg", default=False)
                }
            )
            
            to_delete_indices = [i for i, row in edited_df.iterrows() if row['Delete']]
            if to_delete_indices:
                st.session_state['bet_slip_queue'] = [
                    item for i, item in enumerate(st.session_state['bet_slip_queue']) if i not in to_delete_indices
                ]
                st.rerun()

            for i, row in edited_df.iterrows():
                if i < len(st.session_state['bet_slip_queue']):
                    st.session_state['bet_slip_queue'][i]['Sportsbook'] = row['Sportsbook']
                    st.session_state['bet_slip_queue'][i]['Nexus Odds (+/-)'] = row['Nexus Odds (+/-)']
                    st.session_state['bet_slip_queue'][i]['Include'] = row['Include']

            evaluated_legs = []
            for i, row in edited_df.iterrows():
                odds_val = row['Nexus Odds (+/-)']
                if odds_val is not None and not pd.isna(odds_val) and int(odds_val) != 0:
                    am_odds = int(odds_val)
                    dec_odds = american_to_decimal(am_odds)
                    true_prob = float(row['Model Prob (%)']) / 100.0
                    edge_num = round((true_prob - (1.0 / dec_odds)) * 100, 1)
                    evaluated_legs.append({
                        "Include": row['Include'],
                        "Sportsbook": row['Sportsbook'],
                        "Player": row['Player'],
                        "Opponent": row['Opponent'],
                        "Market": row['Market'],
                        "Line": row['Line'],
                        "Odds": f"{am_odds:+d}" if am_odds > 0 else f"{am_odds}",
                        "Decimal Odds": dec_odds,
                        "Model Prob": f"{round(true_prob * 100, 1)}%",
                        "True Prob": true_prob,
                        "Edge %": edge_num
                    })

            if evaluated_legs:
                eval_df = pd.DataFrame(evaluated_legs)
                st.write("### 📈 Live Edge Evaluation:")
                
                def format_edge(val):
                    return f"+{val}%" if val > 0 else f"{val}%"
                
                disp_eval = eval_df[['Sportsbook', 'Player', 'Opponent', 'Market', 'Line', 'Odds', 'Model Prob', 'Edge %']].copy()
                disp_eval['Edge %'] = disp_eval['Edge %'].apply(format_edge)
                st.dataframe(disp_eval, use_container_width=True)

                parlay_legs = [leg for leg in evaluated_legs if leg['Include']]
                if len(parlay_legs) > 0:
                    st.subheader("🚀 Live Compound Slip & Profit Boost Calculator")
                    
                    comb_dec = 1.0
                    comb_prob = 1.0
                    for leg in parlay_legs:
                        comb_dec *= leg['Decimal Odds']
                        comb_prob *= leg['True Prob']
                    
                    std_am = int((comb_dec - 1) * 100) if comb_dec >= 2.0 else int(-100 / (comb_dec - 1))
                    b_dec = 1 + ((comb_dec - 1) * (1 + (global_boost / 100.0)))
                    b_am = int((b_dec - 1) * 100) if b_dec >= 2.0 else int(-100 / (b_dec - 1))
                    
                    active_dec = b_dec if global_boost > 0 else comb_dec
                    slip_edge = round((comb_prob - (1.0 / active_dec)) * 100, 1)
                    
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("Checked Parlay Odds", f"+{std_am}" if std_am > 0 else f"{std_am}")
                    r2.metric(f"Boosted (+{global_boost}%)", f"+{b_am}" if b_am > 0 else f"{b_am}")
                    r3.metric("Model Slip True Prob", f"{round(comb_prob * 100, 1)}%")
                    r4.metric("Compound Slip Edge", f"+{slip_edge}%" if slip_edge > 0 else f"{slip_edge}%")
            else:
                st.info("✍️ **Enter Odds:** Type your lines under `Nexus Odds (+/-)` above. Live individual edges and parlay metrics will calculate instantly.")
        else:
            st.info("💡 **Instructions:** Go to **Tab 2**, select your market and line, check your desired players, and click **'➕ Add Checked to Bet Slip'**.")

    with tab2:
        st.subheader("Single Dropzone: Multi-File NST Processor & Master Slate Matrix")
        st.write("Drop your 4 Natural Stat Trick count files below. Your probabilities and matchup factors are strictly preserved.")
        
        batch_market = st.selectbox(
            "Select Target Prop Market", 
            ["Shots on Goal (SOG)", "Points (G+A)", "Anytime Goal Scorer", "Assists Only"],
            key="multi_batch_market_nex"
        )
        target_line_choice = st.selectbox(
            "Select Target Threshold Line",
            [0.5, 1.5, 2.5, 3.5, 4.5, 5.5],
            index=1,
            key="batch_alt_line_nex"
        )
        target_date = st.date_input("Target Slate Date", value=date.today(), key="batch_target_date_nex")
        
        uploaded_files = st.file_uploader(
            "Drop all 4 Natural Stat Trick CSV files here", 
            type="csv", 
            accept_multiple_files=True,
            key="multi_nst_drop_nex"
        )
        
        if uploaded_files:
            curr_player_df, prev_player_df, curr_team_df, prev_team_df = None, None, None, None
            for file in uploaded_files:
                fname = file.name.lower()
                if "player" in fname:
                    temp_df = pd.read_csv(file)
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_player_df = temp_df
                    else: prev_player_df = temp_df
                elif "games" in fname:
                    temp_df = pd.read_csv(file)
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_team_df = temp_df
                    else: prev_team_df = temp_df
                    
            if curr_player_df is not None and prev_player_df is not None:
                active_teams = set()
                team_matchup_factors = {}
                team_opponents_raw = {}
                team_opponents_display = {}
                raw_game_pairs = []
                
                try:
                    sched_resp = requests.get(f"https://api-web.nhle.com/v1/schedule/{target_date.strftime('%Y-%m-%d')}").json()
                    if curr_team_df is not None and 'Team' in curr_team_df.columns:
                        curr_team_df['Standard_Abbrev'] = curr_team_df['Team'].map(team_to_abbrev)
                        stat_col = 'SA' if batch_market == "Shots on Goal (SOG)" else ('HDCA' if batch_market == "Anytime Goal Scorer" else 'SCA')
                        if stat_col not in curr_team_df.columns: stat_col = 'CA'
                        curr_team_df[stat_col] = pd.to_numeric(curr_team_df[stat_col], errors='coerce').fillna(0)
                        curr_team_df['GP_numeric'] = pd.to_numeric(curr_team_df['GP'], errors='coerce').fillna(1)
                        curr_team_df['Stat_Per_Game'] = curr_team_df[stat_col] / curr_team_df['GP_numeric']
                        mean_val = curr_team_df['Stat_Per_Game'].mean() if len(curr_team_df) > 0 else 1.0
                        for _, row in curr_team_df.iterrows():
                            t_abbrev = row['Standard_Abbrev']
                            val = row.get('Stat_Per_Game', mean_val)
                            factor = val / mean_val if mean_val > 0 else 1.0
                            if pd.notnull(t_abbrev): team_matchup_factors[t_abbrev] = max(0.80, min(1.20, factor))

                    for week_day in sched_resp.get("gameWeek", []):
                        if week_day.get("date") == target_date.strftime('%Y-%m-%d'):
                            for game in week_day.get("games", []):
                                away = game.get("awayTeam", {}).get("abbrev")
                                home = game.get("homeTeam", {}).get("abbrev")
                                if away: active_teams.add(away)
                                if home: active_teams.add(home)
                                if away and home:
                                    raw_game_pairs.append((away, home))
                                    team_opponents_raw[away] = home
                                    team_opponents_raw[home] = away
                                    team_opponents_display[away] = f"@{home}"
                                    team_opponents_display[home] = f"vs {away}"
                except Exception as e:
                    pass

                # Build Sorted Matchup Labels with Combined Factors Embedded
                scored_matchups = []
                for away, home in raw_game_pairs:
                    # Away team faces Home defense (team_matchup_factors[home])
                    # Home team faces Away defense (team_matchup_factors[away])
                    factor_away_faces = team_matchup_factors.get(home, 1.0)
                    factor_home_faces = team_matchup_factors.get(away, 1.0)
                    comb_factor = round(factor_away_faces + factor_home_faces, 2)
                    
                    flame_icon = " 🔥" if comb_factor >= 2.15 else ""
                    label = f"{away} @ {home} [{comb_factor}{flame_icon}]"
                    scored_matchups.append((comb_factor, label, away, home))
                
                # Sort descending: Highest combined chaos games at the top
                scored_matchups.sort(key=lambda x: x[0], reverse=True)
                available_matchups = [m[1] for m in scored_matchups]

                target_col = 'Shots' if batch_market == "Shots on Goal (SOG)" else ('Total Points' if batch_market == "Points (G+A)" else ('Goals' if batch_market == "Anytime Goal Scorer" else 'Total Assists'))
                prev_col = target_col

                st.session_state['raw_player_dfs'] = (curr_player_df, prev_player_df, team_matchup_factors, team_opponents_raw)

                merged_df = pd.merge(curr_player_df, prev_player_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
                
                def clean_team(t_str):
                    if pd.isna(t_str): return 'UNK'
                    raw = str(t_str).split(',')[-1].strip()
                    return team_to_abbrev.get(raw, raw)

                merged_df['Clean_Team'] = merged_df['Team_curr'].apply(clean_team)
                
                merged_df['Stat_curr'] = pd.to_numeric(merged_df[f'{target_col}_curr'], errors='coerce').fillna(0)
                merged_df['Stat_prev'] = pd.to_numeric(merged_df[f'{prev_col}_prev'], errors='coerce').fillna(0)
                
                gp_prev = 82
                gp_curr = pd.to_numeric(merged_df.get('GP_curr', 5), errors='coerce').replace(0, 1).fillna(5)
                
                merged_df = merged_df[gp_curr >= min_gp].copy()
                
                merged_df['Baseline_Stat'] = merged_df['Stat_prev'] / gp_prev
                merged_df['Current_Stat'] = merged_df['Stat_curr'] / gp_curr
                merged_df['Blended_Proj'] = (merged_df['Baseline_Stat'] * (1 - (season_weight / 100))) + (merged_df['Current_Stat'] * (season_weight / 100))
                
                def get_matrix_opp_factor(row):
                    team = row['Clean_Team']
                    opp_abbrev = team_opponents_raw.get(team, None)
                    if opp_abbrev and opp_abbrev in team_matchup_factors:
                        return team_matchup_factors[opp_abbrev]
                    return 1.0

                merged_df['Matchup_Factor'] = merged_df.apply(get_matrix_opp_factor, axis=1)
                merged_df['Matchup_Proj'] = merged_df['Blended_Proj'] * merged_df['Matchup_Factor']
                merged_df['Opponent'] = merged_df['Clean_Team'].map(team_opponents_display).fillna("vs --")
                
                if active_teams and 'Clean_Team' in merged_df.columns:
                    merged_df = merged_df[merged_df['Clean_Team'].isin(active_teams)].copy()

                st.divider()
                if available_matchups:
                    selected_games_filter = st.multiselect(
                        "🎯 Filter Specific Game Matchups (Sorted by Combined Factor)",
                        available_matchups,
                        default=available_matchups,
                        key=f"game_matchup_multiselect_{batch_market}"
                    )
                    if selected_games_filter:
                        active_filtered_teams = set()
                        for m_lbl in selected_games_filter:
                            clean_m = m_lbl.split(" [")[0].strip()
                            parts = clean_m.split(" @ ")
                            if len(parts) == 2:
                                active_filtered_teams.add(parts[0].strip())
                                active_filtered_teams.add(parts[1].strip())
                        merged_df = merged_df[merged_df['Clean_Team'].isin(active_filtered_teams)].copy()

                merged_df['Model_Over_Prob'] = merged_df['Matchup_Proj'].apply(lambda x: poisson_over_prob(x, target_line_choice))
                merged_df['Fair_American_Odds'] = merged_df['Model_Over_Prob'].apply(lambda p: f"{prob_to_american(p):+d}" if isinstance(prob_to_american(p), int) else prob_to_american(p))
                merged_df['Model_Over_Prob_%'] = (merged_df['Model_Over_Prob'] * 100).round(1)

                merged_df['Weighted_Matchup_Score'] = merged_df['Matchup_Proj'] * (merged_df['Matchup_Factor'] ** 1.5)
                
                st.success(f"📅 **Active Matrix Filter:** Showing **{len(merged_df)} players** across selected games on {target_date}.")
                
                st.write(f"### 📈 Slate Alt-Line Matrix ({batch_market} > {target_line_choice}):")
                display_cols = ['Player', 'Clean_Team', 'Opponent', 'Baseline_Stat', 'Current_Stat', 'Matchup_Factor', 'Matchup_Proj', 'Model_Over_Prob_%', 'Fair_American_Odds']
                
                final_board = merged_df[display_cols].sort_values(by='Matchup_Proj', ascending=False).reset_index(drop=True)
                final_board.insert(0, 'Select', False)

                def color_matrix_cells(val, col_name):
                    if isinstance(val, (int, float)):
                        if col_name == 'Matchup_Factor':
                            if val > 1.05: return 'color: #00E676; font-weight: bold;'
                            elif val < 0.95: return 'color: #FF5252; font-weight: bold;'
                        elif col_name == 'Model_Over_Prob_%':
                            if batch_market == "Anytime Goal Scorer": green_thresh, red_thresh = 42.0, 32.0
                            elif batch_market == "Points (G+A)": green_thresh, red_thresh = (72.0 if target_line_choice <= 0.5 else 45.0), 50.0
                            elif batch_market == "Assists Only": green_thresh, red_thresh = (65.0 if target_line_choice <= 0.5 else 40.0), 45.0
                            else: green_thresh, red_thresh = (55.0 if target_line_choice >= 2.5 else 75.0), 40.0
                            
                            if val >= green_thresh: return 'color: #00E676; font-weight: bold;'
                            elif val <= red_thresh: return 'color: #FF5252; font-weight: bold;'
                    return 'color: #CFD8DC;'

                edited_matrix = st.data_editor(
                    final_board,
                    use_container_width=True,
                    height=500,
                    key=f"matrix_editor_{batch_market}_{target_line_choice}"
                )

                btn_col1, btn_col2 = st.columns(2)
                add_to_slip_btn = btn_col1.button("➕ Add Checked Players to Bet Slip", use_container_width=True)
                autoload_top5_btn = btn_col2.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs", use_container_width=True)

                if add_to_slip_btn:
                    checked_matrix_rows = edited_matrix[edited_matrix['Select'] == True]
                    if len(checked_matrix_rows) > 0:
                        existing_keys = {(r['Player'], r['Market'], float(r['Line'])) for r in st.session_state['bet_slip_queue']}
                        
                        for _, cr in checked_matrix_rows.iterrows():
                            p_name = cr['Player']
                            item_key = (p_name, batch_market, float(target_line_choice))
                            if item_key not in existing_keys:
                                p_match = merged_df[merged_df['Player'] == p_name]
                                if len(p_match) > 0:
                                    p_proj = p_match.iloc[0]['Matchup_Proj']
                                    p_prob = poisson_over_prob(p_proj, target_line_choice)
                                    st.session_state['bet_slip_queue'].append({
                                        'Player': p_name,
                                        'Clean_Team': cr['Clean_Team'],
                                        'Opponent': cr['Opponent'],
                                        'Market': batch_market,
                                        'Line': float(target_line_choice),
                                        'Matchup_Proj': p_proj,
                                        'Model_Over_Prob': p_prob,
                                        'Model_Over_Prob_%': round(p_prob * 100, 1),
                                        'Sportsbook': 'FanDuel',
                                        'Nexus Odds (+/-)': None,
                                        'Include': True
                                    })
                        st.rerun()
                    else:
                        st.warning("⚠️ Please check at least one player in the table first.")

                if autoload_top5_btn:
                    top5_candidates = merged_df.sort_values(by='Weighted_Matchup_Score', ascending=False).head(5)
                    existing_keys = {(r['Player'], r['Market'], float(r['Line'])) for r in st.session_state['bet_slip_queue']}
                    
                    for _, row in top5_candidates.iterrows():
                        p_name = row['Player']
                        item_key = (p_name, batch_market, float(target_line_choice))
                        if item_key not in existing_keys:
                            p_proj = row['Matchup_Proj']
                            p_prob = poisson_over_prob(p_proj, target_line_choice)
                            st.session_state['bet_slip_queue'].append({
                                'Player': p_name,
                                'Clean_Team': row['Clean_Team'],
                                'Opponent': row['Opponent'],
                                'Market': batch_market,
                                'Line': float(target_line_choice),
                                'Matchup_Proj': p_proj,
                                'Model_Over_Prob': p_prob,
                                'Model_Over_Prob_%': round(p_prob * 100, 1),
                                'Sportsbook': 'FanDuel',
                                'Nexus Odds (+/-)': None,
                                'Include': True
                            })
                    st.rerun()
            else:
                st.warning("Please upload both Player Season Total CSV files.")
        else:
            st.info("💡 **Instructions:** Drop all 4 files above to generate color-coded alt-line projections.")

# ==============================================================================
# FOOTBALL (NFL) PLACEHOLDER
# ==============================================================================
elif "NFL" in active_sport:
    st.title("🏈 NFL Quant Terminal: Paused")
    st.markdown("### Focus is currently locked on your production NHL terminal for tonight's slate.")
