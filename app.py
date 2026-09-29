"""
Bellabeat Fitbit Data Analysis — Streamlit App
Business task: how do consumers use their smart devices? (Bellabeat marketing case study)

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "fitbit_data.db"
WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ORANGE = "#F97316"
BLUE = "#2563EB"

st.set_page_config(page_title="Bellabeat Fitbit Analysis", layout="wide", page_icon="📊")


# --------------------------------------------------------------------------------------
# Data access helpers
# --------------------------------------------------------------------------------------
def get_conn():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_data(show_spinner=False)
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


@st.cache_data(show_spinner=False)
def list_tables() -> list[str]:
    df = run_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return df["name"].tolist()


@st.cache_data(show_spinner=False)
def load_daily() -> pd.DataFrame:
    df = run_query("SELECT * FROM daily_activity_clean")
    df["ActivityDate"] = pd.to_datetime(df["ActivityDate"])
    df["Weekday"] = df["ActivityDate"].dt.day_name()
    df["TotalActiveMinutes"] = (
        df["LightlyActiveMinutes"] + df["FairlyActiveMinutes"] + df["VeryActiveMinutes"]
    )
    return df


@st.cache_data(show_spinner=False)
def load_hourly_calories() -> pd.DataFrame:
    df = run_query("SELECT * FROM hourly_calories_clean")
    df["ActivityHour"] = pd.to_datetime(df["ActivityHour"])
    df["Hour"] = df["ActivityHour"].dt.hour
    return df


@st.cache_data(show_spinner=False)
def load_sleep() -> pd.DataFrame:
    df = run_query("SELECT * FROM sleep_day_clean")
    df["SleepDay"] = pd.to_datetime(df["SleepDay"])
    df["Weekday"] = df["SleepDay"].dt.day_name()
    df["HoursAsleep"] = df["TotalMinutesAsleep"] / 60
    return df


@st.cache_data(show_spinner=False)
def load_weight() -> pd.DataFrame:
    df = run_query("SELECT * FROM weight_log_info_clean")
    df["Date"] = pd.to_datetime(df["Date"])
    return df


# Safety guard for the free-form SQL box: read-only, single statement only.
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|CREATE|REPLACE|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


def is_safe_select(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return False  # no stacked statements
    if not stripped.upper().lstrip().startswith(("SELECT", "WITH")):
        return False
    if FORBIDDEN.search(stripped):
        return False
    return True


# --------------------------------------------------------------------------------------
# Sidebar navigation
# --------------------------------------------------------------------------------------
st.sidebar.title("📊 Bellabeat Fitbit Analysis")
page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "SQL Analysis",
        "Activity & Steps",
        "Sedentary Patterns",
        "Calories",
        "Sleep",
        "Participant Explorer",
        "Recommendations",
    ],
)
st.sidebar.markdown("---")
st.sidebar.caption(
    "Data: 33 Fitbit users, Fitabase export (Apr–May 2016), sourced via Amazon Mechanical Turk, "
    "distributed on Kaggle under CC0. Cleaned in SQLite (see *SQL Analysis* tab)."
)

if not DB_PATH.exists():
    st.error(f"Database not found at {DB_PATH}. Place fitbit_data.db next to app.py.")
    st.stop()

daily = load_daily()

# --------------------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------------------
if page == "Overview":
    st.title("Bellabeat: How Do Consumers Use Their Smart Devices?")
    st.markdown(
        """
Bellabeat is a high-tech wellness company for women. This app analyzes public Fitbit
fitness-tracker data as a proxy for smart-device usage patterns, to surface insights that
could inform Bellabeat's marketing strategy.

