import streamlit as st
import pandas as pd

st.set_page_config(page_title="Sports Quant Hub - NHL Suite", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: SOG, Points & Boost Optimizer")
st.markdown("### Evaluate standard lines, alternate markets, batch sheets, and profit-boost parlays.")

# Sidebar for global settings
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=40, step=5)
global_boost = st.sidebar.selectbox("Active Sportsbook Profit Boost (%)", [0, 25, 30, 50], index=2)

# Navigation Tabs
tab1, tab2, tab3 = st.tabs(["📊 Prop & Alt-Line Evaluator", "📁 Batch CSV Data Sheet", "🚀 Boost & Parlay Optimizer"])

with tab1:
    st.subheader("Single Player Prop & Alternate Line Evaluator")
    
    col1, col2, col3 = st.columns(3)

    with col1:
        player_name = st.text_input("Player Name", value="Auston Matthews")
        market_type = st.selectbox("Market Type", ["Shots on Goal (SOG)", "Points (G+A)", "Anytime Goal Scorer"])

    with col2:
        baseline_stat = st.number_input("Multi-Year Baseline / Game", value=3.85, step=0.05)
        current_stat = st.number_input("Current Season Stat / Game", value=4.20, step=0.05)

    with col3:
        sportsbook_line = st.number_input("Sportsbook Line (Standard or Alt)", value=3.5, step=0.5)
        sportsbook_odds = st.number_input("Sportsbook Odds (American)", value=+110, step=5)

    # Blended Projection Calculation
    blended_projection = (baseline_stat * (1 - (season_weight / 100))) + (current_stat * (season_weight / 100))

    st.markdown("### 📈 Model Output & Pricing")

    col_a, col_b, col_c = st.columns(3)

    col_a.metric(label=f"Blended Expected {market_type.split()[0]}", value=f"{blended_projection:.2f}")

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

    if edge_spread > 0.3:
        st.success(f"✅ **Strong Over / Alt Play:** {player_name} projects for {blended_projection:.2f} against the {sportsbook_line} line.")
    elif edge_spread < -0.3:
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
            'Player': ['Auston Matthews', 'Connor McDavid', 'Nathan MacKinnon', 'David Pastrnak'],
            'Baseline_Stat': [3.85, 4.10, 4.25, 3.90],
            'Current_Stat': [4.20, 4.40, 4.50, 4.10],
            'Line': [4.5, 4.5, 5.5, 4.5],
            'Odds': [+135, +125, +160, +140]
        })
        st.dataframe(example_data)

with tab3:
    st.subheader("🚀 Boost & Parlay Compound Optimizer")
    st.write("Test multi-leg slips and profit boosts to verify true expected value (+EV).")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        leg1_name = st.text_input("Leg 1 Player / Prop", value="Matthews Over 3.5 SOG")
        leg1_odds = st.number_input("Leg 1 American Odds", value=-120, step=5)
    with col_p2:
        leg2_name = st.text_input("Leg 2 Player / Prop", value="McDavid Over 1.5 Points")
        leg2_odds = st.number_input("Leg 2 American Odds", value=+100, step=5)
        
    # Convert leg odds to decimal
    dec1 = 1 + (leg1_odds / 100) if leg1_odds > 0 else 1 + (100 / abs(leg1_odds))
    dec2 = 1 + (leg2_odds / 100) if leg2_odds > 0 else 1 + (100 / abs(leg2_odds))
    
    combined_parlay_dec = dec1 * dec2
    parlay_american = int((combined_parlay_dec - 1) * 100) if combined_parlay_dec >= 2 else int(-100 / (combined_parlay_dec - 1))
    
    # Apply boost to parlay
    boost_val = st.selectbox("Apply Profit Boost to Parlay", [25, 30, 50], index=1)
    profit_frac = combined_parlay_dec - 1
    boosted_parlay_dec = 1 + (profit_frac * (1 + (boost_val / 100)))
    boosted_parlay_american = int((boosted_parlay_dec - 1) * 100) if boosted_parlay_dec >= 2 else int(-100 / (boosted_parlay_dec - 1))
    
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric(label="Standard 2-Leg Parlay Odds", value=f"{parlay_american:+d}")
    col_res2.metric(label=f"Boosted Parlay Odds (+{boost_val}%)", value=f"{boosted_parlay_american:+d}")
    
    st.success(f"🎯 **Parlay Ready:** Combining **{leg1_name}** and **{leg2_name}** with a {boost_val}% boost yields **{boosted_parlay_american:+d}** odds!")
