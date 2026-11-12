import os
import sys
from datetime import datetime, date
import numpy as np
import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.mlb_engine import (
    process_mlb_files,
    evaluate_mlb_market,
    fetch_mlb_schedule_with_fallback,
)
from modules.auto_selector import select_promo_legs, get_market_threshold_defaults

st.set_page_config(page_title="MLB Quant Terminal", layout="wide")

# ==========================================
# 0. MARKET & MILESTONE CONFIGURATION
# ==========================================
MLB_MARKET_OPTIONS = [
    "Hits + Runs + RBIs (HRR)",
    "Total Bases (TB)",
    "Hits",
    "Pitcher Strikeouts (Ks)",
    "Home Runs (HR)",
]

MLB_LINE_OPTIONS_MAP = {
    "Hits + Runs + RBIs (HRR)": [0.5, 1.5, 2.5],
    "Total Bases (TB)": [0.5, 1.5, 2.5],
    "Hits": [0.5, 1.5],
    "Pitcher Strikeouts (Ks)": [3.5, 4.5, 5.5, 6.5, 7.5, 8.5],
    "Home Runs (HR)": [0.5],
}

# Default milestone index when switching to each market:
# HRR -> 0.5 (1+ HRR), TB -> 1.5 (2+ TB), Hits -> 0.5 (1+ Hit), Ks -> 5.5, HR -> 0.5
MLB_DEFAULT_LINE_IDX = {
    "Hits + Runs + RBIs (HRR)": 0,
    "Total Bases (TB)": 1,
    "Hits": 0,
    "Pitcher Strikeouts (Ks)": 2,
    "Home Runs (HR)": 0,
}

# ==========================================
# 1. ISOLATED SESSION STATE INITIALIZATION
# ==========================================
if "mlb_bet_slip" not in st.session_state:
    st.session_state.mlb_bet_slip = []


def sync_mlb_market_filters():
    mkt = st.session_state.get("mlb_market_selector", "Hits + Runs + RBIs (HRR)")
    opts = MLB_LINE_OPTIONS_MAP.get(mkt, [0.5])
    def_idx = MLB_DEFAULT_LINE_IDX.get(mkt, 0)
    default_line = opts[def_idx] if def_idx < len(opts) else opts[0]
    line = st.session_state.get(f"mlb_line_selector_{mkt}", default_line)
    p_min, p_max = get_market_threshold_defaults(sport="MLB", market=mkt, line=line)
    st.session_state["mlb_auto_min_prob"] = p_min
    st.session_state["mlb_auto_max_prob"] = p_max


def sync_mlb_line_filters():
    mkt = st.session_state.get("mlb_market_selector", "Hits + Runs + RBIs (HRR)")
    opts = MLB_LINE_OPTIONS_MAP.get(mkt, [0.5])
    def_idx = MLB_DEFAULT_LINE_IDX.get(mkt, 0)
    default_line = opts[def_idx] if def_idx < len(opts) else opts[0]
    line = st.session_state.get(f"mlb_line_selector_{mkt}", default_line)
    p_min, p_max = get_market_threshold_defaults(sport="MLB", market=mkt, line=line)
    st.session_state["mlb_auto_min_prob"] = p_min
    st.session_state["mlb_auto_max_prob"] = p_max


def _prob_to_american(prob_pct: float) -> str:
    p = np.clip(prob_pct / 100.0, 0.01, 0.99)
    if p >= 0.5:
        odds = int(round(-100.0 * p / (1.0 - p)))
        return f"{odds}"
    else:
        odds = int(round(100.0 * (1.0 - p) / p))
        return f"+{odds}"


# ==========================================
# 2. SIDEBAR CONTROLS
# ==========================================
st.sidebar.title("⚾ MLB Quant Controls")
boost_pct = st.sidebar.slider("Active Profit Boost (%)", min_value=0, max_value=100, value=30, step=5)
min_sample = st.sidebar.slider("Min Sample (PA / BF)", min_value=0, max_value=150, value=25, step=5)

