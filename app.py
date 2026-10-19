import streamlit as st
import pandas as pd
import requests
import math
from datetime import date
import itertools

st.set_page_config(page_title="Sports Quant Hub - Multi-Sport Terminal", page_icon="🏆", layout="wide")

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
    ["🏒 NHL (Active)", "🏈 NFL (NST-Style Terminal)"],
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
api_key_input = st.sidebar.text_input("Odds API Key", type="password", placeholder="Enter your API key here...")
available_books = ["draftkings", "fanduel", "betmgm", "bet365", "betrivers", "espnbet", "pinnacle"]
selected_books = st.sidebar.multiselect("Select Your Sportsbooks", available_books, default=["draftkings", "fanduel", "betmgm", "bet365", "betrivers", "pinnacle", "espnbet"])

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

def decimal_to_american(dec):
    if dec is None or dec <= 1.0: return "N/A"
    if dec >= 2.0:
        val = int((dec - 1) * 100)
        return f"+{val}"
    else:
        val = int(-100 / (dec - 1))
        return f"{val}"

def clean_book_title(title):
    t_lower = str(title).lower()
    if "espn" in t_lower or "score" in t_lower: return "ESPN BET"
    elif "draftkings" in t_lower: return "DraftKings"
    elif "fanduel" in t_lower: return "FanDuel"
    elif "betmgm" in t_lower: return "BetMGM"
    elif "bet365" in t_lower: return "Bet365"
    elif "betrivers" in t_lower: return "BetRivers"
    elif "pinnacle" in t_lower: return "Pinnacle"
    return title.title()


