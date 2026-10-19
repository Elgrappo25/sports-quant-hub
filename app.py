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

                    # ==========================================
                    # AUTOMATED PARLAY GENERATOR (CLEANED & SORTED)
                    # ==========================================
                    st.divider()
                    st.subheader("🤖 Automated Same-Book +EV Parlay Generator")
                    auto_col1, auto_col2, auto_col3 = st.columns(3)
                    parlay_mode = auto_col1.selectbox("Parlay Type", ["Same Game Parlay (SGP)", "Multi-Game Parlay (Independent)"], key="auto_parlay_mode")
                    parlay_legs_count = auto_col2.selectbox("Leg Count", [2, 3, 4, 5], key="auto_parlay_legs")
                    min_parlay_edge = auto_col3.slider("Min Parlay Edge (%)", min_value=0.0, max_value=25.0, value=3.0, step=0.5, key="auto_min_edge")
                    generate_parlays_btn = st.button("⚡ Generate Top Automated Parlays", use_container_width=True)
                    
                    if generate_parlays_btn:
                        generated_slips = []
                        for book_name, book_df in merged_scan.groupby("Sportsbook"):
                            if len(book_df) < parlay_legs_count: continue
                            for combo in itertools.combinations(book_df.iterrows(), parlay_legs_count):
                                combo_rows = [item[1] for item in combo]
                                if "Same Game Parlay" in parlay_mode:
                                    match_set = {r['Matchup'] for r in combo_rows}
                                    if len(match_set) > 1: continue
                                    player_set = {r['Player'] for r in combo_rows}
                                    if len(player_set) < parlay_legs_count: continue
                                else:
                                    match_set = {r['Matchup'] for r in combo_rows}
                                    if len(match_set) < parlay_legs_count: continue
                                    player_set = {r['Player'] for r in combo_rows}
                                    if len(player_set) < parlay_legs_count: continue

                                comb_dec = 1.0
                                comb_prob = 1.0
                                leg_descriptions = []
                                for r in combo_rows:
                                    comb_dec *= r['Decimal Odds']
                                    comb_prob *= r['Model_Over_Prob']
                                    leg_descriptions.append(f"{r['Player']} O{r['Line']} ({r['Odds']})")
                                
                                if "Same Game Parlay" in parlay_mode:
                                    haircut_factor = 0.85 if parlay_legs_count <= 3 else 0.78
                                    comb_prob *= haircut_factor
                                    
                                implied_p = 1.0 / comb_dec
                                slip_e = round((comb_prob - implied_p) * 100, 1)
                                
                                if slip_e >= min_parlay_edge:
                                    p_factor = comb_dec - 1
                                    b_dec = 1 + (p_factor * (1 + (global_boost / 100)))
                                    b_am = int((b_dec - 1) * 100) if b_dec >= 2 else int(-100 / (b_dec - 1))
                                    b_str = f"+{b_am}" if b_am > 0 else f"{b_am}"
                                    std_am = int((comb_dec - 1) * 100) if comb_dec >= 2 else int(-100 / (comb_dec - 1))
                                    std_str = f"+{std_am}" if std_am > 0 else f"{std_am}"
                                    generated_slips.append({
                                        "Sportsbook": book_name,
                                        "Compound Edge %": slip_e,  # Front & center!
                                        "Standard Odds": std_str,
                                        f"Boosted Odds (+{global_boost}%)": b_str,
                                        "Model Prob": f"{round(comb_prob * 100, 1)}%",
                                        "Legs": " + | + ".join(leg_descriptions)
                                    })
                        
                        if generated_slips:
                            parlay_results_df = pd.DataFrame(generated_slips)
                            # Explicitly sort highest to lowest compound edge
                            parlay_results_df = parlay_results_df.sort_values(by="Compound Edge %", ascending=False).reset_index(drop=True)
                            st.session_state['generated_parlays_cache'] = parlay_results_df
                        else:
                            st.warning("⚠️ No parlays found matching your criteria.")
                    
                    if 'generated_parlays_cache' in st.session_state:
                        st.success(f"🎉 Showing cached automated parlays session.")
                        st.dataframe(st.session_state['generated_parlays_cache'].head(10), use_container_width=True)
            else:
                st.info("ℹ️ **Model Data Needed:** Please load your 4 Natural Stat Trick CSV files in Tab 2 first.")
        else:
            st.info("💡 **Instructions:** Select target date above and click **Batch Scan All Markets**.")

    with tab2:
        st.subheader("Single Dropzone: Multi-File NST Processor & Market-Tailored Matrix")
        st.write("Drop your 4 Natural Stat Trick count files below. Color coding is custom-tailored to each specific betting market.")
        
        batch_market = st.selectbox(
            "Select Target Prop Market", 
            ["Shots on Goal (SOG)", "Points (G+A)", "Anytime Goal Scorer", "Assists Only"],
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
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_player_df = temp_df
                    else: prev_player_df = temp_df
                elif "games" in fname:
                    temp_df = pd.read_csv(file)
                    if 'GP' in temp_df.columns and temp_df['GP'].max() <= 20: curr_team_df = temp_df
                    else: prev_team_df = temp_df
                    
            if curr_player_df is not None and prev_player_df is not None:
                nst_to_standard = {'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ', 'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET', 'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'MIN': 'MIN', 'MTL': 'MTL', 'N.J': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI', 'NYR': 'NYR', 'OTT': 'OTT', 'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS', 'SEA': 'SEA', 'STL': 'STL', 'T.B': 'TBL', 'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK', 'WPG': 'WPG', 'WSH': 'WSH'}
                def clean_team(t_str):
                    if pd.isna(t_str): return 'UNK'
                    return nst_to_standard.get(str(t_str).split(',')[-1].strip(), str(t_str).split(',')[-1].strip())

                active_teams = set()
                team_matchup_factors = {}
                team_opponents = {}
                
                try:
                    sched_url = f"https://api-web.nhle.com/v1/schedule/{target_date.strftime('%Y-%m-%d')}"
                    sched_resp = requests.get(sched_url).json()
                    
                    if curr_team_df is not None and 'Team' in curr_team_df.columns:
                        curr_team_df['Standard_Abbrev'] = curr_team_df['Team'].map({'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF', 'Carolina Hurricanes': 'CAR', 'Columbus Blue Jackets': 'CBJ', 'Calgary Flames': 'CGY', 'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL', 'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL', 'New Jersey Devils': 'NJD', 'Nashville Predators': 'NSH', 'New York Islanders': 'NYI', 'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI', 'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS', 'Seattle Kraken': 'SEA', 'St Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR', 'Utah Mammoth': 'UTA', 'Utah Hockey Club': 'UTA', 'Utah': 'UTA', 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH'})
                        stat_col = 'SA' if batch_market == "Shots on Goal (SOG)" else ('HDCA' if batch_market == "Anytime Goal Scorer" else 'SCA')
                        if stat_col not in curr_team_df.columns: stat_col = 'CA'
                        curr_team_df[stat_col] = pd.to_numeric(curr_team_df[stat_col], errors='coerce').fillna(0)
                        mean_val = curr_team_df[stat_col].mean() if stat_col in curr_team_df.columns else 1.0
                        for _, row in curr_team_df.iterrows():
                            t_abbrev = row['Standard_Abbrev']
                            factor = row.get(stat_col, mean_val) / mean_val if mean_val > 0 else 1.0
                            if pd.notnull(t_abbrev): team_matchup_factors[t_abbrev] = max(0.80, min(1.20, factor))

                    for week_day in sched_resp.get("gameWeek", []):
                        if week_day.get("date") == target_date.strftime('%Y-%m-%d'):
                            for game in week_day.get("games", []):
                                away = game.get("awayTeam", {}).get("abbrev")
                                home = game.get("homeTeam", {}).get("abbrev")
                                if away: active_teams.add(away)
                                if home: active_teams.add(home)
                                if away and home:
                                    team_opponents[away] = f"@{home}"
                                    team_opponents[home] = f"vs {away}"
                except Exception as e:
                    pass

                target_col = 'Shots' if batch_market == "Shots on Goal (SOG)" else ('Total Points' if batch_market == "Points (G+A)" else ('Goals' if batch_market == "Anytime Goal Scorer" else 'Total Assists'))
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
                
                st.write(f"### 📈 Slate Alt-Line Matrix ({batch_market} > {target_line_choice}):")
                display_cols = ['Player', 'Clean_Team', 'Opponent', 'Baseline_Stat', 'Current_Stat', 'Matchup_Factor', 'Matchup_Proj', 'Model_Over_Prob_%', 'Fair_American_Odds']
                
                final_board = merged_df[display_cols].sort_values(by='Matchup_Proj', ascending=False).reset_index(drop=True)

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

# ==============================================================================
# FOOTBALL (NFL) PLACEHOLDER
# ==============================================================================
elif "NFL" in active_sport:
    st.title("🏈 NFL Quant Terminal: Paused")
    st.markdown("### Focus is currently locked on your production NHL terminal for tomorrow's slate.")
    st.info("💡 **Instructions:** Switch back to **🏒 NHL (Active)** in the sidebar to use your live betting suite.")
