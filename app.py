import streamlit as st

st.set_page_config(page_title="Sports Quant Hub - NHL SOG", page_icon="🏒", layout="wide")

st.title("🏒 NHL Shot-on-Goal & Boost Evaluator")
st.markdown("### Blend historical baselines with current-season sample sizes to find true SOG edges.")

# Sidebar for settings
st.sidebar.header("⚙️ Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=40, step=5)
boost_percent = st.sidebar.selectbox("Sportsbook Profit Boost (%)", [0, 25, 30, 50], index=2)

st.divider()

# Sample Player Input Card
st.subheader("📊 Player Prop Evaluator")

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

# Blended Projection Calculation
blended_sog = (historical_sog * (1 - (season_weight / 100))) + (current_sog * (season_weight / 100))

st.markdown("### 📈 Model Output & Pricing")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.metric(label="Blended Expected SOG", value=f"{blended_sog:.2f}")

# Convert American odds to decimal and implied probability
if sportsbook_odds > 0:
    dec_odds = 1 + (sportsbook_odds / 100)
else:
    dec_odds = 1 + (100 / abs(sportsbook_odds))

# Apply boost if selected
if boost_percent > 0:
    profit_fraction = dec_odds - 1
    boosted_profit = profit_fraction * (1 + (boost_percent / 100))
    boosted_dec_odds = 1 + boosted_profit
    effective_odds_american = int((boosted_dec_odds - 1) * 100) if boosted_dec_odds >= 2 else int(-100 / (boosted_dec_odds - 1))
else:
    boosted_dec_odds = dec_odds
    effective_odds_american = sportsbook_odds

with col_b:
    boost_label = f" (+{boost_percent}% Boost)" if boost_percent > 0 else ""
    st.metric(label=f"Effective Odds{boost_label}", value=f"{effective_odds_american:+d}")

with col_c:
    implied_prob = 1 / boosted_dec_odds
    edge_spread = blended_sog - sportsbook_line
    st.metric(label="Line Diff vs SOG", value=f"{edge_spread:+.2f}")

if edge_spread > 0.4:
    st.success(f"✅ **Strong Over Play:** {player_name} projects for {blended_sog:.2f} SOG against a {sportsbook_line} line.")
elif edge_spread < -0.4:
    st.warning(f"⚠️ **Under Consideration / Pass:** Projection ({blended_sog:.2f}) does not clear safety margin.")
else:
    st.info("ℹ️ **Neutral Spot:** Line is efficiently priced close to model baseline.")

st.divider()

if st.button("🚀 Push Alert to Discord (Simulated)"):
    st.balloons()
    st.success(f"Successfully formatted and sent alert for **{player_name} Over {sportsbook_line} SOG** at {effective_odds_american:+d}!")
