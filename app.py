import streamlit as st
import pandas as pd
import requests
import math
from datetime import date
import itertools
from google import genai
from PIL import Image
import io

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
st.sidebar.header("🔌 Nexus Odds & Vision Input")
gemini_api_key = st.sidebar.text_input("Gemini API Key (for Vision OCR)", type="password", placeholder="Enter Gemini key to read screenshots...")

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
    st.markdown("### Nexus Vision Parser, NST Projections, Poisson Math, and +EV Parlay Generation.")

    tab1, tab2 = st.tabs([
        "📊 Nexus Vision Parser & +EV Prop Scanner", 
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
        st.subheader("📸 Nexus Odds Screenshot Vision Uploader")
        st.write("Upload a screenshot from Nexus Odds showing multiple sportsbooks. Our Vision parser will automatically extract the players, lines, and odds across all books.")
        
        uploaded_screenshot = st.file_uploader("Upload Nexus Odds Screenshot", type=["png", "jpg", "jpeg"], key="nexus_screenshot_drop")
        
        if uploaded_screenshot is not None:
            image = Image.open(uploaded_screenshot)
            st.image(image, caption="Uploaded Nexus Odds Screenshot", use_container_width=True)
            
            parse_screenshot_btn = st.button("⚡ Parse Screenshot with Vision AI", use_container_width=True)
            
            if parse_screenshot_btn:
                if not gemini_api_key:
                    st.error("⚠️ Please enter your Gemini API Key in the sidebar to enable Vision parsing.")
                else:
                    try:
                        with st.spinner("🔍 Reading odds and player props from image..."):
                            client = genai.Client(api_key=gemini_api_key)
                            prompt = """
                            Extract all player prop betting lines from this image across all sportsbooks shown. Return a clean CSV format with columns:
                            Matchup, Sportsbook, Player, Market, Line, Odds
                            Where Market is one of: player_shots_on_goal, player_points, player_goals, player_assists
                            Line is a float (e.g., 1.5, 2.5, 0.5)
                            Odds is American odds as an integer (e.g., -140, +125)
                            Return ONLY valid CSV text, no markdown code blocks.
                            """
                            response = client.models.generate_content(
                                model='gemini-3.8-flash',
                                contents=[image, prompt]
                            )
                            
                            csv_text = response.text.replace("```csv", "").replace("```", "").strip()
                            lines = csv_text.split('\n')
                            parsed_data = []
                            for l in lines[1:]:
                                parts = [p.strip() for p in l.split(',')]
                                if len(parts) >= 6:
                                    try:
                                        am_odds = int(parts[5])
                                        dec_odds = (1.0 + (100 / am_odds)) if am_odds > 0 else (1.0 + (abs(am_odds) / 100))
                                        parsed_data.append({
                                            "Matchup": parts[0],
                                            "Sportsbook": clean_book_title(parts[1]),
                                            "Player": parts[2],
                                            "Market": parts[3],
                                            "Line": float(parts[4]),
                                            "Decimal Odds": dec_odds,
                                            "Odds": f"{am_odds:+d}" if am_odds > 0 else f"{am_odds}"
                                        })
                                    except:
                                        continue
                            
                            if parsed_data:
                                st.session_state['nexus_parsed_slate'] = parsed_data
                                st.success(f"🟢 Successfully extracted {len(parsed_data)} props from your Nexus screenshot!")
                            else:
                                st.warning("⚠️ Could not automatically parse structured rows. Try a clearer screenshot.")
                    except Exception as e:
                        st.error(f"Vision Parsing Error: {e}")

        if 'nexus_parsed_slate' in st.session_state:
            all_prop_rows = st.session_state['nexus_parsed_slate']
            master_df = pd.DataFrame(all_prop_rows)
            
            st.divider()
            market_view_choice = st.selectbox(
                "Select Market to View & Build Parlays From",
                ["player_shots_on_goal", "player_points", "player_goals", "player_assists"],
                format_func=lambda x: x.replace("player_", "").replace("_", " ").title(),
                key="nexus_market_choice"
            )
            
            market_df = master_df[master_df['Market'] == market_view_choice].copy()

            col_ef1, col_ef2 = st.columns(2)
            min_edge_filter = col_ef1.slider(f"Min Edge Filter (%)", min_value=0.0, max_value=30.0, value=0.0, step=0.5, key="nex_min_e")
            max_edge_filter = col_ef2.slider(f"Max Edge Filter (%)", min_value=5.0, max_value=70.0, value=50.0, step=1.0, key="nex_max_e")

            if 'raw_player_dfs' in st.session_state and len(market_df) > 0:
                curr_df, prev_df, team_factors, team_opponents_raw = st.session_state['raw_player_dfs']
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
                
                def get_vision_matchup_factor(row):
                    team = row['Clean_Team']
                    opp_abbrev = team_opponents_raw.get(team, None)
                    if opp_abbrev and opp_abbrev in team_factors:
                        return team_factors[opp_abbrev]
                    return 1.0

                merged_model['Matchup_Factor'] = merged_model.apply(get_vision_matchup_factor, axis=1)
                merged_model['Matchup_Proj'] = merged_model['Blended_Proj'] * merged_model['Matchup_Factor']
                
                merged_scan = pd.merge(market_df, merged_model[['Player', 'Matchup_Proj']], on='Player', how='inner')
                
                if len(merged_scan) > 0:
                    merged_scan['Model_Over_Prob'] = merged_scan.apply(lambda r: poisson_over_prob(r['Matchup_Proj'], r['Line']), axis=1)
                    merged_scan['Model Over'] = (merged_scan['Model_Over_Prob'] * 100).round(1)
                    merged_scan['Fair Odds'] = merged_scan['Model_Over_Prob'].apply(lambda p: prob_to_american(p))
                    merged_scan['Edge %'] = merged_scan.apply(lambda r: round((r['Model_Over_Prob'] - (1.0 / r['Decimal Odds'])) * 100, 1) if r['Decimal Odds'] > 1.0 else 0.0, axis=1)
                    
                    merged_scan = merged_scan[(merged_scan['Edge %'] >= min_edge_filter) & (merged_scan['Edge %'] <= max_edge_filter)]
                    merged_scan = merged_scan.sort_values(by='Edge %', ascending=False).reset_index(drop=True)
                    
                    display_scan = merged_scan[['Matchup', 'Sportsbook', 'Player', 'Line', 'Odds', 'Matchup_Proj', 'Model Over', 'Fair Odds', 'Edge %']].copy()
                    display_scan.insert(0, 'Select', False)
                    display_scan['Line'] = display_scan['Line'].apply(lambda x: f"{x:.1f}")
                    display_scan['Proj Rate'] = display_scan['Matchup_Proj'].apply(lambda x: f"{x:.2f}")
                    display_scan['Model Over'] = display_scan['Model Over'].apply(lambda x: f"{x:.1f}%")
                    display_scan['Edge %'] = display_scan['Edge %'].apply(lambda x: f"+{x:.1f}%" if x > 0 else f"{x:.1f}%")
                    display_scan.drop(columns=['Matchup_Proj'], inplace=True)
                    
                    edited_df = st.data_editor(display_scan, use_container_width=True, height=400, key="nexus_slate_editor")
                    
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
                    # AUTOMATED PARLAY GENERATOR
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
                                        "Compound Edge %": slip_e,
                                        "Standard Odds": std_str,
                                        f"Boosted Odds (+{global_boost}%)": b_str,
                                        "Model Prob": f"{round(comb_prob * 100, 1)}%",
                                        "Legs": " + | + ".join(leg_descriptions)
                                    })
                        
                        if generated_slips:
                            parlay_results_df = pd.DataFrame(generated_slips)
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
            st.info("💡 **Instructions:** Upload a Nexus Odds screenshot above to parse lines.")

    with tab2:
        st.subheader("Single Dropzone: Multi-File NST Processor & Market-Tailored Matrix")
        st.write("Drop your 4 Natural Stat Trick count files below to generate the master probability and matchup matrix.")
        
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
                                    team_opponents_raw[away] = home
                                    team_opponents_raw[home] = away
                                    team_opponents_display[away] = f"@{home}"
                                    team_opponents_display[home] = f"vs {away}"
                except Exception as e:
                    pass

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
                
                gp_prev = pd.to_numeric(merged_df.get('GP_prev', 82), errors='coerce').replace(0, 1).fillna(82)
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
                    final_board.style.apply(lambda col: [color_matrix_cells(val=v, col_name=col.name) for v in col], subset=['Matchup_Factor', 'Model_Over_Prob_%']),
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
    st.markdown("### Focus is currently locked on your production NHL terminal for tonight's slate.")
