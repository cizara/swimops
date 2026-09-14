from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from swimops.reports import SwimReports, summarize_sessions


def _duration(seconds: float) -> str:
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def _pace(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}/100 m"


def _sport_name(value: str) -> str:
    return {
        "lap_swimming": "Pool swimming",
        "open_water_swimming": "Open water swimming",
        "running": "Running",
        "soccer": "Soccer",
    }.get(value, value.replace("_", " ").title())


def _swim_metrics(summary: dict) -> None:
    metrics = st.columns(6)
    metrics[0].metric("Sessions", summary["sessions"])
    metrics[1].metric("Distance", f"{summary['distance_m']:,.0f} m")
    metrics[2].metric("Swim time", _duration(summary["swim_time_s"]))
    metrics[3].metric("Pace", _pace(summary["avg_pace_100m_s"]))
    metrics[4].metric(
        "SWOLF", f"{summary['avg_swolf']:.1f}" if summary["avg_swolf"] else "—"
    )
    metrics[5].metric(
        "Strokes/length",
        f"{summary['avg_strokes_per_length']:.1f}"
        if summary["avg_strokes_per_length"]
        else "—",
    )


def _sports_overview(frame: pd.DataFrame) -> None:
    st.subheader("Activity by sport")
    for sport, group in frame.groupby("sport", sort=False):
        columns = st.columns(3)
        columns[0].metric(_sport_name(sport), len(group))
        distance = group["distance_m"].sum(min_count=1)
        duration = group["duration_s"].sum(min_count=1)
        columns[1].metric(
            "Distance", f"{distance:,.0f} m" if pd.notna(distance) else "No data"
        )
        columns[2].metric(
            "Time", _duration(duration) if pd.notna(duration) else "No data"
        )

    volume = frame.dropna(subset=["distance_m"]).copy()
    if volume.empty:
        return
    volume["Sport"] = volume["sport"].map(_sport_name)
    weekly = (
        volume.groupby([pd.Grouper(key="date", freq="W-MON", label="left"), "Sport"])[
            "distance_m"
        ]
        .sum()
        .reset_index()
    )
    st.subheader("Weekly volume")
    st.bar_chart(weekly, x="date", y="distance_m", color="Sport")


def _comparison(frame: pd.DataFrame, sessions: list[dict], name_by_key: dict[str, str]) -> None:
    st.subheader("Workout comparison")
    rows = []
    for key, group in frame.groupby("routine"):
        summary = summarize_sessions(
            [session for session in sessions if session["routine"] == key]
        )
        rows.append(
            {
                "Workout": name_by_key[key],
                "Sessions": summary["sessions"],
                "Total distance (m)": round(summary["distance_m"]),
                "Pace": _pace(summary["avg_pace_100m_s"]),
                "SWOLF": round(summary["avg_swolf"], 1)
                if summary["avg_swolf"] is not None
                else None,
                "Strokes/length": round(summary["avg_strokes_per_length"], 1)
                if summary["avg_strokes_per_length"] is not None
                else None,
                "Average HR": round(summary["avg_hr"])
                if summary["avg_hr"] is not None
                else None,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    metrics = {
        "Pace (s/100 m)": "avg_pace_100m_s",
        "SWOLF": "avg_swolf",
        "Strokes per length": "avg_strokes_per_length",
        "Heart rate": "avg_hr",
        "Distance": "distance_m",
    }
    selected = st.selectbox("Metric", list(metrics))
    st.line_chart(frame, x="date", y=metrics[selected], color="Workout")


def _general(frame: pd.DataFrame) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Pace by session")
        st.line_chart(frame, x="date", y="avg_pace_100m_s", color="Workout")
    with right:
        st.subheader("Efficiency")
        st.line_chart(
            frame,
            x="date",
            y=["avg_swolf", "avg_strokes_per_length"],
        )


def main() -> None:
    st.set_page_config(page_title="SwimOps", page_icon="🏊", layout="wide")
    st.title("SwimOps")

    data_dir = Path(os.environ.get("GARMIN_DATA_DIR", "data")).expanduser()
    reports = SwimReports(data_dir / "garmin.sqlite")
    try:
        routines = reports.list_routines()
    except FileNotFoundError:
        st.error(f"{data_dir / 'garmin.sqlite'} was not found. Sync Garmin first.")
        return
    if not routines:
        st.info("There are no processed pool sessions yet.")
        return

    first_date = date.fromisoformat(min(item["first_date"] for item in routines))
    last_date = date.fromisoformat(max(item["last_date"] for item in routines))
    labels = {item["name"]: item["key"] for item in routines}

    st.sidebar.header("Filters")
    view = st.sidebar.radio("View", ["Overview", "Compare workouts"])
    period = st.sidebar.date_input(
        "Dates", value=(first_date, last_date), min_value=first_date, max_value=last_date
    )
    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Select a start and end date.")
        return
    defaults = list(labels)[:2] if view == "Compare workouts" else []
    selected_labels = st.sidebar.multiselect("Workouts", list(labels), default=defaults)
    if view == "Compare workouts" and not selected_labels:
        st.info("Select at least one workout to compare.")
        return
    main_only = st.sidebar.checkbox("Main set only", value=False)

    sessions = reports.sessions(
        period[0].isoformat(),
        period[1].isoformat(),
        [labels[label] for label in selected_labels],
        main_only,
    )
    if not sessions:
        st.warning("No sessions match these filters.")
        return

    summary = summarize_sessions(sessions)
    frame = pd.DataFrame(sessions)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.round(
        {
            "distance_m": 0,
            "avg_pace_100m_s": 0,
            "avg_swolf": 1,
            "avg_strokes_per_length": 1,
            "avg_hr": 0,
            "max_hr": 0,
        }
    )
    name_by_key = {item["key"]: item["name"] for item in routines}
    frame["Workout"] = frame["routine"].map(name_by_key)

    if view == "Compare workouts":
        _swim_metrics(summary)
        _comparison(frame, sessions, name_by_key)
    else:
        activities = pd.DataFrame(
            reports.activities(period[0].isoformat(), period[1].isoformat())
        )
        activities["date"] = pd.to_datetime(activities["date"])
        _sports_overview(activities)
        st.subheader("Pool swimming details")
        _swim_metrics(summary)
        _general(frame)

    st.subheader("Sessions")
    table = frame[
        [
            "date",
            "Workout",
            "distance_m",
            "swim_time_s",
            "avg_pace_100m_s",
            "avg_swolf",
            "avg_strokes_per_length",
            "avg_hr",
        ]
    ].copy()
    table["date"] = table["date"].dt.date
    table["distance_m"] = table["distance_m"].astype("Int64")
    table["avg_hr"] = table["avg_hr"].astype("Int64")
    table["swim_time_s"] = table["swim_time_s"].map(_duration)
    table["avg_pace_100m_s"] = table["avg_pace_100m_s"].map(_pace)
    table.columns = [
        "Date",
        "Workout",
        "Distance (m)",
        "Time",
        "Pace",
        "SWOLF",
        "Strokes/length",
        "Average HR",
    ]
    st.dataframe(table, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
