import streamlit as st
import pandas as pd
import requests
from datetime import date

st.set_page_config(page_title="Sports Quant Hub - NHL Pro Terminal", page_icon="🏒", layout="wide")

st.title("🏒 NHL Quant Terminal: Production Suite")
st.markdown("### Count-based per-game scaling, schedule-filtered slate matching, and multi-season processing.")

# Sidebar for global settings
st.sidebar.header("⚙️ Global Model Settings")
season_weight = st.sidebar.slider("Current Season Sample Weight (%)", min_value=10, max_value=90, value=15, step=5)
global_boost = st.sidebar.number_input("Active Sportsbook Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)

# Navigation Tabs
tab1, tab2, tab3 = st.tabs([
    "📊 Smart Market Evaluator", 
    "📁 Multi-File NST Uploader & Slate Matcher", 
    "🚀 Boost & Parlay Optimizer"
])

with tab1:
    st.subheader("Dynamic Prop & Alt-Line Evaluator (Quick Scratchpad)")
    st.write("Use this tab for fast, manual on-the-fly calculations for any single prop or alternate line.")
    
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

    if market_type == "Shots on Goal (SOG)":
        default_base, default_curr, default_line, default_odds = 3.74, 2.29, 3.5, -120
    elif market_type == "Points (G+A)":
        default_base, default_curr, default_line, default_odds = 1.68, 2.57, 1.5, +115
    elif market_type == "Anytime Goal Scorer":
        default_base, default_curr, default_line, default_odds = 0.58, 0.57, 0.5, +135
    elif market_type == "Assists Only":
        default_base, default_curr, default_line, default_odds = 1.10, 1.71, 0.5, -110
    else:  # Power-Play Points (PPP)
        default_base, default_curr, default_line, default_odds = 0.75, 0.85, 0.5, +140

    with col2:
        baseline_stat = st.number_input("Multi-Year Baseline / Game", value=default_base, step=0.05)
        current_stat = st.number_input("Current Season Stat / Game", value=default_curr, step=0.05)

    with col3:
        sportsbook_line = st.number_input("Sportsbook Line (Standard or Alt)", value=default_line, step=0.5)
        sportsbook_odds = st.number_input("Sportsbook Odds (American)", value=default_odds, step=5)

    blended_projection = (baseline_stat * (1 - (season_weight / 100))) + (current_stat * (season_weight / 100))

    st.markdown(f"### 📈 Model Output: {market_type}")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric(label=f"Blended Expected Value", value=f"{blended_projection:.2f}")

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
    st.subheader("Single Dropzone: Multi-File NST Processor & Slate Matcher")
    st.write("Drop your 4 Natural Stat Trick count files below. Projections are calculated directly from Total Counts / GP.")
    
    batch_market = st.selectbox(
        "Select Target Prop Market", 
        [
            "Shots on Goal (SOG)", 
            "Points (G+A)", 
            "Anytime Goal Scorer", 
            "Assists Only", 
            "Power-Play Points (PPP)"
        ],
        key="multi_batch_market"
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
                # Automatically distinguish current season (small GP / early season) vs previous season (large GP)
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
            active_teams = set()
            try:
                sched_url = f"https://api-web.nhle.com/v1/schedule/{target_date.strftime('%Y-%m-%d')}"
                sched_resp = requests.get(sched_url).json()
                for week_day in sched_resp.get("gameWeek", []):
                    if week_day.get("date") == target_date.strftime('%Y-%m-%d'):
                        for game in week_day.get("games", []):
                            away_abbrev = game.get("awayTeam", {}).get("abbrev")
                            home_abbrev = game.get("homeTeam", {}).get("abbrev")
                            if away_abbrev: active_teams.add(away_abbrev)
                            if home_abbrev: active_teams.add(home_abbrev)
            except Exception as e:
                st.warning(f"Schedule fetch warning: {e}")

            # Map markets to Count columns in NST files
            col_map = {
                "Shots on Goal (SOG)": "Shots",
                "Points (G+A)": "Total Points",
                "Anytime Goal Scorer": "Goals",
                "Assists Only": "Total Assists",
                "Power-Play Points (PPP)": "Total Points" # fallback if specific PPP col differs
            }
            target_col = col_map.get(batch_market, "Total Points")

            if target_col in curr_player_df.columns and target_col in prev_player_df.columns:
                merged_df = pd.merge(curr_player_df, prev_player_df, on='Player', suffixes=('_curr', '_prev'), how='inner')
                
                # PER-GAME COUNT CALCULATION: Total Count / Games Played (GP)
                gp_prev = merged_df.get('GP_prev', pd.Series([82]*len(merged_df))).replace(0, 1)
                gp_curr = merged_df.get('GP_curr', pd.Series([5]*len(merged_df))).replace(0, 1)
                
                merged_df['Baseline_Stat'] = merged_df[f'{target_col}_prev'] / gp_prev
                merged_df['Current_Stat'] = merged_df[f'{target_col}_curr'] / gp_curr
                
                merged_df['Blended_Proj'] = (merged_df['Baseline_Stat'] * (1 - (season_weight / 100))) + (merged_df['Current_Stat'] * (season_weight / 100))
                
                team_col = 'Team_curr' if 'Team_curr' in merged_df.columns else ('Team' if 'Team' in merged_df.columns else 'Team_prev')
                
                filter_slate = st.checkbox("Filter by Today's Active Slate Only", value=True)
                if filter_slate and active_teams and team_col in merged_df.columns:
                    filtered_df = merged_df[merged_df[team_col].isin(active_teams)].copy()
                    if len(filtered_df) > 0:
                        merged_df = filtered_df
                        st.success(f"📅 **Slate Filter Active:** Showing **{len(merged_df)} players** playing on {target_date}.")
                    else:
                        st.info("ℹ️ Showing full player pool (team abbreviation mismatch with API).")
                
                st.write(f"### 📈 Slate Projections Board ({batch_market}):")
                display_cols = ['Player', team_col, 'Baseline_Stat', 'Current_Stat', 'Blended_Proj']
                st.dataframe(
                    merged_df[display_cols].sort_values(by='Blended_Proj', ascending=False).reset_index(drop=True),
                    use_container_width=True,
                    height=500
                )
            else:
                st.error(f"Could not find column '{target_col}' in player files.")
        else:
            st.warning("Please upload both Player Season Total CSV files.")
    else:
        st.info("💡 **Instructions:** Drop all 4 files above to generate slate projections.")

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
