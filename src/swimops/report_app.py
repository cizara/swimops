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
        "lap_swimming": "Piscina",
        "open_water_swimming": "Aguas abiertas",
        "running": "Carrera",
        "soccer": "Fútbol",
    }.get(value, value.replace("_", " ").title())


def _swim_metrics(summary: dict) -> None:
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


def _sports_overview(frame: pd.DataFrame) -> None:
    st.subheader("Actividad por deporte")
    for sport, group in frame.groupby("sport", sort=False):
        columns = st.columns(3)
        columns[0].metric(_sport_name(sport), len(group))
        distance = group["distance_m"].sum(min_count=1)
        duration = group["duration_s"].sum(min_count=1)
        columns[1].metric(
            "Distancia", f"{distance:,.0f} m" if pd.notna(distance) else "Sin datos"
        )
        columns[2].metric(
            "Tiempo", _duration(duration) if pd.notna(duration) else "Sin datos"
        )

    volume = frame.dropna(subset=["distance_m"]).copy()
    if volume.empty:
        return
    volume["Deporte"] = volume["sport"].map(_sport_name)
    weekly = (
        volume.groupby([pd.Grouper(key="date", freq="W-MON", label="left"), "Deporte"])[
            "distance_m"
        ]
        .sum()
        .reset_index()
    )
    st.subheader("Volumen semanal")
    st.bar_chart(weekly, x="date", y="distance_m", color="Deporte")


def _comparison(frame: pd.DataFrame, sessions: list[dict], name_by_key: dict[str, str]) -> None:
    st.subheader("Comparación por rutina")
    rows = []
    for key, group in frame.groupby("routine"):
        summary = summarize_sessions(
            [session for session in sessions if session["routine"] == key]
        )
        rows.append(
            {
                "Rutina": name_by_key[key],
                "Sesiones": summary["sessions"],
                "Distancia total (m)": summary["distance_m"],
                "Ritmo": _pace(summary["avg_pace_100m_s"]),
                "SWOLF": summary["avg_swolf"],
                "Brazadas/largo": summary["avg_strokes_per_length"],
                "FC media": summary["avg_hr"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    metrics = {
        "Ritmo (s/100 m)": "avg_pace_100m_s",
        "SWOLF": "avg_swolf",
        "Brazadas por largo": "avg_strokes_per_length",
        "Frecuencia cardíaca": "avg_hr",
        "Distancia": "distance_m",
    }
    selected = st.selectbox("Métrica", list(metrics))
    st.line_chart(frame, x="date", y=metrics[selected], color="Rutina")


def _general(frame: pd.DataFrame) -> None:
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
    view = st.sidebar.radio("Vista", ["General", "Comparar rutinas"])
    period = st.sidebar.date_input(
        "Fechas", value=(first_date, last_date), min_value=first_date, max_value=last_date
    )
    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Selecciona una fecha inicial y una final.")
        return
    defaults = list(labels)[:2] if view == "Comparar rutinas" else []
    selected_labels = st.sidebar.multiselect("Rutinas", list(labels), default=defaults)
    if view == "Comparar rutinas" and not selected_labels:
        st.info("Selecciona al menos una rutina para comparar.")
        return
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
    frame = pd.DataFrame(sessions)
    frame["date"] = pd.to_datetime(frame["date"])
    name_by_key = {item["key"]: item["name"] for item in routines}
    frame["Rutina"] = frame["routine"].map(name_by_key)

    if view == "Comparar rutinas":
        _swim_metrics(summary)
        _comparison(frame, sessions, name_by_key)
    else:
        activities = pd.DataFrame(
            reports.activities(period[0].isoformat(), period[1].isoformat())
        )
        activities["date"] = pd.to_datetime(activities["date"])
        _sports_overview(activities)
        st.subheader("Detalle de natación en piscina")
        _swim_metrics(summary)
        _general(frame)

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
    st.dataframe(table, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