# ==============================================================================
# HOCKEY (NHL) PIPELINE
# ==============================================================================
if "NHL" in active_sport:
    st.title("🏒 NHL Quant Terminal: Production Suite")
    st.markdown("### Multi-market batch scanning, slate date filtering, Poisson math, and automated +EV parlay generation.")

    tab1, tab2 = st.tabs([
        "📊 Automated +EV Prop Scanner & Slip Builder", 
        "📁 Multi-File NST Uploader & Market Matrix"
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
        'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH'
    }

    def compact_matchup(matchup_str):
        if " @ " in matchup_str:
            away, home = matchup_str.split(" @ ")
            away_code = team_to_abbrev.get(away.strip(), away.strip()[:3].upper())
            home_code = team_to_abbrev.get(home.strip(), home.strip()[:3].upper())
            return f"{away_code} @ {home_code}"
        return matchup_str

    with tab1:
        col_scan1, col_scan2 = st.columns([2, 1])
        target_scan_date = col_scan1.date_input("📅 Target Slate Date Filter", value=date.today())
        fetch_all_btn = col_scan2.button("🔄 Batch Scan All Markets", use_container_width=True)
        
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
                        batch_markets = "player_points,player_shots_on_goal,player_goals,player_assists,player_shots_on_goal_alternate,player_points_alternate"
                        
                        progress_bar = st.progress(0)
                        total_events = len(events_list)
                        scanned_games_count = 0
                        target_date_str = target_scan_date.strftime('%Y-%m-%d')

                        for idx, ev in enumerate(events_list):
                            ev_commence = ev.get('commence_time', '')
                            if target_date_str not in ev_commence: continue
                                
                            scanned_games_count += 1
                            ev_id = ev['id']
                            matchup_str = f"{ev['away_team']} @ {ev['home_team']}"
                            
                            prop_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events/{ev_id}/odds?apiKey={api_key_input}&regions=us,us2&markets={batch_markets}&bookmakers={books_str}"
                            resp = requests.get(prop_url, timeout=6)
                            if resp.status_code == 200:
                                game_data = resp.json()
                                for bookmaker in game_data.get('bookmakers', []):
                                    b_title = clean_book_title(bookmaker['title'])
                                    for market in bookmaker.get('markets', []):
                                        m_key = market.get('key')
                                        for outcome in market.get('outcomes', []):
                                            if outcome.get('name') == 'Over':
                                                all_prop_rows.append({
                                                    "Matchup": matchup_str, "Market": m_key, "Sportsbook": b_title,
                                                    "Player": outcome.get('description').strip(), "Line": float(outcome.get('point')),
                                                    "Decimal Odds": outcome.get('price'), "Odds": decimal_to_american(outcome.get('price'))
                                                })
                            progress_bar.progress((idx + 1) / total_events)
                        
                        st.session_state['master_batch_prop_slate'] = all_prop_rows
                        st.success(f"🟢 Batch scan complete for {target_scan_date}! Found {len(all_prop_rows)} prop lines across {scanned_games_count} games.")
                    else:
                        st.warning(f"⚠️ API Error: Status {events_resp.status_code}")
                except Exception as e:
                    st.warning(f"⚠️ Connection Failed: {e}")
        elif 'master_batch_prop_slate' in st.session_state:
            all_prop_rows = st.session_state['master_batch_prop_slate']

        if all_prop_rows:
            master_df = pd.DataFrame(all_prop_rows)
            st.divider()
            market_view_choice = st.selectbox(
                "Select Market to View & Build Parlays From",
                ["player_shots_on_goal", "player_points", "player_goals", "player_assists"],
                format_func=lambda x: x.replace("player_", "").replace("_", " ").title()
            )
            
            if "shots_on_goal" in market_view_choice:
                market_df = master_df[master_df['Market'].str.contains("shots_on_goal", na=False)].copy()
                market_df = market_df[market_df['Line'].isin([1.5, 2.5, 3.5])]
                default_min_e, default_max_e = 5.0, 15.0
            elif "goals" in market_view_choice:
                market_df = master_df[master_df['Market'] == "player_goals"].copy()
                market_df = market_df[market_df['Line'] == 0.5]
                default_min_e, default_max_e = 8.0, 25.0
            elif "assists" in market_view_choice:
                market_df = master_df[master_df['Market'] == "player_assists"].copy()
                market_df = market_df[market_df['Line'] == 0.5]
                default_min_e, default_max_e = 6.0, 18.0
            else:
                market_df = master_df[master_df['Market'].str.contains("points", na=False)].copy()
                market_df = market_df[market_df['Line'] == 0.5]
                default_min_e, default_max_e = 6.0, 18.0

            col_ef1, col_ef2 = st.columns(2)
            min_edge_filter = col_ef1.slider(f"Min Edge Filter (%)", min_value=0.0, max_value=30.0, value=default_min_e, step=0.5)
            max_edge_filter = col_ef2.slider(f"Max Edge Filter (%)", min_value=5.0, max_value=70.0, value=default_max_e, step=1.0)

            if 'raw_player_dfs' in st.session_state and len(market_df) > 0:
                curr_df, prev_df, team_factors = st.session_state['raw_player_dfs']
                target_col = 'Shots' if "shots" in market_view_choice else ('Total Points' if "points" in market_view_choice else ('Goals' if "goals" in market_view_choice else 'Total Assists'))

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
                
                nst_to_standard = {'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ', 'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET', 'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'MIN': 'MIN', 'MTL': 'MTL', 'N.J': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI', 'NYR': 'NYR', 'OTT': 'OTT', 'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS', 'SEA': 'SEA', 'STL': 'STL', 'T.B': 'TBL', 'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK', 'WPG': 'WPG', 'WSH': 'WSH'}
                def clean_team(t_str):
                    if pd.isna(t_str): return 'UNK'
                    return nst_to_standard.get(str(t_str).split(',')[-1].strip(), str(t_str).split(',')[-1].strip())
                    
                merged_model['Clean_Team'] = merged_model['Team_curr'].apply(clean_team)
                merged_model['Matchup_Factor'] = merged_model['Clean_Team'].map(team_factors).fillna(1.0)
                merged_model['Matchup_Proj'] = merged_model['Blended_Proj'] * merged_model['Matchup_Factor']
                
                merged_scan = pd.merge(market_df, merged_model[['Player', 'Matchup_Proj']], on='Player', how='inner')
                
                if len(merged_scan) > 0:
                    merged_scan['Model_Over_Prob'] = merged_scan.apply(lambda r: poisson_over_prob(r['Matchup_Proj'], r['Line']), axis=1)
                    merged_scan['Model Over'] = (merged_scan['Model_Over_Prob'] * 100).round(1)
                    merged_scan['Fair Odds'] = merged_scan['Model_Over_Prob'].apply(lambda p: prob_to_american(p))
                    merged_scan['Edge %'] = merged_scan.apply(lambda r: round((r['Model_Over_Prob'] - (1.0 / r['Decimal Odds'])) * 100, 1) if r['Decimal Odds'] > 1.0 else 0.0, axis=1)
                    
                    merged_scan = merged_scan[(merged_scan['Edge %'] >= min_edge_filter) & (merged_scan['Edge %'] <= max_edge_filter)]
                    merged_scan = merged_scan.sort_values(by='Edge %', ascending=False).reset_index(drop=True)
                    
                    st.divider()
                    col_f1, col_f2, col_f3 = st.columns(3)
                    selected_matchup = col_f1.selectbox("🏟️ Filter Matchup", ["All Games (Full Slate)"] + sorted(merged_scan['Matchup'].unique().tolist()))
                    selected_book = col_f2.selectbox("🏛️ Filter Sportsbook", ["All Sportsbooks"] + sorted(merged_scan['Sportsbook'].unique().tolist()))
                    search_query = col_f3.text_input("🔍 Search Player", placeholder="Type name...").strip()
                    
                    if selected_matchup != "All Games (Full Slate)": merged_scan = merged_scan[merged_scan['Matchup'] == selected_matchup]
                    if selected_book != "All Sportsbooks": merged_scan = merged_scan[merged_scan['Sportsbook'] == selected_book]
                    if search_query: merged_scan = merged_scan[merged_scan['Player'].str.contains(search_query, case=False, na=False)]
                    
                    display_scan = merged_scan[['Matchup', 'Sportsbook', 'Player', 'Line', 'Odds', 'Matchup_Proj', 'Model Over', 'Fair Odds', 'Edge %']].copy()
                    display_scan.insert(0, 'Select', False)
                    display_scan['Matchup'] = display_scan['Matchup'].apply(compact_matchup)
                    display_scan['Line'] = display_scan['Line'].apply(lambda x: f"{x:.1f}")
                    display_scan['Proj Rate'] = display_scan['Matchup_Proj'].apply(lambda x: f"{x:.2f}")
                    display_scan['Model Over'] = display_scan['Model Over'].apply(lambda x: f"{x:.1f}%")
                    display_scan['Edge %'] = display_scan['Edge %'].apply(lambda x: f"+{x:.1f}%" if x > 0 else f"{x:.1f}%")
                    display_scan.drop(columns=['Matchup_Proj'], inplace=True)
                    
                    edited_df = st.data_editor(display_scan, use_container_width=True, height=400, key="nhl_slate_editor")
                    
                    checked_rows = edited_df[edited_df['Select'] == True]
                    if len(checked_rows) > 0:
                        st.subheader("🚀 Live Checked Slip & Boost Compound Calculator")
                        combined_dec, combined_true_prob, slip_summary = 1.0, 1.0, []
                        for idx, row in checked_rows.iterrows():
                            orig = merged_scan[(merged_scan['Player'] == row['Player']) & (merged_scan['Sportsbook'] == row['Sportsbook']) & (abs(merged_scan['Line'] - float(row['Line'])) < 0.1)]
                            if len(orig) > 0:
                                dec, prob = orig.iloc[0]['Decimal Odds'], orig.iloc[0]['Model_Over_Prob']
                                combined_dec *= dec
                                combined_true_prob *= prob
                                slip_summary.append({"Sportsbook": row['Sportsbook'], "Player": row['Player'], "Line": row['Line'], "Odds": row['Odds'], "Model Win Prob": row['Model Over'], "Edge": row['Edge %']})
                        st.dataframe(pd.DataFrame(slip_summary), use_container_width=True)
                        p_am = int((combined_dec - 1) * 100) if combined_dec >= 2 else int(-100 / (combined_dec - 1))
                        b_dec = 1 + ((combined_dec - 1) * (1 + (global_boost / 100)))
                        b_am = int((b_dec - 1) * 100) if b_dec >= 2 else int(-100 / (b_dec - 1))
                        slip_edge = round((combined_true_prob - (1.0 / combined_dec)) * 100, 1)
                        
                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("Checked Parlay Odds", f"+{p_am}" if p_am > 0 else f"{p_am}")
                        r2.metric(f"Boosted (+{global_boost}%)", f"+{b_am}" if b_am > 0 else f"{b_am}")
                        r3.metric("Model Slip True Prob", f"{round(combined_true_prob * 100, 1)}%")
                        r4.metric("Compound Slip Edge", f"+{slip_edge}%" if slip_edge > 0 else f"{slip_edge}%")
            else:
                st.info("ℹ️ **Model Data Needed:** Please load your 4 Natural Stat Trick CSV files in Tab 2 first.")
        else:
            st.info("💡 **Instructions:** Select target date above and click **Batch Scan All Markets**.")

    with tab2:
        st.subheader("Single Dropzone: Multi-File NST Processor")
        batch_market = st.selectbox("Select Target Prop Market", ["Shots on Goal (SOG)", "Points (G+A)", "Anytime Goal Scorer", "Assists Only"], key="nhl_batch_market")
        target_line_choice = st.selectbox("Select Target Threshold Line", [0.5, 1.5, 2.5, 3.5, 4.5, 5.5], index=1, key="nhl_alt_line")
        target_date = st.date_input("Target Slate Date", value=date.today(), key="nhl_target_date")
        uploaded_files = st.file_uploader("Drop all 4 Natural Stat Trick CSV files here", type="csv", accept_multiple_files=True, key="nhl_nst_drop")
        
        if uploaded_files:
            curr_player_df, prev_player_df, curr_team_df = None, None, None
            for file in uploaded_files:
                fname = file.name.lower()
                if "player" in fname:
                    temp_df = pd.read_csv(file)
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_player_df = temp_df
                    else: prev_player_df = temp_df
                elif "games" in fname:
                    temp_df = pd.read_csv(file)
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_team_df = temp_df
                    
            if curr_player_df is not None and prev_player_df is not None:
                team_matchup_factors = {}
                try:
                    sched_resp = requests.get(f"https://api-web.nhle.com/v1/schedule/{target_date.strftime('%Y-%m-%d')}").json()
                    if curr_team_df is not None and 'Team' in curr_team_df.columns:
                        f_std = {'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF', 'Carolina Hurricanes': 'CAR', 'Columbus Blue Jackets': 'CBJ', 'Calgary Flames': 'CGY', 'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL', 'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL', 'New Jersey Devils': 'NJD', 'Nashville Predators': 'NSH', 'New York Islanders': 'NYI', 'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI', 'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS', 'Seattle Kraken': 'SEA', 'St Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR', 'Utah Mammoth': 'UTA', 'Utah Hockey Club': 'UTA', 'Utah': 'UTA', 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH'}
                        curr_team_df['Standard_Abbrev'] = curr_team_df['Team'].map(f_std)
                        stat_col = 'SA' if batch_market == "Shots on Goal (SOG)" else ('HDCA' if batch_market == "Anytime Goal Scorer" else 'SCA')
                        if stat_col not in curr_team_df.columns: stat_col = 'CA'
                        mean_val = curr_team_df[stat_col].mean() if stat_col in curr_team_df.columns else 1.0
                        for _, row in curr_team_df.iterrows():
                            if pd.notnull(row['Standard_Abbrev']):
                                factor = row.get(stat_col, mean_val) / mean_val if mean_val > 0 else 1.0
                                team_matchup_factors[row['Standard_Abbrev']] = max(0.80, min(1.20, factor))
                except: pass

                target_col = 'Shots' if batch_market == "Shots on Goal (SOG)" else ('Total Points' if batch_market == "Points (G+A)" else ('Goals' if batch_market == "Anytime Goal Scorer" else 'Total Assists'))
                st.session_state['raw_player_dfs'] = (curr_player_df, prev_player_df, team_matchup_factors)
                
                merged_df = pd.merge(curr_player_df, prev_player_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
                merged_df['Stat_curr'] = pd.to_numeric(merged_df[f'{target_col}_curr'], errors='coerce').fillna(0)
                merged_df['Stat_prev'] = pd.to_numeric(merged_df[f'{target_col}_prev'], errors='coerce').fillna(0)
                
                gp_prev = pd.to_numeric(merged_df.get('GP_prev', 82), errors='coerce').replace(0, 1).fillna(82)
                gp_curr = pd.to_numeric(merged_df.get('GP_curr', 5), errors='coerce').replace(0, 1).fillna(5)
                merged_df = merged_df[gp_curr >= min_gp].copy()
                
                merged_df['Blended_Proj'] = ((merged_df['Stat_prev'] / gp_prev) * (1 - (season_weight / 100))) + ((merged_df['Stat_curr'] / gp_curr) * (season_weight / 100))
                
                st.success(f"🟢 Loaded {len(merged_df)} players successfully for NHL model!")
            else:
                st.warning("Please upload both Player Season Total CSV files.")


# ==============================================================================
# FOOTBALL (NFL) PIPELINE (NST-STYLE DROPZONE + SCHEDULE & MATCHUP MAPPING)
# ==============================================================================
elif "NFL" in active_sport:
    st.title("🏈 NFL Quant Terminal: NST-Style Suite")
    st.markdown("### Drop your NFL CSV files, filter by target date, and batch scan live props with matchup factors.")

    tab_nfl1, tab_nfl2 = st.tabs([
        "📊 Automated +EV NFL Prop Scanner & Parlay Builder", 
        "📁 NFL Multi-File Uploader & Matchup Matrix"
    ])

    with tab_nfl2:
        st.subheader("NFL Multi-File CSV Dropzone")
        st.write("Drop your exported NFL Player stats and Team defense CSV files below.")
        
        nfl_uploaded_files = st.file_uploader(
            "Drop NFL Player & Team CSV files here", 
            type="csv", 
            accept_multiple_files=True,
            key="nfl_nst_style_drop"
        )
        
        nfl_target_date = st.date_input("Target NFL Slate Date for Matchup Factors", value=date.today(), key="nfl_nst_date")

        if nfl_uploaded_files:
            nfl_player_df, nfl_team_df = None, None
            for file in nfl_uploaded_files:
                fname = file.name.lower()
                try:
                    temp_df = pd.read_csv(file)
                    if "player" in fname or "stats" in fname:
                        nfl_player_df = temp_df
                        st.success(f"🟢 Loaded NFL Player File: {file.name} ({len(temp_df)} rows)")
                    elif "team" in fname or "def" in fname or "game" in fname:
                        nfl_team_df = temp_df
                        st.success(f"🟢 Loaded NFL Team File: {file.name} ({len(temp_df)} rows)")
                except Exception as e:
                    st.error(f"⚠️ Error reading {file.name}: {e}")
            
            if nfl_player_df is not None:
                # Fetch NFL schedule to map opponent matchup factors
                nfl_matchup_factors = {}
                try:
                    # The Odds API or ESPN/NFL schedule endpoint fallback for matchups on target date
                    sched_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={nfl_target_date.strftime('%Y%m%d')}"
                    sched_resp = requests.get(sched_url, timeout=5).json()
                    events = sched_resp.get("events", [])
                    st.info(f"📅 Found {len(events)} NFL games scheduled for {nfl_target_date}.")
                except Exception as e:
                    st.warning(f"Schedule fetch notice: {e}")

                st.session_state['nfl_model_data'] = (nfl_player_df, nfl_team_df)
                st.write("### 📋 Player Data Matrix Preview:")
                st.dataframe(nfl_player_df.head(25), use_container_width=True)
            else:
                st.warning("Please upload at least your NFL Player CSV dataset.")
        else:
            st.info("💡 **Instructions:** Drop your NFL CSV files above to initialize the model matrix.")

    with tab_nfl1:
        col_nfl_s1, col_nfl_s2 = st.columns([2, 1])
        target_nfl_scan_date = col_nfl_s1.date_input("📅 Target NFL Slate Date", value=date.today(), key="nfl_scan_date_picker")
        fetch_nfl_odds_btn = col_nfl_s2.button("🔄 Batch Scan NFL Markets", use_container_width=True)

        all_nfl_rows = []
        if fetch_nfl_odds_btn:
            if not api_key_input:
                st.error("⚠️ Please enter your Odds API Key in the sidebar first.")
            else:
                try:
                    events_url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events?apiKey={api_key_input}"
                    ev_resp = requests.get(events_url, timeout=8)
                    if ev_resp.status_code == 200:
                        events_list = ev_resp.json()
                        books_str = ",".join(selected_books)
                        nfl_markets = "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_anytime_td,player_pass_yds_alternate,player_rush_yds_alternate,player_reception_yds_alternate"
                        
                        progress_bar = st.progress(0)
                        scanned_count = 0
                        target_date_str = target_nfl_scan_date.strftime('%Y-%m-%d')

                        for idx, ev in enumerate(events_list):
                            if target_date_str not in ev.get('commence_time', ''): continue
                            scanned_count += 1
                            ev_id = ev['id']
                            matchup_str = f"{ev['away_team']} @ {ev['home_team']}"
                            
                            prop_url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{ev_id}/odds?apiKey={api_key_input}&regions=us,us2&markets={nfl_markets}&bookmakers={books_str}"
                            resp = requests.get(prop_url, timeout=6)
                            if resp.status_code == 200:
                                game_data = resp.json()
                                for bookmaker in game_data.get('bookmakers', []):
                                    b_title = clean_book_title(bookmaker['title'])
                                    for market in bookmaker.get('markets', []):
                                        m_key = market.get('key')
                                        for outcome in market.get('outcomes', []):
                                            if outcome.get('name') == 'Over':
                                                all_nfl_rows.append({
                                                    "Matchup": matchup_str, "Market": m_key, "Sportsbook": b_title,
                                                    "Player": outcome.get('description').strip(), "Line": float(outcome.get('point')),
                                                    "Decimal Odds": outcome.get('price'), "Odds": decimal_to_american(outcome.get('price'))
                                                })
                            progress_bar.progress((idx + 1) / len(events_list))
                        
                        st.session_state['nfl_batch_slate'] = all_nfl_rows
                        st.success(f"🟢 NFL batch scan complete! Found {len(all_nfl_rows)} prop lines across {scanned_count} games.")
                    else:
                        st.warning(f"⚠️ API Error: Status {ev_resp.status_code}")
                except Exception as e:
                    st.warning(f"⚠️ Connection Failed: {e}")
        elif 'nfl_batch_slate' in st.session_state:
            all_nfl_rows = st.session_state['nfl_batch_slate']

        if all_nfl_rows:
            nfl_master_df = pd.DataFrame(all_nfl_rows)
            st.divider()
            nfl_market_choice = st.selectbox(
                "Select NFL Market to View",
                ["player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions", "player_anytime_td"],
                format_func=lambda x: x.replace("player_", "").replace("_", " ").title()
            )
            
            market_nfl_df = nfl_master_df[nfl_master_df['Market'].str.contains(nfl_market_choice, na=False)].copy()
            
            st.metric("Available Props in Market View", len(market_nfl_df))
            st.dataframe(market_nfl_df[['Matchup', 'Sportsbook', 'Player', 'Line', 'Odds']].head(50), use_container_width=True)
        else:
            st.info("💡 **Instructions:** Select target date above and click **Batch Scan NFL Markets** to pull live props.")