**Deliverables covered in this app:** business task summary · data sources · cleaning
documentation (SQL) · analysis & visualizations · key findings · recommendations.
        """
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Participants", f'{daily["Id"].nunique()}')
    c2.metric("Avg. Steps / Day", f'{daily["TotalSteps"].mean():,.0f}')
    c3.metric("Avg. Calories / Day", f'{daily["Calories"].mean():,.0f}')
    c4.metric(
        "% Days ≥ 10,000 Steps",
        f'{(daily["TotalSteps"] >= 10000).mean() * 100:.1f}%',
    )

    st.subheader("Dataset")
    tables = list_tables()
    meta_rows = []
    for t in tables:
        if t.endswith("_clean"):
            cnt = run_query(f"SELECT COUNT(*) AS n FROM {t}").iloc[0]["n"]
            meta_rows.append({"table": t, "rows": cnt})
    meta_df = pd.DataFrame(meta_rows).sort_values("rows", ascending=False)
    st.dataframe(meta_df, use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------------------
# SQL Analysis
# --------------------------------------------------------------------------------------
elif page == "SQL Analysis":
    st.title("SQL Analysis")
    st.markdown("Data-cleaning and integrity checks performed in SQL, runnable live below.")

    presets = {
        "Min/max sanity check (steps, distance, calories)": """
SELECT
    MIN(TotalDistance) AS min_dist, MAX(TotalDistance) AS max_dist,
    MIN(TotalSteps)    AS min_steps, MAX(TotalSteps)    AS max_steps,
    MIN(Calories)      AS min_cal,   MAX(Calories)       AS max_cal
FROM daily_activity_clean;
""".strip(),
        "Negative-value check": """
SELECT COUNT(*) AS negative_rows
FROM daily_activity_clean
WHERE TotalSteps < 0 OR TotalDistance < 0 OR Calories < 0 OR SedentaryMinutes < 0;
""".strip(),
        "Full-day sedentary readings (>= 1440 min) by participant": """
SELECT Id, COUNT(*) AS full_sedentary_days
FROM daily_activity_clean
WHERE SedentaryMinutes >= 1440
GROUP BY Id
ORDER BY full_sedentary_days DESC;
""".strip(),
        "Avg. steps by weekday": """
SELECT
    strftime('%w', ActivityDate) AS dow,
    ROUND(AVG(TotalSteps), 0) AS avg_steps
FROM daily_activity_clean
GROUP BY dow
ORDER BY dow;
""".strip(),
        "Participants below CDC sleep guideline (7 hrs)": """
SELECT Id,
       ROUND(AVG(TotalMinutesAsleep) / 60.0, 2) AS avg_hours_asleep
FROM sleep_day_clean
GROUP BY Id
HAVING avg_hours_asleep < 7
ORDER BY avg_hours_asleep;
""".strip(),
        "Business Q1: Sleep vs. activity (daily_summary join)": """
WITH daily_summary AS (
    SELECT da.Id, date(da.ActivityDate) AS ActivityDate,
           da.TotalSteps, da.SedentaryMinutes, da.VeryActiveMinutes, da.Calories,
           sd.TotalMinutesAsleep, wl.WeightKg
    FROM daily_activity_clean da
    LEFT JOIN sleep_day_clean sd
           ON da.Id = sd.Id AND date(da.ActivityDate) = date(sd.SleepDay)
    LEFT JOIN weight_log_info_clean wl
           ON da.Id = wl.Id AND date(da.ActivityDate) = date(wl.Date)
)
SELECT
    CASE WHEN TotalMinutesAsleep IS NULL THEN 'No sleep data'
         WHEN TotalMinutesAsleep < 420 THEN 'Under 7 hrs sleep'
         ELSE '7+ hrs sleep' END AS sleep_group,
    ROUND(AVG(TotalSteps), 0) AS avg_steps,
    ROUND(AVG(Calories), 0) AS avg_calories,
    ROUND(AVG(SedentaryMinutes), 0) AS avg_sedentary_min,
    COUNT(*) AS days
FROM daily_summary
GROUP BY sleep_group;
""".strip(),
        "Business Q2: Sedentary + sleep check (unrecorded-sleep effect)": """
