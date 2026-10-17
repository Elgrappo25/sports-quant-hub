import streamlit as st
import pandas as pd
import requests
import math
from datetime import date

st.set_page_config(page_title="Sports Quant Hub - NHL Pro Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("### Count-based scaling, Poisson math, live Odds API line-shopping, and market-tailored color coding.")

# Sidebar for global settings & Live Odds configuration
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=15, step=5)
min_gp = st.sidebar.slider("Minimum Current Season GP Filter", min_value=1, max_value=15, value=3, step=1)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

st.sidebar.divider()
st.sidebar.header("🔌 Live Odds & Line Shopping")
api_key_input = st.sidebar.text_input("Odds API Key", type="password", placeholder="Enter your API key here...")
available_books = ["draftkings", "fanduel", "betmgm", "betrivers", "thescore", "bet365", "pinnacle"]
selected_books = st.sidebar.multiselect("Select Your Sportsbooks", available_books, default=["draftkings", "fanduel", "betmgm", "thescore", "bet365"])

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
    "📊 Live +EV Market Scanner & Valuator", 
    "📁 Multi-File NST Uploader & Market Matrix", 
    "🚀 Boost & Parlay Optimizer"
])

with tab1:
    st.subheader("Live Odds API & Poisson Prop Valuator")
    st.write("Click the button below only when you want to pull live market odds (saves your monthly API credits).")
    
    col_fetch1, col_fetch2 = st.columns([1, 3])
    fetch_clicked = col_fetch1.button("🔄 Fetch Live Odds Now")
    
    live_games = []
    if fetch_clicked:
        if not api_key_input:
            st.error("⚠️ Please enter your Odds API Key in the sidebar first.")
        else:
            try:
                books_str = ",".join(selected_books)
                odds_url = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds/?apiKey={api_key_input}&regions=us&markets=h2h&bookmakers={books_str}"
                resp = requests.get(odds_url, timeout=5)
                if resp.status_code == 200:
                    live_games = resp.json()
                    st.session_state['live_games'] = live_games
                    st.success(f"🟢 Successfully pulled live odds! ({len(live_games)} games found)")
                else:
                    st.warning(f"⚠️ API Error: Status {resp.status_code}")
            except Exception as e:
                st.warning(f"⚠️ Connection Failed: {e}")
    elif 'live_games' in st.session_state:
        live_games = st.session_state['live_games']

    if live_games:
        st.write("### 🏟️ Live Games Available on Board:")
        game_options = [f"{g['away_team']} @ {g['home_team']} ({g['commence_time'][:10]})" for g in live_games]
        selected_game_label = st.selectbox("Select Live Game to Inspect", game_options)
        
        selected_game_obj = live_games[game_options.index(selected_game_label)]
        st.write(f"**Bookmaker Lines for {selected_game_label} (American Odds):**")
        
        book_rows = []
        for bookmaker in selected_game_obj.get('bookmakers', []):
            b_title = bookmaker['title']
            for market in bookmaker.get('markets', []):
                if market['key'] == 'h2h':
                    outcomes = market['outcomes']
                    away_dec = next((o['price'] for o in outcomes if o['name'] == selected_game_obj['away_team']), None)
                    home_dec = next((o['price'] for o in outcomes if o['name'] == selected_game_obj['home_team']), None)
                    book_rows.append({
                        "Sportsbook": b_title,
                        f"Away ({selected_game_obj['away_team']})": decimal_to_american(away_dec),
                        f"Home ({selected_game_obj['home_team']})": decimal_to_american(home_dec)
                    })
        if book_rows:
            st.dataframe(pd.DataFrame(book_rows), use_container_width=True)

    st.divider()
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
                'Anaheim Ducks': 'ANA