# Streamlined Auto-Selector Sidebar Controls
st.sidebar.markdown("---")
st.sidebar.header("⚡ Auto-Selector Engine")

col_p1, col_p2 = st.sidebar.columns(2)
with col_p1:
    st.number_input("Min Model Prob (%)", min_value=10.0, max_value=95.0, value=70.0, step=1.0, key="mlb_auto_min_prob")
with col_p2:
    st.number_input("Max Model Prob (%)", min_value=20.0, max_value=99.0, value=82.0, step=1.0, key="mlb_auto_max_prob")

col_l1, col_l2 = st.sidebar.columns(2)
with col_l1:
    st.number_input("Target Leg Count", min_value=1, max_value=10, value=5, step=1, key="mlb_auto_legs_count")
with col_l2:
    st.number_input("Max Per Team", min_value=1, max_value=5, value=1, step=1, key="mlb_auto_max_team")

# ==========================================
# 3. MAIN NAVIGATION TABS
# ==========================================
tab1, tab2 = st.tabs(["🚀 Live Compound Slip & Profit Boost Calculator", "📊 Slate Matrix & Projections"])

# ------------------------------------------
# TAB 1: BET SLIP & LIVE BOOST EVALUATOR
# ------------------------------------------
with tab1:
    if st.button("🗑️ Clear Bet Slip"):
        st.session_state.mlb_bet_slip = []
        st.rerun()

    if not st.session_state.mlb_bet_slip:
        st.info("Select your sportsbook and enter Nexus Odds. Real-time edges calculate automatically once entered.")
    else:
        df_slip = pd.DataFrame(st.session_state.mlb_bet_slip)

        # Ensure correct column existence and defaults
        if "Include in Parlay" not in df_slip.columns:
            df_slip["Include in Parlay"] = True
        if "Sportsbook" not in df_slip.columns:
            df_slip["Sportsbook"] = "FanDuel"
        if "Nexus Odds (+/-)" not in df_slip.columns:
            df_slip["Nexus Odds (+/-)"] = None
        if "Delete" not in df_slip.columns:
            df_slip["Delete"] = False

        column_order = [
            "Include in Parlay",
            "Sportsbook",
            "Player",
            "Opponent",
            "Market",
            "Line",
            "Nexus Odds (+/-)",
            "Model Prob (%)",
            "Delete",
        ]
        df_slip = df_slip[[c for c in column_order if c in df_slip.columns]]

        sportsbook_options = ["FanDuel", "DraftKings", "bet365", "BetMGM", "theScore Bet", "BetRivers"]

        edited_slip = st.data_editor(
            df_slip,
            column_config={
                "Include in Parlay": st.column_config.CheckboxColumn("Include in Parlay", default=True),
                "Sportsbook": st.column_config.SelectboxColumn("Sportsbook", options=sportsbook_options, default="FanDuel", required=True),
                "Player": st.column_config.TextColumn("Player", disabled=True),
                "Opponent": st.column_config.TextColumn("Opponent", disabled=True),
                "Market": st.column_config.TextColumn("Market", disabled=True),
                "Line": st.column_config.NumberColumn("Line", disabled=True),
                "Nexus Odds (+/-)": st.column_config.NumberColumn("Nexus Odds (+/-)", step=1),
                "Model Prob (%)": st.column_config.NumberColumn("Model Prob (%)", format="%.1f", disabled=True),
                "Delete": st.column_config.CheckboxColumn("Delete", default=False),
            },
            hide_index=True,
            use_container_width=True,
        )

        # Check for individual deletes
        if edited_slip["Delete"].any():
            remaining_slip = edited_slip[edited_slip["Delete"] == False].to_dict("records")
            st.session_state.mlb_bet_slip = remaining_slip
            st.rerun()
        else:
            st.session_state.mlb_bet_slip = edited_slip.to_dict("records")

        # Live Edge Evaluation
        active_legs = []
        dec_odds_list = []
        joint_model_prob = 1.0

        for idx, row in edited_slip.iterrows():
            if row["Include in Parlay"] and pd.notna(row["Nexus Odds (+/-)"]) and row["Nexus Odds (+/-)"] != 0:
                odds = int(row["Nexus Odds (+/-)"])
                m_prob = float(row["Model Prob (%)"]) / 100.0

                if odds < 0:
                    dec = 1.0 + (100.0 / abs(odds))
                    imp_prob = abs(odds) / (abs(odds) + 100.0)
                    odds_str = f"{odds}"
                else:
                    dec = 1.0 + (odds / 100.0)
                    imp_prob = 100.0 / (odds + 100.0)
                    odds_str = f"+{odds}"

                edge = (m_prob - imp_prob) * 100.0

                dec_odds_list.append(dec)
                joint_model_prob *= m_prob

                active_legs.append({
                    "Sportsbook": row["Sportsbook"],
                    "Player": row["Player"],
                    "Opponent": row["Opponent"],
                    "Market": row["Market"],
                    "Line": row["Line"],
                    "Odds": odds_str,
                    "Model Prob": f"{row['Model Prob (%)']:.1f}%",
                    "Edge %": f"{edge:+.1f}%",
                })

        st.subheader("📈 Live Edge Evaluation:")
        if active_legs:
            df_active = pd.DataFrame(active_legs)
            st.dataframe(df_active, hide_index=True, use_container_width=True)
        else:
            st.caption("Enter your Nexus Odds (+/-) in the table above to view live individual edge calculations.")

        st.divider()
        st.subheader("🚀 Live Compound Slip & Profit Boost Calculator")

        if dec_odds_list:
            parlay_dec = np.prod(dec_odds_list)
            if parlay_dec >= 2.0:
                unboosted_am = f"+{int(round((parlay_dec - 1.0) * 100))}"
                parlay_imp_prob = 100.0 / (float(unboosted_am[1:]) + 100.0)
            else:
                unboosted_am = f"{int(round(-100.0 / (parlay_dec - 1.0)))}"
                parlay_imp_prob = abs(float(unboosted_am)) / (abs(float(unboosted_am)) + 100.0)

            boosted_profit = (parlay_dec - 1.0) * (1.0 + (boost_pct / 100.0))
            boosted_dec = boosted_profit + 1.0
            if boosted_dec >= 2.0:
                boosted_am = f"+{int(round((boosted_dec - 1.0) * 100))}"
            else:
                boosted_am = f"{int(round(-100.0 / (boosted_dec - 1.0)))}"

            compound_edge = (joint_model_prob - parlay_imp_prob) * 100.0

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Checked Parlay Odds", unboosted_am)
            r2.metric(f"Boosted (+{boost_pct}%)", boosted_am)
            r3.metric("Model Slip True Prob", f"{joint_model_prob * 100:.1f}%")
            r4.metric("Compound Slip Edge", f"{compound_edge:+.1f}%")
        else:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Checked Parlay Odds", "--")
            r2.metric(f"Boosted (+{boost_pct}%)", "--")
            r3.metric("Model Slip True Prob", "--")
            r4.metric("Compound Slip Edge", "--")

