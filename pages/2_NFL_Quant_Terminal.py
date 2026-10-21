import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
from modules.nfl_engine import (
    compute_nfl_team_baselines,
    calculate_matchup_factors_for_slate,
    process_nfl_player_matrix,
    prob_to_american_odds,
    WEEK_7_SCHEDULE
)

st.set_page_config(page_title="NFL Quant Terminal: Production Suite", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    </style>
""", unsafe_allow_html=True)

# Helper functions for American Odds calculation
def american_to_decimal(odds):
    try:
        odds = float(odds)
        if odds > 0:
            return 1.0 + (odds / 100.0)
        elif odds < 0:
            return 1.0 + (100.0 / abs(odds))
        return 1.0
    except (ValueError, TypeError):
        return 1.0

def decimal_to_american(dec):
    if dec <= 1.0:
        return "+100"
    if dec >= 2.0:
        val = int(round((dec - 1.0) * 100))
        return f"+{val}"
    else:
        val = int(round(-100 / (dec - 1.0)))
        return f"{val}"

# Initialize session state for bet slip
if "nfl_bet_slip" not in st.session_state:
    st.session_state.nfl_bet_slip = []

# Top Header
st.title("🏈 NFL Quant Terminal: Production Suite")
st.subheader("Multi-Market Accumulator, Schedule Pace Matchups, and Compound Parlay Generator")

# Sidebar settings
with st.sidebar:
    st.header("⚙️ NFL Model Settings")
    st.caption("Active Slate: 2026 Week 7")
    min_gp = st.slider("Minimum Player Games Played (GP)", min_value=1, max_value=6, value=3)
    profit_boost_pct = st.slider("Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)
    st.divider()
    st.info("💡 Tip: Multi-select matchups in Tab 2 to isolate high-pace shootouts.")

tab1, tab2 = st.tabs(["📑 Checked Slips & Nexus Odds Comparator", "📁 Slate Matrix & Projections"])

# ==========================================
# TAB 1: BET SLIP & LIVE EDGE EVALUATION
# ==========================================
with tab1:
    st.subheader("📝 Checked Players & Nexus Odds Comparator")
    st.caption("Type your Nexus Odds in the table. Real-time edges and compound parlay odds calculate live below.")

    col_btn, _ = st.columns([1, 5])
    with col_btn:
        if st.button("🗑️ Clear Bet Slip", use_container_width=True):
            st.session_state.nfl_bet_slip = []
            st.rerun()

    if not st.session_state.nfl_bet_slip:
        st.info("💡 Instructions: Go to Tab 2, select your market and line, check your desired players, and click '➕ Add Checked Players to Bet Slip'.")
    else:
        slip_df = pd.DataFrame(st.session_state.nfl_bet_slip)

        # Ensure all columns exist
        if "Include in Parlay" not in slip_df.columns:
            slip_df.insert(0, "Include in Parlay", True)
        if "Sportsbook" not in slip_df.columns:
            slip_df.insert(1, "Sportsbook", "FanDuel")
        if "Nexus Odds (+/-)" not in slip_df.columns:
            slip_df["Nexus Odds (+/-)"] = None
        if "Delete" not in slip_df.columns:
            slip_df["Delete"] = False

        column_config = {
            "Include in Parlay": st.column_config.CheckboxColumn("Include in Parlay", default=True),
            "Sportsbook": st.column_config.SelectboxColumn(
                "Sportsbook",
                options=["FanDuel", "DraftKings", "BetMGM", "Bet365", "BetRivers", "ESPN BET", "Pinnacle"],
                default="FanDuel",
                required=True
            ),
            "Player": st.column_config.TextColumn("Player", disabled=True),
            "Opponent": st.column_config.TextColumn("Opponent", disabled=True),
            "Market": st.column_config.TextColumn("Market", disabled=True),
            "Line": st.column_config.NumberColumn("Line", disabled=True),
            "Nexus Odds (+/-)": st.column_config.NumberColumn("Nexus Odds (+/-)", step=5),
            "Model Prob (%)": st.column_config.TextColumn("Model Prob (%)", disabled=True),
            "Delete": st.column_config.CheckboxColumn("Delete", default=False)
        }

        cols_order = [
            "Include in Parlay", "Sportsbook", "Player", "Opponent", 
            "Market", "Line", "Nexus Odds (+/-)", "Model Prob (%)", "Delete"
        ]
        slip_df = slip_df[[c for c in cols_order if c in slip_df.columns]]

        edited_slip = st.data_editor(
            slip_df,
            column_config=column_config,
            use_container_width=True,
            hide_index=False,
            key="nfl_slip_editor"
        )

        # Handle row deletions
        if edited_slip["Delete"].any():
            st.session_state.nfl_bet_slip = edited_slip[~edited_slip["Delete"]].to_dict('records')
            st.rerun()

        st.session_state.nfl_bet_slip = edited_slip.to_dict('records')

        # Live Edge Evaluation (only for rows where Odds are provided)
        eval_rows = []
        parlay_true_prob = 1.0
        parlay_dec_odds = 1.0
        has_parlay_legs = False

        for idx, row in edited_slip.iterrows():
            odds_val = row.get("Nexus Odds (+/-)")
            if pd.notna(odds_val) and str(odds_val).strip() != "" and odds_val is not None:
                try:
                    user_odds = float(odds_val)
                    dec_odds = american_to_decimal(user_odds)
                    implied_prob = 1.0 / dec_odds
                    
                    prob_str = str(row["Model Prob (%)"]).replace("%", "")
                    model_prob = float(prob_str) / 100.0
                    
                    edge_pct = (model_prob - implied_prob) * 100.0
                    
                    eval_rows.append({
                        "Sportsbook": row["Sportsbook"],
                        "Player": row["Player"],
                        "Opponent": row["Opponent"],
                        "Market": row["Market"],
                        "Line": row["Line"],
                        "Odds": f"+{int(user_odds)}" if user_odds > 0 else f"{int(user_odds)}",
                        "Model Prob": f"{round(model_prob * 100, 1)}%",
                        "Edge %": f"{'+' if edge_pct > 0 else ''}{round(edge_pct, 1)}%"
                    })
                    
                    if row.get("Include in Parlay", True):
                        parlay_true_prob *= model_prob
                        parlay_dec_odds *= dec_odds
                        has_parlay_legs = True
                except (ValueError, TypeError):
                    continue

        if eval_rows:
            st.subheader("📈 Live Edge Evaluation:")
            eval_df = pd.DataFrame(eval_rows)
            st.dataframe(eval_df, use_container_width=True)

        if has_parlay_legs:
            st.subheader("🚀 Live Compound Slip & Profit Boost Calculator")
            boost_mult = 1.0 + (profit_boost_pct / 100.0)
            boosted_dec = 1.0 + ((parlay_dec_odds - 1.0) * boost_mult)
            
            raw_parlay_american = decimal_to_american(parlay_dec_odds)
            boosted_american = decimal_to_american(boosted_dec)
            
            implied_boosted_prob = 1.0 / boosted_dec
            compound_edge = (parlay_true_prob - implied_boosted_prob) * 100.0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Checked Parlay Odds", raw_parlay_american)
            c2.metric(f"Boosted (+{profit_boost_pct}%)", boosted_american)
            c3.metric("Model Slip True Prob", f"{round(parlay_true_prob * 100, 1)}%")
            c4.metric("Compound Slip Edge", f"{'+' if compound_edge > 0 else ''}{round(compound_edge, 1)}%")


# ==========================================
# TAB 2: SLATE MATRIX & PROJECTIONS
# ==========================================
with tab2:
    st.subheader("Single Dropzone: NFL Play-by-Play Processor")
    uploaded_file = st.file_uploader("Drop your pbp-2026.csv file here", type=["csv"])

    if uploaded_file is not None:
        try:
            @st.cache_data
            def load_pbp_data(file):
                return pd.read_csv(file, low_memory=False)

            df = load_pbp_data(uploaded_file)
            baselines = compute_nfl_team_baselines(df)
            
            col_mkt, col_line = st.columns(2)
            with col_mkt:
                target_market = st.selectbox(
                    "Select Target Prop Market",
                    ["Passing Yards", "Rushing Yards", "Receiving Yards", "Receptions", "Anytime Touchdown Scorer"]
                )
            
            with col_line:
                if target_market == "Passing Yards":
                    default_lines = [199.5, 224.5, 249.5, 274.5, 299.5]
                elif target_market in ["Rushing Yards", "Receiving Yards"]:
                    default_lines = [24.5, 39.5, 49.5, 59.5, 69.5, 79.5, 99.5]
                elif target_market == "Receptions":
                    default_lines = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
                else:
                    default_lines = [0.5]
                target_line = st.selectbox("Select Target Threshold Line", default_lines, index=min(1, len(default_lines)-1))

            st.date_input("Target Slate Date", value=date(2026, 10, 25))

            # Matchup badges
            all_matchups = calculate_matchup_factors_for_slate(WEEK_7_SCHEDULE, baselines)
            matchup_options = [f"{m['matchup']} [{m['combined_factor']}{' 🔥' if m['is_fire'] else ''}]" for m in all_matchups]
            
            selected_badge_strings = st.multiselect(
                "🎯 Filter Specific Game Matchups (Sorted by Pace Factor)",
                options=matchup_options,
                default=matchup_options
            )
            
            selected_matchups = []
            for m in all_matchups:
                badge_str = f"{m['matchup']} [{m['combined_factor']}{' 🔥' if m['is_fire'] else ''}]"
                if badge_str in selected_badge_strings:
                    selected_matchups.append(m)

            matrix_df = process_nfl_player_matrix(
                df, baselines, selected_matchups, target_market, target_line, min_gp=min_gp
            )

            if not matrix_df.empty:
                st.subheader(f"📈 Slate Alt-Line Matrix ({target_market} > {target_line}):")
                matrix_df.insert(0, "Select", False)

                grid_cfg = {
                    "Select": st.column_config.CheckboxColumn("Select", default=False),
                    "Baseline_Stat": st.column_config.NumberColumn(format="%.1f"),
                    "Current_Stat": st.column_config.NumberColumn(format="%.1f"),
                    "Matchup_Factor": st.column_config.NumberColumn(format="%.4f"),
                    "Matchup_Proj": st.column_config.NumberColumn(format="%.1f"),
                    "Model_Over_Prob_%": st.column_config.NumberColumn(format="%.1f%%"),
                    "Fair_American_Odds": st.column_config.NumberColumn()
                }

                edited_matrix = st.data_editor(
                    matrix_df,
                    column_config=grid_cfg,
                    use_container_width=True,
                    hide_index=True,
                    key=f"nfl_matrix_{target_market}_{target_line}"
                )

                col_add, col_auto = st.columns([1, 1])
                with col_add:
                    if st.button("➕ Add Checked Players to Bet Slip", use_container_width=True):
                        checked_rows = edited_matrix[edited_matrix["Select"] == True]
                        if not checked_rows.empty:
                            for _, r in checked_rows.iterrows():
                                st.session_state.nfl_bet_slip.append({
                                    "Include in Parlay": True,
                                    "Sportsbook": "FanDuel",
                                    "Player": r["Player"],
                                    "Opponent": r["Opponent"],
                                    "Market": r["Market"],
                                    "Line": r["Line"],
                                    "Nexus Odds (+/-)": None,
                                    "Model Prob (%)": f"{r['Model_Over_Prob_%']}%",
                                    "Delete": False
                                })
                            st.success(f"Added {len(checked_rows)} player(s) to Tab 1!")
                            st.rerun()

                with col_auto:
                    if st.button("⚡ Auto-Load Top 5 Matchup-Weighted Legs", use_container_width=True):
                        top5 = edited_matrix.head(5)
                        for _, r in top5.iterrows():
                            st.session_state.nfl_bet_slip.append({
                                "Include in Parlay": True,
                                "Sportsbook": "FanDuel",
                                "Player": r["Player"],
                                "Opponent": r["Opponent"],
                                "Market": r["Market"],
                                "Line": r["Line"],
                                "Nexus Odds (+/-)": None,
                                "Model Prob (%)": f"{r['Model_Over_Prob_%']}%",
                                "Delete": False
                            })
                        st.success("Auto-loaded Top 5 legs to Tab 1!")
                        st.rerun()
            else:
                st.warning("No qualifying players found for current filters.")
        except Exception as e:
            st.error(f"Error processing play-by-play file: {e}")
    else:
        st.info("Awaiting pbp-2026.csv upload to compute baselines and render slate projections.")
