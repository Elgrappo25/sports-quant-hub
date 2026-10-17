import streamlit as st
import pandas as pd

st.set_page_config(page_title="Sports Quant Hub - NHL Suite", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Pro Market Suite")
st.markdown("### Multi-market evaluation including SOG, Goals, Points, Assists, Power-Play Points, and Flexible Boost Optimization.")

# Sidebar for global settings (Now using a custom number input from 0 to 100%)
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=40, step=5)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

# Navigation Tabs
tab1, tab2, tab3 = st.tabs(["📊 Smart Market Evaluator", "📁 Batch CSV Data Sheet", "🚀 Boost & Parlay Optimizer"])

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

    # Automatically set smart defaults based on selected market type
    if market_type == "Shots on Goal (SOG)":
        default_base = 3.85
        default_curr = 4.20
        default_line = 3.5
        default_odds = -120
    elif market_type == "Points (G+A)":
        default_base = 1.15
        default_curr = 1.30
        default_line = 1.5
        default_odds = +115
    elif market_type == "Anytime Goal Scorer":
        default_base = 0.65
        default_curr = 0.75
        default_line = 0.5
        default_odds = +135
    elif market_type == "Assists Only":
        default_base = 0.80
        default_curr = 0.90
        default_line = 0.5
        default_odds = -110
    else:  # Power-Play Points (PPP)
        default_base = 0.45
        default_curr = 0.55
        default_line = 0.5
        default_odds = +140

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

    # Convert American odds to decimal
    if sportsbook_odds > 0:
        dec_odds = 1 + (sportsbook_odds / 100)
    else:
        dec_odds = 1 + (100 / abs(sportsbook_odds))

    # Apply global boost if active
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
    st.subheader("Upload Daily Data Sheet")
    st.write("Upload a CSV file containing player stats to batch-calculate edges across the entire slate.")
    st.info("💡 **Required CSV Column Names:** `Player`, `Baseline_Stat`, `Current_Stat`, `Line`, `Odds`")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write("### 📋 Raw Uploaded Data:")
        st.dataframe(df)
        try:
            df['Blended_Proj'] = (df['Baseline_Stat'] * (1 - (season_weight / 100))) + (df['Current_Stat'] * (season_weight / 100))
            df['Edge'] = df['Blended_Proj'] - df['Line']
            st.write("### 📈 Processed Model Edges (Sorted High to Low):")
            st.dataframe(df.sort_values(by='Edge', ascending=False))
        except Exception as e:
            st.error(f"Error processing columns. Ensure column names match: Player, Baseline_Stat, Current_Stat, Line, Odds. Details: {e}")
    else:
        st.write("### 🔎 Example CSV Format Preview:")
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
    
    # Flexible boost number input for parlays too!
    boost_val = st.number_input("Apply Profit Boost to Parlay (%)", min_value=0, max_value=100, value=30, step=5)
    
    profit_frac = combined_parlay_dec - 1
    boosted_parlay_dec = 1 + (profit_frac * (1 + (boost_val / 100)))
    boosted_parlay_american = int((boosted_parlay_dec - 1) * 100) if boosted_parlay_dec >= 2 else int(-100 / (boosted_parlay_dec - 1))
    
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric(label="Standard 2-Leg Parlay Odds", value=f"{parlay_american:+d}")
    col_res2.metric(label=f"Boosted Parlay Odds (+{boost_val}%)", value=f"{boosted_parlay_american:+d}")
    
    st.success(f"🎯 **Parlay Ready:** Combining **{leg1_name}** and **{leg2_name}** with a {boost_val}% boost yields **{boosted_parlay_american:+d}** odds!")