WITH daily_summary AS (
    SELECT da.Id, date(da.ActivityDate) AS ActivityDate,
           da.TotalSteps, da.SedentaryMinutes, da.VeryActiveMinutes, da.Calories,
           sd.TotalMinutesAsleep, wl.WeightKg
    FROM daily_activity_clean da
    LEFT JOIN sleep_day_clean sd
           ON da.Id = sd.Id AND date(da.ActivityDate) = date(sd.SleepDay)
    LEFT JOIN weight_log_info_clean wl
           ON da.Id = wl.Id AND date(da.ActivityDate) = date(wl.Date)
)
SELECT
    CASE WHEN TotalMinutesAsleep IS NULL THEN 'No sleep data'
         WHEN TotalMinutesAsleep < 420 THEN 'Under 7 hrs sleep'
         ELSE '7+ hrs sleep' END AS sleep_group,
    ROUND(AVG(SedentaryMinutes), 0) AS avg_sedentary_min,
    ROUND(AVG(TotalMinutesAsleep), 0) AS avg_asleep_min,
    ROUND(AVG(SedentaryMinutes + COALESCE(TotalMinutesAsleep, 0)), 0) AS sedentary_plus_sleep
FROM daily_summary
GROUP BY sleep_group;
""".strip(),
        "Business Q3: Who logs weight?": """
WITH daily_summary AS (
    SELECT da.Id, date(da.ActivityDate) AS ActivityDate,
           da.TotalSteps, da.SedentaryMinutes, da.VeryActiveMinutes, da.Calories,
           sd.TotalMinutesAsleep, wl.WeightKg
    FROM daily_activity_clean da
    LEFT JOIN sleep_day_clean sd
           ON da.Id = sd.Id AND date(da.ActivityDate) = date(sd.SleepDay)
    LEFT JOIN weight_log_info_clean wl
           ON da.Id = wl.Id AND date(da.ActivityDate) = date(wl.Date)
)
SELECT
    COUNT(DISTINCT Id) AS total_participants,
    COUNT(DISTINCT CASE WHEN WeightKg IS NOT NULL THEN Id END) AS participants_with_weight_data,
    ROUND(COUNT(DISTINCT CASE WHEN WeightKg IS NOT NULL THEN Id END) * 100.0
          / COUNT(DISTINCT Id), 1) AS pct_tracking_weight
FROM daily_summary;
""".strip(),
        "Business Q4: Step brackets vs. calories & intensity": """
WITH daily_summary AS (
    SELECT da.Id, date(da.ActivityDate) AS ActivityDate,
           da.TotalSteps, da.SedentaryMinutes, da.VeryActiveMinutes, da.Calories,
           sd.TotalMinutesAsleep, wl.WeightKg
    FROM daily_activity_clean da
    LEFT JOIN sleep_day_clean sd
           ON da.Id = sd.Id AND date(da.ActivityDate) = date(sd.SleepDay)
    LEFT JOIN weight_log_info_clean wl
           ON da.Id = wl.Id AND date(da.ActivityDate) = date(wl.Date)
)
SELECT
    CASE WHEN TotalSteps < 5000 THEN 'Under 5,000 steps'
         WHEN TotalSteps < 10000 THEN '5,000-9,999 steps'
         ELSE '10,000+ steps' END AS step_bracket,
    ROUND(AVG(Calories), 0) AS avg_calories,
    ROUND(AVG(VeryActiveMinutes), 1) AS avg_very_active_min,
    COUNT(*) AS days
FROM daily_summary
GROUP BY step_bracket
ORDER BY MIN(TotalSteps);
""".strip(),
        "Duplicate rows removed during cleaning (minute_sleep)": """
