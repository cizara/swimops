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


def main() -> None:
    st.set_page_config(page_title="SwimOps", page_icon="🏊", layout="wide")
    st.title("SwimOps")

    data_dir = Path(os.environ.get("GARMIN_DATA_DIR", "data")).expanduser()
    reports = SwimReports(data_dir / "garmin.sqlite")
    try:
        routines = reports.list_routines()
    except FileNotFoundError:
        st.error(f"No se encontró {data_dir / 'garmin.sqlite'}. Sincroniza Garmin primero.")
        return
    if not routines:
        st.info("Todavía no hay sesiones de piscina procesadas.")
        return

    first_date = date.fromisoformat(min(item["first_date"] for item in routines))
    last_date = date.fromisoformat(max(item["last_date"] for item in routines))
    labels = {item["name"]: item["key"] for item in routines}

    st.sidebar.header("Filtros")
    period = st.sidebar.date_input(
        "Fechas", value=(first_date, last_date), min_value=first_date, max_value=last_date
    )
    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Selecciona una fecha inicial y una final.")
        return
    selected_labels = st.sidebar.multiselect("Rutinas", list(labels))
    main_only = st.sidebar.checkbox("Sólo bloque principal", value=False)

    sessions = reports.sessions(
        period[0].isoformat(),
        period[1].isoformat(),
        [labels[label] for label in selected_labels],
        main_only,
    )
    if not sessions:
        st.warning("No hay sesiones para estos filtros.")
        return

    summary = summarize_sessions(sessions)
    metrics = st.columns(6)
    metrics[0].metric("Sesiones", summary["sessions"])
    metrics[1].metric("Distancia", f"{summary['distance_m']:,.0f} m")
    metrics[2].metric("Tiempo nadado", _duration(summary["swim_time_s"]))
    metrics[3].metric("Ritmo", _pace(summary["avg_pace_100m_s"]))
    metrics[4].metric(
        "SWOLF", f"{summary['avg_swolf']:.1f}" if summary["avg_swolf"] else "—"
    )
    metrics[5].metric(
        "Brazadas/largo",
        f"{summary['avg_strokes_per_length']:.1f}"
        if summary["avg_strokes_per_length"]
        else "—",
    )

    frame = pd.DataFrame(sessions)
    frame["date"] = pd.to_datetime(frame["date"])
    name_by_key = {item["key"]: item["name"] for item in routines}
    frame["Rutina"] = frame["routine"].map(name_by_key)

    st.subheader("Volumen semanal")
    weekly = (
        frame.set_index("date")["distance_m"]
        .resample("W-MON", label="left")
        .sum()
        .rename("Distancia (m)")
    )
    st.bar_chart(weekly)

    left, right = st.columns(2)
    with left:
        st.subheader("Ritmo por sesión")
        st.line_chart(frame, x="date", y="avg_pace_100m_s", color="Rutina")
    with right:
        st.subheader("Eficiencia")
        st.line_chart(
            frame,
            x="date",
            y=["avg_swolf", "avg_strokes_per_length"],
        )

    st.subheader("Sesiones")
    table = frame[
        [
            "date",
            "Rutina",
            "distance_m",
            "swim_time_s",
            "avg_pace_100m_s",
            "avg_swolf",
            "avg_strokes_per_length",
            "avg_hr",
        ]
    ].copy()
    table["date"] = table["date"].dt.date
    table["swim_time_s"] = table["swim_time_s"].map(_duration)
    table["avg_pace_100m_s"] = table["avg_pace_100m_s"].map(_pace)
    table.columns = [
        "Fecha",
        "Rutina",
        "Distancia (m)",
        "Tiempo",
        "Ritmo",
        "SWOLF",
        "Brazadas/largo",
        "FC media",
    ]
    st.dataframe(table, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
