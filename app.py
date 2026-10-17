import streamlit as st
import pandas as pd
import requests
from datetime import date

st.set_page_config(page_title="Sports Quant Hub - NHL Pro Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Complete Production Suite")
st.markdown("### Live multi-market evaluation, NST batch sheet processing, boost optimization, and live schedule tracking.")

# Sidebar for global settings
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=40, step=5)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

# Navigation Tabs (Added Live Schedule Tab!)
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Smart Market Evaluator", 
    "📁 NST Batch CSV Uploader", 
    "🚀 Boost & Parlay Optimizer",
    "📅 Live NHL Schedule & Matchups"
])

with tab1:
    st.subheader("Dynamic Prop & Alt-Line Evaluator")
    
    col1, col2, col3 = st.columns(3)

    with col1:
        player_name = st.text_input("Player Name", value="Connor McDavid")
        market_type = st.selectbox(
            "Market Type", 
            [
                "Shots on Goal (SOG)", 
                "Points (G+A)", 
                "Anytime Goal Scorer", 
                "Assists Only", 
                "Power-Play Points (PPP)"
            ]
        )

    # Smart defaults based on market type
    if market_type == "Shots on Goal (SOG)":
        default_base, default_curr, default_line, default_odds = 3.85, 4.20, 3.5, -120
    elif market_type == "Points (G+A)":
        default_base, default_curr, default_line, default_odds = 1.15, 1.30, 1.5, +115
    elif market_type == "Anytime Goal Scorer":
        default_base, default_curr, default_line, default_odds = 0.65, 0.75, 0.5, +135
    elif market_type == "Assists Only":
        default_base, default_curr, default_line, default_odds = 0.80, 0.90, 0.5, -110
    else:  # Power-Play Points (PPP)
        default_base, default_curr, default_line, default_odds = 0.45, 0.55, 0.5, +140

    with col2:
        baseline_stat = st.number_input("Multi-Year Baseline / Game", value=default_base, step=0.05)
        current_stat = st.number_input("Current Season Stat / Game", value=default_curr, step=0.05)

    with col3:
        sportsbook_line = st.number_input("Sportsbook Line (Standard or Alt)", value=default_line, step=0.5)
        sportsbook_odds = st.number_input("Sportsbook Odds (American)", value=default_odds, step=5)

    # Blended Projection Calculation
    blended_projection = (baseline_stat * (1 - (season_weight / 100))) + (current_stat * (season_weight / 100))

    st.markdown(f"### 📈 Model Output: {market_type}")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric(label=f"Blended Expected Value", value=f"{blended_projection:.2f}")

    # Odds conversion & boost calculation
    if sportsbook_odds > 0:
        dec_odds = 1 + (sportsbook_odds / 100)
    else:
        dec_odds = 1 + (100 / abs(sportsbook_odds))

    if global_boost > 0:
        profit_fraction = dec_odds - 1
        boosted_profit = profit_fraction * (1 + (global_boost / 100))
        boosted_dec_odds = 1 + boosted_profit
        effective_odds_american = int((boosted_dec_odds - 1) * 100) if boosted_dec_odds >= 2 else int(-100 / (boosted_dec_odds - 1))
    else:
        boosted_dec_odds = dec_odds
        effective_odds_american = sportsbook_odds

    boost_label = f" (+{global_boost}% Boost)" if global_boost > 0 else ""
    col_b.metric(label=f"Effective Odds{boost_label}", value=f"{effective_odds_american:+d}")

    edge_spread = blended_projection - sportsbook_line
    col_c.metric(label="Line Diff vs Projection", value=f"{edge_spread:+.2f}")

    if edge_spread > 0.20:
        st.success(f"✅ **Strong Over / Alt Play:** {player_name} projects for {blended_projection:.2f} in **{market_type}** against the {sportsbook_line} line.")
    elif edge_spread < -0.20:
        st.warning(f"⚠️ **Under / Pass:** Projection ({blended_projection:.2f}) does not clear safety margin.")
    else:
        st.info("ℹ️ **Neutral Spot:** Line is efficiently priced close to model baseline.")