SELECT Id, date, value, logId, COUNT(*) AS occurrences
FROM minute_sleep
GROUP BY Id, date, value, logId
HAVING COUNT(*) > 1;
""".strip(),
    }

    choice = st.selectbox("Preset query", list(presets.keys()))
    sql_text = st.text_area("SQL (editable)", value=presets[choice], height=160)

    if st.button("Run query", type="primary"):
        if not is_safe_select(sql_text):
            st.error(
                "Only a single read-only SELECT statement is allowed here "
                "(no INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA, no stacked statements)."
            )
        else:
            try:
                result = run_query(sql_text)
                st.success(f"{len(result):,} rows returned")
                st.dataframe(result, use_container_width=True)
                if result.shape[1] == 2 and pd.api.types.is_numeric_dtype(result.iloc[:, 1]):
                    st.bar_chart(result.set_index(result.columns[0]))
            except Exception as e:
                st.error(f"Query failed: {e}")

    st.markdown("---")
    st.subheader("Custom query")
    st.caption("Explore any of the 18 `*_clean` tables directly. Read-only SELECT statements only.")
    custom_sql = st.text_area(
        "Your SQL",
        value="SELECT * FROM daily_activity_clean LIMIT 20;",
        height=100,
        key="custom_sql",
    )
    if st.button("Run custom query"):
        if not is_safe_select(custom_sql):
            st.error("Only a single read-only SELECT statement is allowed.")
        else:
            try:
                result = run_query(custom_sql)
                st.dataframe(result, use_container_width=True)
            except Exception as e:
                st.error(f"Query failed: {e}")

# --------------------------------------------------------------------------------------
# Activity & Steps
# --------------------------------------------------------------------------------------
elif page == "Activity & Steps":
    st.title("Activity & Steps")

    steps_wd = (
        daily.groupby("Weekday")["TotalSteps"].mean().reindex(WEEKDAY_ORDER).reset_index()
    )
    fig = px.bar(
        steps_wd, x="TotalSteps", y="Weekday", orientation="h",
        color="TotalSteps", color_continuous_scale="Blues",
        title="Average Steps Taken Through Weekdays",
        labels={"TotalSteps": "Avg. Total Steps"},
    )
    fig.add_vline(x=10000, line_dash="dash", line_color="red",
                   annotation_text="CDC 10,000-step goal")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Steps by participant, by weekday")
    pivot = daily.pivot_table(index="Id", columns="Weekday", values="TotalSteps", aggfunc="mean")
    pivot = pivot.reindex(columns=WEEKDAY_ORDER)
    pivot["Avg"] = pivot.mean(axis=1)
    pivot = pivot.sort_values("Avg", ascending=False).drop(columns="Avg")
    fig2 = px.imshow(
        pivot, color_continuous_scale="RdYlBu_r", aspect="auto",
        labels=dict(color="Avg. Steps"),
    )
    fig2.update_yaxes(type="category", title="Participant Id")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Activity category breakdown")
    cat_wd = (
        daily.groupby("Weekday")[["LightlyActiveMinutes", "FairlyActiveMinutes", "VeryActiveMinutes"]]
        .mean()
        .reindex(WEEKDAY_ORDER)
        .reset_index()
        .melt(id_vars="Weekday", var_name="Category", value_name="Minutes")
    )
    fig3 = px.bar(
        cat_wd, x="Weekday", y="Minutes", color="Category", barmode="group",
        title="Time Spent in Activity Categories by Weekday",
        category_orders={"Weekday": WEEKDAY_ORDER},
    )
    st.plotly_chart(fig3, use_container_width=True)

    pct_goal = (daily["TotalSteps"] >= 10000).mean() * 100
    st.info(f"Only **{pct_goal:.1f}%** of all participant-days reach the CDC's 10,000-step goal.")

# --------------------------------------------------------------------------------------
# Sedentary Patterns
# --------------------------------------------------------------------------------------
elif page == "Sedentary Patterns":
    st.title("Sedentary Patterns")

    pivot_sed = daily.pivot_table(index="Id", columns="Weekday", values="SedentaryMinutes", aggfunc="mean")
    pivot_sed = pivot_sed.reindex(columns=WEEKDAY_ORDER)
    pivot_sed["Avg"] = pivot_sed.mean(axis=1)
    pivot_sed = pivot_sed.sort_values("Avg", ascending=False).drop(columns="Avg")
    fig = px.imshow(
        pivot_sed, color_continuous_scale="RdBu_r", aspect="auto",
        labels=dict(color="Avg. Sedentary Minutes"),
    )
    fig.update_yaxes(type="category", title="Participant Id")
    fig.update_layout(title="Avg. Sedentary Minutes by Participant, by Weekday")
    st.plotly_chart(fig, use_container_width=True)

    full_day = daily[daily["SedentaryMinutes"] >= 1440].groupby("Id").size().reset_index(name="Full-day sedentary readings")
    full_day = full_day.sort_values("Full-day sedentary readings", ascending=False)
    pct_full_day = (daily["SedentaryMinutes"] >= 1440).mean() * 100

    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Days with a full 24h sedentary reading", f"{pct_full_day:.1f}%",
                   help="Likely indicates the tracker wasn't worn / actively used that day.")
        st.dataframe(full_day, use_container_width=True, hide_index=True)
    with col2:
        st.metric("Avg. sedentary minutes / day (all users)", f'{daily["SedentaryMinutes"].mean():.0f}')
        frac_high = (pivot_sed.mean(axis=1) > 1150).mean() * 100
        st.metric("Participants averaging > 1,150 sedentary min/day", f"{frac_high:.0f}%")
        st.caption(
            "Note: raw sedentary minutes likely include nights with no recorded sleep. "
            "Days without sleep data average ~1,207 sedentary min vs ~656-783 on days with it."
        )

# --------------------------------------------------------------------------------------
# Calories
# --------------------------------------------------------------------------------------
elif page == "Calories":
    st.title("Calories")

    cal_wd = daily.groupby("Weekday")[["TotalActiveMinutes", "Calories"]].mean().reindex(WEEKDAY_ORDER).reset_index()
    fig = go.Figure()
    fig.add_bar(x=cal_wd["Weekday"], y=cal_wd["TotalActiveMinutes"], name="Avg. Total Active Minutes", marker_color=BLUE)
    fig.add_trace(go.Scatter(x=cal_wd["Weekday"], y=cal_wd["Calories"], name="Avg. Calories",
                              yaxis="y2", mode="lines+markers", line=dict(color=ORANGE, width=3)))
    fig.update_layout(
        title="Avg. Calories Burnt vs. Active Minutes, by Weekday",
        yaxis=dict(title="Avg. Total Active Minutes"),
        yaxis2=dict(title="Avg. Calories", overlaying="y", side="right"),
    )
    st.plotly_chart(fig, use_container_width=True)

    hourly_cal = load_hourly_calories()
    cal_hr = hourly_cal.groupby("Hour")["Calories"].mean().reset_index()
    fig2 = px.bar(cal_hr, x="Hour", y="Calories", title="Average Calories Burnt Each Hour")
    fig2.update_xaxes(dtick=1)
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Steps vs. Calories")
    corr = daily["TotalSteps"].corr(daily["Calories"])
    fig3 = px.scatter(
        daily, x="TotalSteps", y="Calories", trendline="ols",
        opacity=0.4, title=f"Steps vs. Calories Burnt (r = {corr:.2f})",
    )
    st.plotly_chart(fig3, use_container_width=True)

# --------------------------------------------------------------------------------------
# Sleep
# --------------------------------------------------------------------------------------
elif page == "Sleep":
    st.title("Sleep")
    sleep = load_sleep()

    sleep_wd = sleep.groupby("Weekday")["HoursAsleep"].mean().reindex(WEEKDAY_ORDER).reset_index()
    fig = px.bar(sleep_wd, x="Weekday", y="HoursAsleep", title="Avg. Sleep Duration by Weekday",
                 color_discrete_sequence=["#6D28D9"])
    fig.add_hline(y=8, line_dash="dash", line_color="red", annotation_text="CDC 8-hour guideline")
    fig.add_hline(y=7, line_dash="dash", line_color="orange", annotation_text="CDC min. 7-hour guideline")
    st.plotly_chart(fig, use_container_width=True)

    avg_sleep = sleep["HoursAsleep"].mean()
    st.warning(
        f"Average sleep across all users is **{avg_sleep:.2f} hours/day** — "
        "below the CDC's recommended 7–9 hour range on every day of the week."
    )

    below7 = sleep.groupby("Id")["HoursAsleep"].mean()
    below7 = below7[below7 < 7].sort_values()
    st.subheader(f"Participants averaging < 7 hours sleep ({len(below7)} of {sleep['Id'].nunique()})")
    st.dataframe(below7.reset_index().rename(columns={"HoursAsleep": "Avg. Hours Asleep"}),
                 use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------------------
# Participant Explorer
# --------------------------------------------------------------------------------------
elif page == "Participant Explorer":
    st.title("Participant Explorer")

    ids = sorted(daily["Id"].unique())
    pid = st.selectbox("Select participant Id", ids)

    p_daily = daily[daily["Id"] == pid].sort_values("ActivityDate")
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg. Steps/Day", f'{p_daily["TotalSteps"].mean():,.0f}')
    c2.metric("Avg. Calories/Day", f'{p_daily["Calories"].mean():,.0f}')
    c3.metric("Avg. Sedentary Min/Day", f'{p_daily["SedentaryMinutes"].mean():,.0f}')

    fig = px.line(p_daily, x="ActivityDate", y="TotalSteps", title=f"Daily Steps — Participant {pid}", markers=True)
    fig.add_hline(y=10000, line_dash="dash", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

    sleep = load_sleep()
    p_sleep = sleep[sleep["Id"] == pid].sort_values("SleepDay")
    if len(p_sleep):
        fig2 = px.line(p_sleep, x="SleepDay", y="HoursAsleep", title=f"Sleep — Participant {pid}", markers=True)
        fig2.add_hline(y=8, line_dash="dash", line_color="red")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("No sleep data logged for this participant.")

    if st.checkbox("Load minute-level heart rate (slower — large table)"):
        if "heartrate_seconds_clean" not in list_tables():
            st.caption(
                "Heart-rate data isn't included in this deployment (the full table is ~2.5M rows). "
                "Run the app locally with the full fitbit_data.db to see it."
            )
        else:
            hr = run_query(
                "SELECT Time, Value FROM heartrate_seconds_clean WHERE Id = ? ORDER BY Time LIMIT 20000",
                params=(int(pid),),
            )
            if len(hr):
                hr["Time"] = pd.to_datetime(hr["Time"])
                fig3 = px.line(hr, x="Time", y="Value", title=f"Heart Rate (first 20k readings) — Participant {pid}")
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.caption("No heart-rate data logged for this participant.")

# --------------------------------------------------------------------------------------
# Recommendations
# --------------------------------------------------------------------------------------
elif page == "Recommendations":
    st.title("Summary & Recommendations")
    st.markdown(
        """
