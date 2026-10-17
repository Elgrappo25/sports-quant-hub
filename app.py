import streamlit as st

st.set_page_config(page_title="Sports Quant Hub", page_icon="🏀", layout="wide")

st.title("🎯 Sports Quant Hub")
st.markdown("### Welcome to your automated sports betting analytics engine.")
st.write("Your baseline pipeline is live. Next, we will hook up your NHL Shot-on-Goal model and live odds feeds right here.")

# Quick interactive test slider
st.divider()
st.subheader("🧪 Quick Test Calculator: Kelly Criterion Check")
bankroll = st.number_input("Total Bankroll ($)", value=1000, step=100)
odds_american = st.number_input("American Odds (e.g., +110)", value=110, step=10)
win_prob = st.slider("Model True Win Probability (%)", min_value=1, max_value=99, value=52)

# Simple math check
if odds_american > 0:
    decimal_odds = 1 + (odds_american / 100)
else:
    decimal_odds = 1 + (100 / abs(odds_american))

implied_prob = 1 / decimal_odds
edge = (win_prob / 100) - implied_prob

st.write(f"**Implied Market Probability:** {implied_prob:.1%}")
st.write(f"**Your Model Edge:** {edge:+.1%}")

if edge > 0:
    st.success("✅ **+EV Play Identified!** Edge is positive.")
else:
    st.warning("⚠️ **-EV Play.** Negative or neutral edge.")
