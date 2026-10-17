import streamlit as st
import pandas as pd

st.set_page_config(page_title="Sports Quant Hub - NHL SOG", page_icon="🏒", layout="wide")

st.title("🏒 NHL Shot-on-Goal & Boost Evaluator (Batch Mode)")
st.markdown("### Run individual player lookups or upload your daily data sheet.")

# Sidebar for settings
st.sidebar.header("⚙️ Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=40, step=5)
boost_percent = st.sidebar.selectbox("Sportsbook Profit Boost (%)", [0, 25, 30, 50], index=2)

# Tabs for Single vs Batch Mode
tab1, tab2 = st.tabs(["📊 Single Player Evaluator", "📁 Batch CSV Data Sheet Uploader"])

with tab1:
    st.subheader("Single Player Lookup")
    
    col1, col2, col3 = st.columns(3)

    with col1:
        player_name = st.text_input("Player Name", value="Auston Matthews")
        position = st.selectbox("Position / Role", ["1C / PP1", "Winger / PP1", "Defense / PP1"])

    with col2:
        historical_sog = st.number_input("Multi-Year Baseline SOG / Game", value=3.85, step=0.05)
        current_sog = st.number_input("Current Season SOG / Game", value=4.20, step=0.05)

    with col3:
        sportsbook_line = st.number_input("Sportsbook Line", value=3.5, step=0.5)
        sportsbook_odds = st.number_input("Sportsbook Odds (American)", value=-120, step=5)

    blended_sog = (historical_sog * (1 - (season_weight / 100))) + (current_sog * (season_weight / 100))

    st.markdown("### 📈 Model Output & Pricing")

    col_a, col_b, col_c = st.columns(3)

    col_a.metric(label="Blended Expected SOG", value=f"{blended_sog:.2f}")

    if sportsbook_odds > 0:
        dec_odds = 1 + (sportsbook_odds / 100)
    else:
        dec_odds = 1 + (100 / abs(sportsbook_odds))

    if boost_percent > 0:
        profit_fraction = dec_odds - 1
        boosted_profit = profit_fraction * (1 + (boost_percent / 100))
        boosted_dec_odds = 1 + boosted_profit
        effective_odds_american = int((boosted_dec_odds - 1) * 100) if boosted_dec_odds >= 2 else int(-100 / (boosted_dec_odds - 1))
    else:
        boosted_dec_odds = dec_odds
        effective_odds_american = sportsbook_odds

    boost_label = f" (+{boost_percent}% Boost)" if boost_percent > 0 else ""
    col_b.metric(label=f"Effective Odds{boost_label}", value=f"{effective_odds_american:+d}")

    edge_spread = blended_sog - sportsbook_line
    col_c.metric(label="Line Diff vs SOG", value=f"{edge_spread:+.2f}")

    if edge_spread > 0.4:
        st.success(f"✅ **Strong Over Play:** {player_name} projects for {blended_sog:.2f} SOG against a {sportsbook_line} line.")
    elif edge_spread < -0.4:
        st.warning(f"⚠️ **Under Consideration / Pass:** Projection ({blended_sog:.2f}) does not clear safety margin.")
    else:
        st.info("ℹ️ **Neutral Spot:** Line is efficiently priced close to model baseline.")

with tab2:
    st.subheader("Upload Daily SOG Data Sheet")
    st.write("Upload a CSV file containing player stats to batch-calculate edges across the entire slate.")
    
    st.info("💡 **Required CSV Column Names:** `Player`, `Baseline_SOG`, `Current_SOG`, `Line`, `Odds`")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write("### 📋 Raw Uploaded Data:")
        st.dataframe(df)
        
        try:
            df['Blended_SOG'] = (df['Baseline_SOG'] * (1 - (season_weight / 100))) + (df['Current_SOG'] * (season_weight / 100))
            df['Edge'] = df['Blended_SOG'] - df['Line']
            st.write("### 📈 Processed Model Edges (Sorted High to Low):")
            st.dataframe(df.sort_values(by='Edge', ascending=False))
        except Exception as e:
            st.error(f"Error processing columns. Please ensure your CSV column names match: Player, Baseline_SOG, Current_SOG, Line, Odds. Details: {e}")
    else:
        st.write("### 🔎 Example CSV Format Preview:")
        example_data = pd.DataFrame({
            'Player': ['Auston Matthews', 'Connor McDavid', 'Nathan MacKinnon', 'David Pastrnak'],
            'Baseline_SOG': [3.85, 4.10, 4.25, 3.90],
            'Current_SOG': [4.20, 4.40, 4.50, 4.10],
            'Line': [3.5, 3.5, 4.5, 3.5],
            'Odds': [-120, -135, +105, -110]
        })
        st.dataframe(example_data)
        st.markdown("*Tip: You can create a file like this in Excel or Google Sheets, save it as a `.csv` file, and drop it right here to test batch processing.*")