### Key findings
- Average daily steps (**~7,600**) fall short of the CDC's 10,000-step benchmark; only **~32%** of
  participant-days meet it.
- Movement is dominated by low-intensity ("lightly active") minutes — very little logged
  moderate/vigorous activity.
- Raw sedentary minutes look very high for a third of users, but much of that is likely unrecorded
  sleep (days without sleep data average ~1,207 sedentary min vs ~656-783 with it). Separately,
  **8.4%** of all days show a full 24-hour sedentary reading, suggesting the tracker wasn't worn.
- Only ~44% of participant-days have sleep data, and just 8 of 33 users ever logged weight.
- Sleep consistently falls short of guidelines — average **6.99 hours/day**, never reaching 8 hours
  on any day of the week.
- Steps and calories are only moderately correlated (**r ≈ 0.59**) — intensity/activity type matters
  as much as raw step count.
- SQL step-bracket analysis: very active minutes rise from **2.3** (under 5,000 steps) to **13.4**
  (5,000–9,999) to **48.5** (10,000+); calories rise from 1,807 to 2,355 to 2,744.
- Days with under 7 hours of sleep did **not** show lower activity (9,363 vs 7,845 steps), so this
  data can't support a sleep-drives-activity claim; the groups are different people and sleep is
  logged on only ~44% of days.

### Recommendations for Bellabeat
1. **Encourage consistent tracker wear** — full-day-sedentary readings suggest some users aren't
   wearing the device throughout the day; wear-detection nudges could improve engagement and data quality.
2. **Push activity reminders during low-movement windows** — especially midweek and
   overnight/early-morning hours where intensity is lowest.
3. **Make overnight wear and sleep tracking easier** — sleep is missing on ~56% of days; bedtime
   wear reminders and simpler sleep setup would close the biggest data gap. Among users who do log
   sleep, the average (6.99 h) is below the 7-hour minimum, so sleep-coaching content fits too.
4. **Reframe goals beyond step count** — surface intensity/active-minutes goals alongside step
   count, and use progressive targets that move under-5,000-step users into the middle bracket first.
5. **Treat weight tracking as an engagement problem** — only 8 of 33 users (24.2%) ever logged
   weight; smart-scale sync or automatic logging is a better bet than manual-entry features.
        """
    )
