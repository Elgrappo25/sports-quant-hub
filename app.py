import streamlit as st
import pandas as pd
import requests
import math
from datetime import date

st.set_page_config(page_title="Sports Quant Hub - NHL Pro Terminal", page_icon="🏒", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #0e1117; }
        .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
        .stDataFrame { border-radius: 10px; overflow: hidden; }
    </style>
""", unsafe_allow_html=True)

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("### Count-based scaling, Poisson math, live Odds API line-shopping, and market-tailored color coding.")

# Sidebar for global settings & Live Props configuration
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=15, step=5)
min_gp = st.sidebar.slider("Minimum Current Season GP Filter", min_value=1, max_value=15, value=3, step=1)

st.sidebar.divider()
st.sidebar.header("🎯 Edge & Value Filters")
min_edge_filter = st.sidebar.slider("Min Edge Filter (%)", min_value=0.0, max_value=30.0, value=3.0, step=0.5)
max_edge_filter = st.sidebar.slider("Max Edge Filter (%)", min_value=5.0, max_value=70.0, value=25.0, step=1.0)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

st.sidebar.divider()
st.sidebar.header("🔌 Live Props & Line Shopping")
api_key_input = st.sidebar.text_input("Odds API Key", type="password", placeholder="Enter your API key here...")
available_books = ["draftkings", "fanduel", "betmgm", "betrivers", "espnbet", "bet365", "pinnacle"]
selected_books = st.sidebar.multiselect("Select Your Sportsbooks", available_books, default=["draftkings", "fanduel", "betmgm", "bet365", "betrivers", "pinnacle"])

# Helper functions for Poisson probability calculation
def poisson_prob(lam, k):
    if lam <= 0:
        return 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)

def poisson_over_prob(lam, threshold):
    k_min = int(math.floor(threshold)) + 1
    prob_under = sum(poisson_prob(lam, i) for i in range(k_min))
    return max(0.0, min(1.0, 1.0 - prob_under))

def prob_to_american(p):
    if p <= 0:
        return "+99999"
    if p >= 1:
        return "-99999"
    if p >= 0.5:
        dec = 1.0 / p
        return int(-100 / (dec - 1))
    else:
        dec = 1.0 / p
        return int((dec - 1) * 100)

def decimal_to_american(dec):
    if dec is None or dec <= 1.0:
        return "N/A"
    if dec >= 2.0:
        val = int((dec - 1) * 100)
        return f"+{val}"
    else:
        val = int(-100 / (dec - 1))
        return f"{val}"

# Navigation Tabs
tab1, tab2, tab3 = st.tabs([
    "📊 Automated +EV Prop Scanner", 
    "📁 Multi-File NST Uploader & Market Matrix", 
    "🚀 Boost & Parlay Optimizer"
])

with tab1:
    st.subheader("Automated +EV Slate Scanner & Line-Shopper")
    st.write("Scans live book props across standard & alternate endpoints, filtering out model glitches and matching against your Tab 2 model projections.")
    
    col_m1, col_m2 = st.columns([2, 1])
    api_market_choice = col_m1.selectbox(
        "Select Target Prop Market to Scan",
        [
            "player_points", 
            "player_shots_on_goal", 
            "player_goals", 
            "player_assists"
        ],
        format_func=lambda x: x.replace("player_", "").replace("_", " ").title()
    )
    
    fetch_all_btn = col_m2.button("🔄 Scan Slate & Calculate +EV", use_container_width=True)
    
    all_prop_rows = []
    if fetch_all_btn:
        if not api_key_input:
            st.error("⚠️ Please enter your Odds API Key in the sidebar first.")
        else:
            try:
                events_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events?apiKey={api_key_input}"
                events_resp = requests.get(events_url, timeout=8)
                if events_resp.status_code == 200:
                    events_list = events_resp.json()
                    books_str = ",".join(selected_books)
                    markets_to_query = f"{api_market_choice},{api_market_choice}_alternate"
                    
                    progress_bar = st.progress(0)
                    total_events = len(events_list)
                    
                    for idx, ev in enumerate(events_list):
                        ev_id = ev['id']
                        prop_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events/{ev_id}/odds?apiKey={api_key_input}&regions=us,us2&markets={markets_to_query}&bookmakers={books_str}"
                        resp = requests.get(prop_url, timeout=6)
                        if resp.status_code == 200:
                            game_data = resp.json()
                            for bookmaker in game_data.get('bookmakers', []):
                                b_title = bookmaker['title']
                                for market in bookmaker.get('markets', []):
                                    for outcome in market.get('outcomes', []):
                                        if outcome.get('name') == 'Over':
                                            all_prop_rows.append({
                                                "Sportsbook": b_title,
                                                "Player": outcome.get('description').strip(),
                                                "Line": float(outcome.get('point')),
                                                "Decimal Odds": outcome.get('price'),
                                                "Odds": decimal_to_american(outcome.get('price'))
                                            })
                        progress_bar.progress((idx + 1) / total_events)
                    
                    st.session_state['master_prop_slate'] = all_prop_rows
                    st.success(f"🟢 Successfully scanned all games! Found {len(all_prop_rows)} combined prop lines.")
                else:
                    st.warning(f"⚠️ API Error: Status {events_resp.status_code}")
            except Exception as e:
                st.warning(f"⚠️ Connection Failed: {e}")
    elif 'master_prop_slate' in st.session_state:
        all_prop_rows = st.session_state['master_prop_slate']

    if all_prop_rows:
        master_df = pd.DataFrame(all_prop_rows)
        
        # AIRTIGHT MAIN LINE FILTERING
        if "shots_on_goal" in api_market_choice:
            master_df = master_df[master_df['Line'].isin([1.5, 2.5, 3.5])]
        elif any(m in api_market_choice for m in ["points", "goals", "assists"]):
            master_df = master_df[master_df['Line'] == 0.5]

        # Merge with Tab 2 model data based on selected market category
        if 'raw_player_dfs' in st.session_state:
            curr_df, prev_df, team_factors = st.session_state['raw_player_dfs']
            
            if "shots" in api_market_choice:
                target_col = 'Shots'
            elif "points" in api_market_choice:
                target_col = 'Total Points'
            elif "goals" in api_market_choice:
                target_col = 'Goals'
            else:
                target_col = 'Total Assists'

            merged_model = pd.merge(curr_df, prev_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
            merged_model['Player'] = merged_model['Player'].astype(str).str.strip()
            
            merged_model['Stat_curr'] = pd.to_numeric(merged_model[f'{target_col}_curr'], errors='coerce').fillna(0)
            merged_model['Stat_prev'] = pd.to_numeric(merged_model[f'{target_col}_prev'], errors='coerce').fillna(0)
            
            gp_prev = pd.to_numeric(merged_model.get('GP_prev', 82), errors='coerce').replace(0, 1).fillna(82)
            gp_curr = pd.to_numeric(merged_model.get('GP_curr', 5), errors='coerce').replace(0, 1).fillna(5)
            
            merged_model = merged_model[gp_curr >= min_gp].copy()
            
            merged_model['Baseline_Stat'] = merged_model['Stat_prev'] / gp_prev
            merged_model['Current_Stat'] = merged_model['Stat_curr'] / gp_curr
            
            merged_model['Blended_Proj'] = (merged_model['Baseline_Stat'] * (1 - (season_weight / 100))) + (merged_model['Current_Stat'] * (season_weight / 100))
            
            nst_to_standard = {
                'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ',
                'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET',
                'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'MIN': 'MIN', 'MTL': 'MTL',
                'N.J': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI', 'NYR': 'NYR', 'OTT': 'OTT',
                'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS', 'SEA': 'SEA', 'STL': 'STL',
                'T.B': 'TBL', 'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK',
                'WPG': 'WPG', 'WSH': 'WSH'
            }
            def clean_team(t_str):
                if pd.isna(t_str): return 'UNK'
                t = str(t_str).split(',')[-1].strip()
                return nst_to_standard.get(t, t)
                
            merged_model['Clean_Team'] = merged_model['Team_curr'].apply(clean_team)
            merged_model['Matchup_Factor'] = merged_model['Clean_Team'].map(team_factors).fillna(1.0)
            merged_model['Matchup_Proj'] = merged_model['Blended_Proj'] * merged_model['Matchup_Factor']

            # Filter out zero projection glitches
            merged_model = merged_model[merged_model['Matchup_Proj'] > 0.1].copy()

            merged_scan = pd.merge(master_df, merged_model[['Player', 'Matchup_Proj']], on='Player', how='inner')
            
            if len(merged_scan) == 0:
                st.warning("⚠️ Player name mismatch between live odds and loaded CSVs.")
            else:
                def calc_row_prob(row):
                    return poisson_over_prob(row['Matchup_Proj'], row['Line'])
                    
                merged_scan['Model_Over_Prob'] = merged_scan.apply(calc_row_prob, axis=1)
                merged_scan['Model Over (%)'] = (merged_scan['Model_Over_Prob'] * 100).round(1)
                merged_scan['Fair Odds'] = merged_scan['Model_Over_Prob'].apply(lambda p: prob_to_american(p))
                
                def calc_edge(row):
                    dec = row['Decimal Odds']
                    if dec <= 1.0: return 0.0
                    implied = 1.0 / dec
                    return round((row['Model_Over_Prob'] - implied) * 100, 1)
                    
                merged_scan['Edge (%)'] = merged_scan.apply(calc_edge, axis=1)
                
                # Apply sidebar edge range filters
                merged_scan = merged_scan[(merged_scan['Edge (%)'] >= min_edge_filter) & (merged_scan['Edge (%)'] <= max_edge_filter)]
                merged_scan = merged_scan.sort_values(by='Edge (%)', ascending=False).reset_index(drop=True)
                
                # Summary Metrics Bar
                pos_ev_count = len(merged_scan)
                top_edge = merged_scan['Edge (%)'].max() if len(merged_scan) > 0 else 0.0
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Filtered Props", len(merged_scan))
                m2.metric("Props in Target Sweet Spot", pos_ev_count)
                m3.metric("Max Edge in Range", f"+{top_edge}%" if top_edge > 0 else f"{top_edge}%")
                
                st.divider()
                
                # INTERACTIVE PLAYER SEARCH BAR
                search_query = st.text_input("🔍 Search Player Name", placeholder="Type player name (e.g., McDavid, Martone)...").strip()
                if search_query:
                    merged_scan = merged_scan[merged_scan['Player'].str.contains(search_query, case=False, na=False)]
                
                st.write("### 🎯 Slate +EV Market Comparison Board:")
                
                display_scan = merged_scan[['Sportsbook', 'Player', 'Line', 'Odds', 'Matchup_Proj', 'Model Over (%)', 'Fair Odds', 'Edge (%)']].copy()
                display_scan.rename(columns={'Matchup_Proj': 'Proj Rate (λ)'}, inplace=True)
                
                def color_edge(val):
                    if val >= 5.0:
                        return 'color: #00E676; font-weight: bold;'
                    elif val < 0.0:
                        return 'color: #FF5252;'
                    return 'color: #CFD8DC;'
                    
                st.dataframe(
                    display_scan.style.map(color_edge, subset=['Edge (%)']),
                    use_container_width=True,
                    height=500
                )
        else:
            st.info("ℹ️ **Model Data Needed:** Please load your 4 Natural Stat Trick CSV files in **Tab 2** first so the terminal can correctly map stats for your selected market!")
            st.dataframe(master_df[['Sportsbook', 'Player', 'Line', 'Odds']], use_container_width=True, height=400)
    else:
        st.info("💡 **Instructions:** Select your target market above and click **Scan Slate & Calculate +EV** to pull live bookmaker props across all games.")

with tab2:
    st.subheader("Single Dropzone: Multi-File NST Processor & Market-Tailored Matrix")
    st.write("Drop your 4 Natural Stat Trick count files below. Color coding is custom-tailored to each specific betting market.")
    
    batch_market = st.selectbox(
        "Select Target Prop Market", 
        [
            "Shots on Goal (SOG)", 
            "Points (G+A)", 
            "Anytime Goal Scorer", 
            "Assists Only"
        ],
        key="multi_batch_market"
    )
    
    target_line_choice = st.selectbox(
        "Select Target Threshold Line for Alt Matrix",
        [0.5, 1.5, 2.5, 3.5, 4.5, 5.5],
        index=1,
        key="batch_alt_line"
    )
    
    target_date = st.date_input("Target Slate Date", value=date.today(), key="batch_target_date")
    
    uploaded_files = st.file_uploader(
        "Drop all 4 Natural Stat Trick CSV files here", 
        type="csv", 
        accept_multiple_files=True,
        key="multi_nst_drop"
    )
    
    if uploaded_files:
        curr_player_df, prev_player_df, curr_team_df, prev_team_df = None, None, None, None
        
        for file in uploaded_files:
            fname = file.name.lower()
            if "player" in fname:
                temp_df = pd.read_csv(file)
                if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20:
                    curr_player_df = temp_df
                else:
                    prev_player_df = temp_df
            elif "games" in fname:
                temp_df = pd.read_csv(file)
                if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20:
                    curr_team_df = temp_df
                else:
                    prev_team_df = temp_df
                
        if curr_player_df is not None and prev_player_df is not None:
            nst_to_standard = {
                'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ',
                'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET',
                'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'MIN': 'MIN', 'MTL': 'MTL',
                'N.J': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI', 'NYR': 'NYR', 'OTT': 'OTT',
                'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS', 'SEA': 'SEA', 'STL': 'STL',
                'T.B': 'TBL', 'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK',
                'WPG': 'WPG', 'WSH': 'WSH'
            }
            full_to_standard = {
                'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF',
                'Carolina Hurricanes': 'CAR', 'Columbus Blue Jackets': 'CBJ', 'Calgary Flames': 'CGY',
                'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL', 'Dallas Stars': 'DAL',
                'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA',
                'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL',
                'New Jersey Devils': 'NJD', 'Nashville Predators': 'NSH', 'New York Islanders': 'NYI',
                'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
                'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS', 'Seattle Kraken': 'SEA',
                'St Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
                'Utah Mammoth': 'UTA', 'Utah Hockey Club': 'UTA', 'Utah': 'UTA', 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK',
                'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH'
            }

            def clean_team(team_str):
                if pd.isna(team_str):
                    return 'UNK'
                parts = [p.strip() for p in str(team_str).split(',')]
                t = parts[-1]
                return nst_to_standard.get(t, t)

            active_teams = set()
            team_matchup_factors = {}
            team_opponents = {}
            
            try:
                sched_url = f"https://api-web.nhle.com/v1/schedule/{target_date.strftime('%Y-%m-%d')}"
                sched_resp = requests.get(sched_url).json()
                
                if curr_team_df is not None and 'Team' in curr_team_df.columns:
                    curr_team_df['Standard_Abbrev'] = curr_team_df['Team'].map(full_to_standard)
                    
                    if batch_market == "Shots on Goal (SOG)":
                        candidates = ['SA', 'CA', 'FA']
                    elif batch_market == "Anytime Goal Scorer":
                        candidates = ['HDCA', 'HDCF', 'CA']
                    else:
                        candidates = ['SCA', 'SCF', 'CA']
                        
                    stat_col = next((c for c in candidates if c in curr_team_df.columns), 'CA')
                    curr_team_df[stat_col] = pd.to_numeric(curr_team_df[stat_col], errors='coerce').fillna(0)
                        
                    mean_val = curr_team_df[stat_col].mean() if stat_col in curr_team_df.columns else 1.0
                    for _, row in curr_team_df.iterrows():
                        t_abbrev = row['Standard_Abbrev']
                        val = row.get(stat_col, mean_val)
                        factor = val / mean_val if mean_val > 0 else 1.0
                        if pd.notnull(t_abbrev):
                            team_matchup_factors[t_abbrev] = max(0.80, min(1.20, factor))

                for week_day in sched_resp.get("gameWeek", []):
                    if week_day.get("date") == target_date.strftime('%Y-%m-%d'):
                        for game in week_day.get("games", []):
                            away_abbrev = game.get("awayTeam", {}).get("abbrev")
                            home_abbrev = game.get("homeTeam", {}).get("abbrev")
                            if away_abbrev: active_teams.add(away_abbrev)
                            if home_abbrev: active_teams.add(home_abbrev)
                            
                            if away_abbrev and home_abbrev:
                                team_opponents[away_abbrev] = f"@{home_abbrev}"
                                team_opponents[home_abbrev] = f"vs {away_abbrev}"
            except Exception as e:
                st.warning(f"Schedule/Matchup fetch warning: {e}")

            if batch_market == "Shots on Goal (SOG)":
                target_col = 'Shots'
            elif batch_market == "Points (G+A)":
                target_col = 'Total Points'
            elif batch_market == "Anytime Goal Scorer":
                target_col = 'Goals'
            else:
                target_col = 'Total Assists'

            prev_col = target_col

            st.session_state['raw_player_dfs'] = (curr_player_df, prev_player_df, team_matchup_factors)

            merged_df = pd.merge(curr_player_df, prev_player_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
            merged_df['Clean_Team'] = merged_df['Team_curr'].apply(clean_team)
            
            merged_df['Stat_curr'] = pd.to_numeric(merged_df[f'{target_col}_curr'], errors='coerce').fillna(0)
            merged_df['Stat_prev'] = pd.to_numeric(merged_df[f'{prev_col}_prev'], errors='coerce').fillna(0)
            
            gp_prev = pd.to_numeric(merged_df.get('GP_prev', 82), errors='coerce').replace(0, 1).fillna(82)
            gp_curr = pd.to_numeric(merged_df.get('GP_curr', 5), errors='coerce').replace(0, 1).fillna(5)
            
            merged_df = merged_df[gp_curr >= min_gp].copy()
            
            merged_df['Baseline_Stat'] = merged_df['Stat_prev'] / gp_prev
            merged_df['Current_Stat'] = merged_df['Stat_curr'] / gp_curr
            
            merged_df['Blended_Proj'] = (merged_df['Baseline_Stat'] * (1 - (season_weight / 100))) + (merged_df['Current_Stat'] * (season_weight / 100))
            
            merged_df['Matchup_Factor'] = merged_df['Clean_Team'].map(team_matchup_factors).fillna(1.0)
            merged_df['Matchup_Proj'] = merged_df['Blended_Proj'] * merged_df['Matchup_Factor']
            merged_df['Opponent'] = merged_df['Clean_Team'].map(team_opponents).fillna("vs --")

            merged_df['Model_Over_Prob'] = merged_df['Matchup_Proj'].apply(lambda x: poisson_over_prob(x, target_line_choice))
            merged_df['Fair_American_Odds'] = merged_df['Model_Over_Prob'].apply(lambda p: f"{prob_to_american(p):+d}" if isinstance(prob_to_american(p), int) else prob_to_american(p))
            merged_df['Model_Over_Prob_%'] = (merged_df['Model_Over_Prob'] * 100).round(1)
            
            filter_slate = st.checkbox("Filter by Today's Active Slate Only", value=True)
            if filter_slate and active_teams and 'Clean_Team' in merged_df.columns:
                filtered_df = merged_df[merged_df['Clean_Team'].isin(active_teams)].copy()
                if len(filtered_df) > 0:
                    merged_df = filtered_df
                    st.success(f"📅 **Slate Filter Active:** Showing **{len(merged_df)} players** (min {min_gp} GP) playing on {target_date}.")
                else:
                    st.info("ℹ️ Showing full player pool (team abbreviation mismatch with API).")
            
            st.write(f"### 📈 Slate Alt-Line Matrix ({batch_market} > {target_line_choice}):")
            display_cols = ['Player', 'Clean_Team', 'Opponent', 'Baseline_Stat', 'Current_Stat', 'Matchup_Factor', 'Matchup_Proj', 'Model_Over_Prob_%', 'Fair_American_Odds']
            
            final_board = merged_df[display_cols].sort_values(by='Matchup_Proj', ascending=False).reset_index(drop=True)

            def color_matrix_cells(val, col_name):
                if isinstance(val, (int, float)):
                    if col_name == 'Matchup_Factor':
                        if val > 1.05:
                            return 'color: #00E676; font-weight: bold;'
                        elif val < 0.95:
                            return 'color: #FF5252; font-weight: bold;'
                    elif col_name == 'Model_Over_Prob_%':
                        if batch_market == "Anytime Goal Scorer":
                            green_thresh, red_thresh = 42.0, 32.0
                        elif batch_market == "Points (G+A)":
                            green_thresh, red_thresh = (72.0 if target_line_choice <= 0.5 else 45.0), 50.0
                        elif batch_market == "Assists Only":
                            green_thresh, red_thresh = (65.0 if target_line_choice <= 0.5 else 40.0), 45.0
                        else:
                            green_thresh, red_thresh = (55.0 if target_line_choice >= 2.5 else 75.0), 40.0
                            
                        if val >= green_thresh:
                            return 'color: #00E676; font-weight: bold;'
                        elif val <= red_thresh:
                            return 'color: #FF5252; font-weight: bold;'
                return 'color: #CFD8DC;'

            st.dataframe(
                final_board.style.map(lambda v: color_matrix_cells(v, 'Matchup_Factor'), subset=['Matchup_Factor'])
                           .map(lambda v: color_matrix_cells(v, 'Model_Over_Prob_%'), subset=['Model_Over_Prob_%']),
                use_container_width=True,
                height=500
            )
        else:
            st.warning("Please upload both Player Season Total CSV files.")
    else:
        st.info("💡 **Instructions:** Drop all 4 files above to generate color-coded alt-line projections.")

with tab3:
    st.subheader("🚀 Boost & Parlay Compound Optimizer")
    st.write("Test multi-leg slips and profit boosts to verify true expected value (+EV).")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        leg1_name = st.text_input("Leg 1 Player / Prop", value="McDavid Over 0.5 Assists", key="t3_l1_name")
        leg1_odds = st.number_input("Leg 1 American Odds", value=-110, step=5, key="t3_l1_odds")
    with col_p2:
        leg2_name = st.text_input("Leg 2 Player / Prop", value="Draisaitl Over 0.5 Points", key="t3_l2_name")
        leg2_odds = st.number_input("Leg 2 American Odds", value=130, step=5, key="t3_l2_odds")
        
    dec1 = 1 + (leg1_odds / 100) if leg1_odds > 0 else 1 + (100 / abs(leg1_odds))
    dec2 = 1 + (leg2_odds / 100) if leg2_odds > 0 else 1 + (100 / abs(leg2_odds))
    
    combined_parlay_dec = dec1 * dec2
    parlay_american = int((combined_parlay_dec - 1) * 100) if combined_parlay_dec >= 2 else int(-100 / (combined_parlay_dec - 1))
    
    boost_val = st.number_input("Apply Profit Boost to Parlay (%)", min_value=0, max_value=100, value=30, step=5, key="t3_boost")
    
    profit_factor = combined_parlay_dec - 1
    boosted_parlay_dec = 1 + (profit_factor * (1 + (boost_val / 100)))
    boosted_parlay_american = int((boosted_parlay_dec - 1) * 100) if boosted_parlay_dec >= 2 else int(-100 / (boosted_parlay_dec - 1))
    
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric(label="Standard 2-Leg Parlay Odds Feed", value=f"{parlay_american:+d}")
    col_res2.metric(label="Boosted Parlay Odds (+" + str(boosted_parlay_american) + "%)", value=f"{boosted_parlay_american:+d}")
    
    st.success("🎯 **Parlay Ready:** Combining **" + leg1_name + "** and **" + leg2_name + "** with a " + str(boost_val) + "% boost yields **" + str(boosted_parlay_american) + "** odds!")
