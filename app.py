import streamlit as st
import pandas as pd
import requests
import math
from datetime import date

st.set_page_config(page_title="Sports Quant Hub - NHL Pro Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("### Count-based scaling, Poisson math, live Odds API line-shopping, and market-tailored color coding.")

# Sidebar for global settings & Live Props configuration
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=15, step=5)
min_gp = st.sidebar.slider("Minimum Current Season GP Filter", min_value=1, max_value=15, value=3, step=1)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

st.sidebar.divider()
st.sidebar.header("🔌 Live Props & Line Shopping")
api_key_input = st.sidebar.text_input("Odds API Key", type="password", placeholder="Enter your API key here...")
available_books = ["draftkings", "fanduel", "betmgm", "betrivers", "espnbet", "bet365", "pinnacle"]
selected_books = st.sidebar.multiselect("Select Your Sportsbooks", available_books, default=["draftkings", "fanduel", "betmgm", "espnbet"])

# Helper function for Poisson probability calculation
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
    "📊 Live Player Prop Scanner & Valuator", 
    "📁 Multi-File NST Uploader & Market Matrix", 
    "🚀 Boost & Parlay Optimizer"
])

with tab1:
    st.subheader("Live Player Prop Line-Shopper & +EV Valuator")
    st.write("First, fetch today's active games, then select a game and market to pull live bookmaker props.")
    
    col_f1, col_f2 = st.columns([1, 3])
    fetch_events_btn = col_f1.button("🔄 Step 1: Load Today's Games")
    
    events_list = []
    if fetch_events_btn:
        if not api_key_input:
            st.error("⚠️ Please enter your Odds API Key in the sidebar first.")
        else:
            try:
                events_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events?apiKey={api_key_input}"
                resp = requests.get(events_url, timeout=8)
                if resp.status_code == 200:
                    events_list = resp.json()
                    st.session_state['events_list'] = events_list
                    st.success(f"🟢 Loaded {len(events_list)} active games!")
                else:
                    st.warning(f"⚠️ API Error: Status {resp.status_code}")
            except Exception as e:
                st.warning(f"⚠️ Connection Failed: {e}")
    elif 'events_list' in st.session_state:
        events_list = st.session_state['events_list']

    if events_list:
        st.divider()
        col_m1, col_m2, col_m3 = st.columns([2, 2, 1])
        
        event_options = {f"{e['away_team']} @ {e['home_team']} ({e['commence_time'][:10]})": e['id'] for e in events_list}
        selected_event_label = col_m1.selectbox("Select Game", list(event_options.keys()), key="prop_event_select")
        selected_event_id = event_options[selected_event_label]
        
        api_market_choice = col_m2.selectbox(
            "Select Prop Market",
            [
                "player_shots_on_goal", 
                "player_points", 
                "player_goals", 
                "player_assists",
                "player_shots_on_goal_alternate",
                "player_points_alternate"
            ],
            format_func=lambda x: x.replace("player_", "").replace("_", " ").title(),
            key="prop_market_select"
        )
        
        fetch_props_btn = col_m3.button("📥 Fetch Props")
        
        prop_data = None
        if fetch_props_btn:
            try:
                books_str = ",".join(selected_books)
                prop_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events/{selected_event_id}/odds?apiKey={api_key_input}&regions=us,us2&markets={api_market_choice}&bookmakers={books_str}"
                resp = requests.get(prop_url, timeout=10)
                if resp.status_code == 200:
                    prop_data = resp.json()
                    st.session_state[f'props_{selected_event_id}_{api_market_choice}'] = prop_data
                    st.success("🟢 Successfully pulled live props for this game!")
                else:
                    st.warning(f"⚠️ API Error: Status {resp.status_code} - Market may not be posted by books yet.")
            except Exception as e:
                st.warning(f"⚠️ Connection Failed: {e}")
        elif f'props_{selected_event_id}_{api_market_choice}' in st.session_state:
            prop_data = st.session_state[f'props_{selected_event_id}_{api_market_choice}']

        if prop_data:
            st.write(f"### 🏒 Live Prop Board for {selected_event_label}:")
            prop_rows = []
            for bookmaker in prop_data.get('bookmakers', []):
                b_title = bookmaker['title']
                for market in bookmaker.get('markets', []):
                    for outcome in market.get('outcomes', []):
                        if outcome.get('name') == 'Over':
                            prop_rows.append({
                                "Sportsbook": b_title,
                                "Player": outcome.get('description'),
                                "Line": outcome.get('point'),
                                "Over Odds": decimal_to_american(outcome.get('price'))
                            })
            if prop_rows:
                st.dataframe(pd.DataFrame(prop_rows), use_container_width=True, height=450)
            else:
                st.info("ℹ️ No player prop lines currently posted for this specific market/game combination.")

    st.divider()
    st.write("### 🧮 Single Prop +EV Valuator")
    col1, col2, col3 = st.columns(3)

    with col1:
        player_name = st.text_input("Player Name", value="Connor McDavid", key="tab1_player")
        market_type = st.selectbox(
            "Market Type", 
            [
                "Shots on Goal (SOG)", 
                "Points (G+A)", 
                "Anytime Goal Scorer", 
                "Assists Only"
            ],
            key="tab1_market"
        )

    if market_type == "Shots on Goal (SOG)":
        default_base, default_curr, default_line, default_odds = 3.74, 2.29, 3.5, -120
    elif market_type == "Points (G+A)":
        default_base, default_curr, default_line, default_odds = 1.68, 2.57, 1.5, +115
    elif market_type == "Anytime Goal Scorer":
        default_base, default_curr, default_line, default_odds = 0.58, 0.57, 0.5, +135
    else:  # Assists Only
        default_base, default_curr, default_line, default_odds = 1.10, 1.71, 0.5, -110

    with col2:
        baseline_stat = st.number_input("Multi-Year Baseline / Game", value=default_base, step=0.05, key="tab1_base")
        current_stat = st.number_input("Current Season Stat / Game", value=default_curr, step=0.05, key="tab1_curr")

    with col3:
        alt_line_input = st.number_input("Target Alt / Book Line (e.g. 0.5, 1.5, 3.5)", value=default_line, step=0.5, key="tab1_line")
        sportsbook_odds = st.number_input("Book Odds Offered (American)", value=default_odds, step=5, key="tab1_odds")

    blended_projection = (baseline_stat * (1 - (season_weight / 100))) + (current_stat * (season_weight / 100))
    over_prob = poisson_over_prob(blended_projection, alt_line_input)
    fair_american = prob_to_american(over_prob)

    st.markdown(f"### 📈 Poisson Model Output: {market_type} (Over {alt_line_input})")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric(label="Blended Rate (Lambda)", value=f"{blended_projection:.2f}")
    col_b.metric(label="Model Over Probability", value=f"{over_prob * 100:.1f}%")
    col_c.metric(label="Model Fair Odds", value=f"{fair_american:+d}" if isinstance(fair_american, int) else fair_american)

    if sportsbook_odds > 0:
        dec_odds = 1 + (sportsbook_odds / 100)
    else:
        dec_odds = 1 + (100 / abs(sportsbook_odds))

    implied_book_prob = 1 / dec_odds
    edge_percentage = (over_prob - implied_book_prob) * 100
    col_d.metric(label="Model vs Book Edge", value=f"{edge_percentage:+.1f}%")

    if edge_percentage > 3.0:
        st.success(f"✅ **Strong +EV Play Found:** Model probability ({over_prob*100:.1f}%) significantly outpaces book implied probability ({implied_book_prob*100:.1f}%).")
    elif edge_percentage < -3.0:
        st.warning(f"⚠️ **Negative EV / Pass:** Book price is too sharp compared to model expectation.")
    else:
        st.info("ℹ️ **Fairly Priced:** Market odds are closely aligned with Poisson model probability.")

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
                
                team_stat_dict = {}
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

            # Calculate Poisson Probabilities and Fair Odds
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
    col_res2.metric(label="Boosted Parlay Odds (+" + str(boost_val) + "%)", value=f"{boosted_parlay_american:+d}")
    
    st.success("🎯 **Parlay Ready:** Combining **" + leg1_name + "** and **" + leg2_name + "** with a " + str(boost_val) + "% boost yields **" + str(boosted_parlay_american) + "** odds!")
