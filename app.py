import streamlit as st

st.set_page_config(page_title="Sports Quant Hub", page_icon="📊", layout="wide")

st.title("📊 Sports Quant Hub: Production Suite")
st.caption("Quantitative sports modeling, schedule pace factors, and boosted compound parlay engines.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏒 NHL Quant Terminal")
    st.write("Multi-file Natural Stat Trick ingestion, dynamic 4-phase weighting, individual shot generation rates, and SOG alt-line matrices.")
    st.info("👈 Select **NHL Quant Terminal** from the sidebar to launch.")

with col2:
    st.subheader("🏈 NFL Quant Terminal")
    st.write("Play-by-play data processing, schedule pace adjustments, matchup dampening, and alt-line prop accumulators.")
    st.info("👈 Select **NFL Quant Terminal** from the sidebar to launch.")