with tab2:
    st.subheader("Natural Stat Trick Batch Data Sheet Processor")
    st.write("Select the target market for your batch sheet, then upload your CSV to compute edges.")
    
    batch_market = st.selectbox(
        "Select Market Type for This Batch Sheet", 
        [
            "Shots on Goal (SOG)", 
            "Points (G+A)", 
            "Anytime Goal Scorer", 
            "Assists Only", 
            "Power-Play Points (PPP)"
        ],
        key="batch_market_select"
    )
    
    st.info(f"💡 **Active Batch Market:** Evaluating **{batch_market}**. Expected CSV Columns: `Player`, `Baseline_Stat`, `Current_Stat`, `Line`, `Odds`")
    
    uploaded_file = st.file_uploader("Choose a Natural Stat Trick CSV Export", type="csv")
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write(f"### 📋 Raw Uploaded Data Preview ({batch_market}):")
        st.dataframe(df.head(10))
        try:
            df['Market'] = batch_market
            df['Blended_Proj'] = (df['Baseline_Stat'] * (1 - (season_weight / 100))) + (df['Current_Stat'] * (season_weight / 100))
            df['Edge'] = df['Blended_Proj'] - df['Line']
            st.write(f"### 📈 Processed Model Edges for {batch_market} (Sorted High to Low):")
            cols_to_show = ['Player', 'Market', 'Baseline_Stat', 'Current_Stat', 'Line', 'Odds', 'Blended_Proj', 'Edge']
            st.dataframe(df[cols_to_show].sort_values(by='Edge', ascending=False))
        except Exception as e:
            st.error(f"Error processing columns. Please ensure your CSV headers include: Player, Baseline_Stat, Current_Stat, Line, Odds. Details: {e}")
    else:
        st.write("### 🔎 Example Batch Template Format:")
        example_data = pd.DataFrame({
            'Player': ['Connor McDavid', 'Cale Makar', 'Leon Draisaitl', 'Auston Matthews'],
            'Baseline_Stat': [0.90, 0.50, 0.85, 0.65],
            'Current_Stat': [1.05, 0.60, 0.95, 0.75],
            'Line': [0.5, 0.5, 0.5, 1.5],
            'Odds': [-110, +130, -105, +170]
        })
        st.dataframe(example_data)

with tab3:
    st.subheader("🚀 Boost & Parlay Compound Optimizer")
    st.write("Test multi-leg slips and profit boosts to verify true expected value (+EV).")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        leg1_name = st.text_input("Leg 1 Player / Prop", value="McDavid Over 0.5 Assists")
        leg1_odds = st.number_input("Leg 1 American Odds", value=-110, step=5)
    with col_p2:
        leg2_name = st.text_input("Leg 2 Player / Prop", value="Draisaitl Over 0.5 PPP")
        leg2_odds = st.number_input("Leg 2 American Odds", value=+130, step=5)
        
    dec1 = 1 + (leg1_odds / 100) if leg1_odds > 0 else 1 + (100 / abs(leg1_odds))
    dec2 = 1 + (leg2_odds / 100) if leg2_odds > 0 else 1 + (100 / abs(leg2_odds))
    
    combined_parlay_dec = dec1 * dec2
    parlay_american = int((combined_parlay_dec - 1) * 100) if combined_parlay_dec >= 2 else int(-100 / (combined_parlay_dec - 1))
    
    boost_val = st.number_input("Apply Profit Boost to Parlay (%)", min_value=0, max_value=100, value=30, step=5)
    
    profit_frac = combined_parlay_dec - 1
    boosted_parlay_dec = 1 + (profit_frac * (1 + (boost_val / 100)))
    boosted_parlay_american = int((boosted_parlay_dec - 1) * 100) if boosted_parlay_dec >= 2 else int(-100 / (boosted_parlay_dec - 1))
    
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric(label="Standard 2-Leg Parlay Odds", value=f"{parlay_american:+d}")
    col_res2.metric(label=f"Boosted Parlay Odds (+{boost_val}%)", value=f"{boosted_parlay_american:+d}")
    
    st.success(f"🎯 **Parlay Ready:** Combining **{leg1_name}** and **{leg2_name}** with a {boost_val}% boost yields **{boosted_parlay_american:+d}** odds!")

with tab4:
    st.subheader("📅 Live NHL Game Schedule & Matchups")
    st.write("Automatically pull today's scheduled games and team matchups straight from the official NHL data feed.")
    
    selected_date = st.date_input("Select Date", value=date.today())
    
    if st.button("Fetch Live Schedule"):
        try:
            url = f"https://api-web.nhle.com/v1/schedule/{selected_date.strftime('%Y-%m-%d')}"
            response = requests.get(url)
            data = response.json()
            
            games_found = False
            for week_day in data.get("gameWeek", []):
                if week_day.get("date") == selected_date.strftime('%Y-%m-%d'):
                    games = week_day.get("games", [])
                    if games:
                        games_found = True
                        st.success(f"Successfully loaded {len(games)} games for {selected_date}!")
                        for idx, game in enumerate(games, 1):
                            away_team = game.get("awayTeam", {}).get("commonName", {}).get("default", "Away")
                            home_team = game.get("homeTeam", {}).get("commonName", {}).get("default", "Home")
                            game_state = game.get("gameState", "FUT")
                            st.markdown(f"**Game {idx}:** {away_team} @ {home_team} *(Status: {game_state})*")
                    else:
                        st.warning(f"No games found for {selected_date}.")
            if not games_found:
                st.info("No game schedule data returned for this date.")
        except Exception as e:
            st.error(f"Could not fetch live schedule data: {e}")
    else:
        st.markdown("*Click the button above to fetch today's live NHL matchups.*")