# ------------------------------------------
# TAB 2: DATA INGESTION & SLATE MATRIX
# ------------------------------------------
with tab2:
    st.subheader("📁 Daily Data Ingestion")

    uploaded_files = st.file_uploader(
        "Upload MLB Data Files (Drag & drop all Ballpark Pal .xlsx/.csv & Baseball Savant .csv files together)",
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        key="mlb_central_uploader",
    )

    if not uploaded_files:
        st.info("👆 Please drop your Ballpark Pal & Baseball Savant files into the upload box above to populate the slate matrix.")
        st.stop()

    # Signature cache so switching markets/milestones is instantaneous
    file_sig = tuple(sorted((f.name, f.size) for f in uploaded_files))
    if st.session_state.get("mlb_file_sig") != file_sig:
        with st.spinner("Auto-routing Ballpark Pal & Baseball Savant datasets..."):
            parsed_data = process_mlb_files(uploaded_files)
            st.session_state["mlb_file_sig"] = file_sig
            st.session_state["mlb_parsed_data"] = parsed_data
    else:
        parsed_data = st.session_state["mlb_parsed_data"]

    if parsed_data.get("batters", pd.DataFrame()).empty and parsed_data.get("pitchers", pd.DataFrame()).empty:
        st.error("Could not detect Ballpark Pal batter or pitcher tables in the uploaded files. Please verify your uploads.")
        st.stop()

    if parsed_data.get("loaded_tags"):
        st.caption(f"✅ Auto-Routed Datasets ({len(uploaded_files)} files): " + " • ".join(parsed_data["loaded_tags"]))

    st.divider()

    # Default calendar to uploaded file's slate date (great for offseason testing) or today
    default_dt = date.today()
    if parsed_data.get("slate_date"):
        try:
            default_dt = datetime.strptime(parsed_data["slate_date"], "%Y-%m-%d").date()
        except Exception:
            pass

    selected_date = st.date_input("📅 Select Slate Date:", value=default_dt, key="mlb_date_picker")
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    slate_games = fetch_mlb_schedule_with_fallback(parsed_data, selected_date_str)

    if not slate_games:
        st.warning(f"No scheduled MLB games found for {selected_date_str}. Please select another date on the calendar.")
        st.stop()

    pill_labels = [g["pill_label"] for g in slate_games]
    pill_to_key = {g["pill_label"]: g["matchup_key"] for g in slate_games}

    selected_pills = st.multiselect("Select Games to Analyze:", pill_labels, default=pill_labels, key="mlb_game_pills")
    selected_matchup_keys = [pill_to_key[p] for p in selected_pills]

    if not selected_matchup_keys:
        st.info("Select at least one game pill above to view players.")
        st.stop()

    st.divider()

    col_m, col_l = st.columns([1, 1])
    with col_m:
        market_choice = st.selectbox(
            "Target Prop Market:",
            MLB_MARKET_OPTIONS,
            key="mlb_market_selector",
            on_change=sync_mlb_market_filters,
        )

    with col_l:
        line_opts = MLB_LINE_OPTIONS_MAP[market_choice]
        def_idx = MLB_DEFAULT_LINE_IDX.get(market_choice, 0)
        chosen_line = st.selectbox(
            "Select Milestone Alt-Line Floor:",
            line_opts,
            index=def_idx,
            key=f"mlb_line_selector_{market_choice}",
            on_change=sync_mlb_line_filters,
        )

    eval_df = evaluate_mlb_market(
        parsed_data=parsed_data,
        market=market_choice,
        line=chosen_line,
        min_sample=min_sample,
        selected_games=selected_matchup_keys,
    )

    if eval_df.empty:
        st.warning("No players met the current sample size or game filters. Try lowering Min Sample (PA / BF) in the sidebar.")
        st.stop()

    rows = []
    for _, r in eval_df.iterrows():
        prob_pct = float(r["Model_Over_Prob_%"])
        rows.append({
            "Select": False,
            "Player": r["Player"],
            "Clean_Team": r["Clean_Team"],
            "Opponent": r["Opponent_Info"],
            "Lineup_Role": r["Pos_Slot"],
            "Sample": int(r["Sample"]),
            "Key_Stat": r["Key_Stat"],
            "Base_Proj": float(r["Base_Proj"]),
            "Matchup_Factor": float(r["Matchup_Factor"]),
            "Matchup_Proj": float(r["Matchup_Proj"]),
            "Model_Over_Prob_%": prob_pct,
            "Fair_American_Odds": _prob_to_american(prob_pct),
            "Market": market_choice,
            "Line": chosen_line,
            "_Clean_Opp": r.get("Clean_Opp", ""),
        })

    matrix_df = pd.DataFrame(rows).sort_values(by="Model_Over_Prob_%", ascending=False).reset_index(drop=True)
    display_cols = [c for c in matrix_df.columns if not c.startswith("_")]

    edited_matrix = st.data_editor(
        matrix_df[display_cols],
        column_config={"Select": st.column_config.CheckboxColumn(required=True)},
        disabled=[c for c in display_cols if c != "Select"],
        hide_index=True,
        use_container_width=True,
    )

    st.write("")
    col_btn1, col_btn2 = st.columns([1, 1])

    # Left Column: Manual Add
    with col_btn1:
        if st.button("➕ Add Selected Players to Bet Slip", use_container_width=True):
            selected_rows = edited_matrix[edited_matrix["Select"] == True].to_dict("records")
            added_count = 0
            for item in selected_rows:
                if not any(
                    b["Player"] == item["Player"]
                    and b["Market"] == item["Market"]
                    and b["Line"] == item["Line"]
                    for b in st.session_state.mlb_bet_slip
                ):
                    st.session_state.mlb_bet_slip.append({
                        "Include in Parlay": True,
                        "Sportsbook": "FanDuel",
                        "Player": item["Player"],
                        "Opponent": item["Opponent"],
                        "Market": item["Market"],
                        "Line": item["Line"],
                        "Nexus Odds (+/-)": None,
                        "Model Prob (%)": item["Model_Over_Prob_%"],
                        "Delete": False,
                    })
                    added_count += 1
            if added_count > 0:
                st.rerun()

    # Right Column: Streamlined Auto-Selector Engine
    with col_btn2:
        auto_label = f"⚡ Auto-Load {st.session_state['mlb_auto_legs_count']} Promo-Weighted Legs"
        if st.button(auto_label, use_container_width=True):
            candidate_df = matrix_df.copy()

            # Anti-correlation guard: avoid pairing Pitcher Strikeout Overs with opposing batters in same game
            existing_slip = st.session_state.mlb_bet_slip
            if existing_slip:
                is_pitcher_mkt = "Strikeout" in market_choice or "Ks" in market_choice
                blocked_teams = set()
                for leg in existing_slip:
                    leg_is_pit = "Strikeout" in str(leg.get("Market", "")) or "Ks" in str(leg.get("Market", ""))
                    if is_pitcher_mkt != leg_is_pit:
                        for _, m_row in candidate_df.iterrows():
                            if m_row["Player"] == leg.get("Player"):
                                blocked_teams.add(m_row["_Clean_Opp"])
                if blocked_teams:
                    candidate_df = candidate_df[~candidate_df["Clean_Team"].isin(blocked_teams)].copy()

            top_candidates = select_promo_legs(
                df=candidate_df,
                min_prob=st.session_state["mlb_auto_min_prob"],
                max_prob=st.session_state["mlb_auto_max_prob"],
                target_count=st.session_state["mlb_auto_legs_count"],
                max_per_team=st.session_state["mlb_auto_max_team"],
                team_col="Clean_Team",
                prob_col="Model_Over_Prob_%",
                score_col="Matchup_Proj",
                matchup_factor_col="Matchup_Factor",
            )

            if top_candidates.empty:
                st.warning("No players matched the current probability window. Try widening your Min/Max Prob % in the sidebar.")
            else:
                added_count = 0
                for _, item in top_candidates.iterrows():
                    if not any(
                        b["Player"] == item["Player"]
                        and b["Market"] == item["Market"]
                        and b["Line"] == item["Line"]
                        for b in st.session_state.mlb_bet_slip
                    ):
                        st.session_state.mlb_bet_slip.append({
                            "Include in Parlay": True,
                            "Sportsbook": "FanDuel",
                            "Player": item["Player"],
                            "Opponent": item["Opponent"],
                            "Market": item["Market"],
                            "Line": item["Line"],
                            "Nexus Odds (+/-)": None,
                            "Model Prob (%)": item["Model_Over_Prob_%"],
                            "Delete": False,
                        })
                        added_count += 1
                if added_count > 0:
                    st.rerun()
