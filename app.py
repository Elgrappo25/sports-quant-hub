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
    st.markdown("### Manual Prop Input, NST Projections, Poisson Math, and +EV Parlay Generation.")

    tab1, tab2 = st.tabs([
        "📊 Manual Prop Input & +EV Scanner", 
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
        'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG', 'Washington Capitals': 'WSH',
        'ANA': 'ANA', 'BOS': 'BOS', 'BUF': 'BUF', 'CAR': 'CAR', 'CBJ': 'CBJ',
        'CGY': 'CGY', 'CHI': 'CHI', 'COL': 'COL', 'DAL': 'DAL', 'DET': 'DET',
        'EDM': 'EDM', 'FLA': 'FLA', 'L.A': 'LAK', 'LAK': 'LAK', 'MIN': 'MIN',
        'MTL': 'MTL', 'N.J': 'NJD', 'NJD': 'NJD', 'NSH': 'NSH', 'NYI': 'NYI',
        'NYR': 'NYR', 'OTT': 'OTT', 'PHI': 'PHI', 'PIT': 'PIT', 'S.J': 'SJS',
        'SJS': 'SJS', 'SEA': 'SEA', 'STL': 'STL', 'T.B': 'TBL', 'TBL': 'TBL',
        'TOR': 'TOR', 'UTA': 'UTA', 'VAN': 'VAN', 'VGK': 'VGK', 'WPG': 'WPG', 'WSH': 'WSH'
    }

    with tab1:
        st.subheader("📝 Manual Nexus Odds & Prop Input")
        st.write("Enter the player props from your Nexus Odds screen below to run them against your NST model projections.")

        # Default sample row so the table is never empty on load
        if 'manual_props_df' not in st.session_state:
            st.session_state['manual_props_df'] = pd.DataFrame([
                {"Select": False, "Matchup": "TOR @ MTL", "Sportsbook": "FanDuel", "Player": "Auston Matthews", "Market": "player_shots_on_goal", "Line": 3.5, "Odds (+/-)": "+115"}
            ])

        edited_input_df = st.data_editor(st.session_state['manual_props_df'], num_rows="dynamic", use_container_width=True, key="manual_prop_editor")
        st.session_state['manual_props_df'] = edited_input_df

        if len(edited_input_df) > 0 and 'raw_player_dfs' in st.session_state:
            curr_df, prev_df, team_factors = st.session_state['raw_player_dfs']
            
            processed_rows = []
            for _, r in edited_input_df.iterrows():
                try:
                    am_odds = int(r['Odds (+/-)'])
                    dec_odds = (1.0 + (100 / am_odds)) if am_odds > 0 else (1.0 + (abs(am_odds) / 100))
                    processed_rows.append({
                        "Select": r['Select'],
                        "Matchup": r['Matchup'],
                        "Sportsbook": r['Sportsbook'],
                        "Player": r['Player'].strip(),
                        "Market": r['Market'],
                        "Line": float(r['Line']),
                        "Decimal Odds": dec_odds,
                        "Odds": f"{am_odds:+d}" if am_odds > 0 else f"{am_odds}"
                    })
                except:
                    continue

            if processed_rows:
                market_df = pd.DataFrame(processed_rows)
                
                market_view_choice = st.selectbox(
                    "Select Market to View & Build Parlays From",
                    ["player_shots_on_goal", "player_points", "player_goals", "player_assists"],
                    format_func=lambda x: x.replace("player_", "").replace("_", " ").title(),
                    key="manual_market_choice"
                )
                
                market_df = market_df[market_df['Market'] == market_view_choice].copy()

                if len(market_df) > 0:
                    target_col = 'Shots' if "shots" in market_view_choice else ('Total Points' if "points" in market_view_choice else ('Goals' if "goals" in market_view_choice else 'Total Assists'))

                    merged_model = pd.merge(curr_df, prev_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
                    merged_model['Player'] = merged_model['Player'].astype(str).str.strip()
                    merged_model['Stat_curr'] = pd.to_numeric(merged_model[f'{target_col}_curr'], errors='coerce').fillna(0)
                    merged_model['Stat_prev'] = pd.to_numeric(merged_model[f'{target_col}_prev'], errors='coerce').fillna(0)
                    
                    gp_prev = pd.to_numeric(merged_model.get('GP_prev', 82), errors='coerce').replace(0, 1).fillna(82)
                    gp_curr = pd.to_numeric(merged_model.get('GP_curr', 5), errors='coerce').replace(0, 1).fillna(5)
                    
                    merged_model['Baseline_Stat'] = merged_model['Stat_prev'] / gp_prev
                    merged_model['Current_Stat'] = merged_model['Stat_curr'] / gp_curr
                    merged_model['Blended_Proj'] = (merged_model['Baseline_Stat'] * (1 - (season_weight / 100))) + (merged_model['Current_Stat'] * (season_weight / 100))
                    
                    def clean_team(t_str):
                        if pd.isna(t_str): return 'UNK'
                        raw = str(t_str).split(',')[-1].strip()
                        return team_to_abbrev.get(raw, raw)
                        
                    merged_model['Clean_Team'] = merged_model['Team_curr'].apply(clean_team)
                    merged_model['Matchup_Factor'] = merged_model['Clean_Team'].map(team_factors).fillna(1.0)
                    merged_model['Matchup_Proj'] = merged_model['Blended_Proj'] * merged_model['Matchup_Factor']
                    
                    merged_scan = pd.merge(market_df, merged_model[['Player', 'Matchup_Proj']], on='Player', how='inner')
                    
                    if len(merged_scan) > 0:
                        merged_scan['Model_Over_Prob'] = merged_scan.apply(lambda r: poisson_over_prob(r['Matchup_Proj'], r['Line']), axis=1)
                        merged_scan['Model Over'] = (merged_scan['Model_Over_Prob'] * 100).round(1)
                        merged_scan['Fair Odds'] = merged_scan['Model_Over_Prob'].apply(lambda p: prob_to_american(p))
                        merged_scan['Edge %'] = merged_scan.apply(lambda r: round((r['Model_Over_Prob'] - (1.0 / r['Decimal Odds'])) * 100, 1) if r['Decimal Odds'] > 1.0 else 0.0, axis=1)
                        merged_scan = merged_scan.sort_values(by='Edge %', ascending=False).reset_index(drop=True)
                        
                        display_scan = merged_scan[['Matchup', 'Sportsbook', 'Player', 'Line', 'Odds', 'Matchup_Proj', 'Model Over', 'Fair Odds', 'Edge %']].copy()
                        display_scan.insert(0, 'Select', False)
                        display_scan['Line'] = display_scan['Line'].apply(lambda x: f"{x:.1f}")
                        display_scan['Proj Rate'] = display_scan['Matchup_Proj'].apply(lambda x: f"{x:.2f}")
                        display_scan['Model Over'] = display_scan['Model Over'].apply(lambda x: f"{x:.1f}%")
                        display_scan['Edge %'] = display_scan['Edge %'].apply(lambda x: f"+{x:.1f}%" if x > 0 else f"{x:.1f}%")
                        display_scan.drop(columns=['Matchup_Proj'], inplace=True)
                        
                        st.write("### 📈 Model Evaluation & Edge Matrix:")
                        st.dataframe(display_scan, use_container_width=True, height=400)
        else:
            st.info("ℹ️ **Model Data Needed:** Please load your 4 Natural Stat Trick CSV files in Tab 2 first.")

    with tab2:
        st.subheader("Single Dropzone: Multi-File NST Processor & Market-Tailored Matrix")
        st.write("Drop your 4 Natural Stat Trick count files below.")
        
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
                team_matchup_factors = {}
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
                except: pass

                target_col = 'Shots' if batch_market == "Shots on Goal (SOG)" else ('Total Points' if batch_market == "Points (G+A)" else ('Goals' if batch_market == "Anytime Goal Scorer" else 'Total Assists'))
                st.session_state['raw_player_dfs'] = (curr_player_df, prev_player_df, team_matchup_factors)
                st.success("🟢 NST Player files successfully loaded and cached for model pairing!")

# ==============================================================================
# FOOTBALL (NFL) PLACEHOLDER
# ==============================================================================
elif "NFL" in active_sport:
    st.title("🏈 NFL Quant Terminal: Paused")
    st.markdown("### Focus is currently locked on your production NHL terminal for tonight's slate.")
