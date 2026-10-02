"""Anomalías CMIP6 para el Meta: SSP1-2.6, SSP2-4.5, SSP5-8.5 vs Historical 1995-2014.

Lee los .nc de la carpeta de NetCDF (variable de entorno CMIP6_NC_DIR) (ruta sin tildes: netCDF4 no abre
rutas con tildes en Windows) y escribe tablas CSV y gráficos en .../resultados.
Método: promedio simple de las celdas del recuadro -> media anual por modelo ->
ventana de plazo menos línea base (1995-2014) del mismo modelo.
Temperatura: diferencia en °C. Precipitación: cambio relativo en %.
"""
import glob
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

PROY = Path(__file__).resolve().parents[1]
NC_DIR = Path(os.environ.get("CMIP6_NC_DIR", PROY / "datos" / "nc"))  # carpeta con los NetCDF (ruta sin tildes en Windows)
OUT = PROY / "resultados" / "tablas"
FIG = PROY / "resultados" / "figuras"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

BASE = (1995, 2014)
PLAZOS = {"Corto\n2021-2040": (2021, 2040), "Mediano\n2041-2060": (2041, 2060), "Largo\n2081-2100": (2081, 2100)}
ESCENARIOS = {"ssp1_2_6": "SSP1-2.6 (bajas)", "ssp2_4_5": "SSP2-4.5 (medias)", "ssp5_8_5": "SSP5-8.5 (altas)"}
VARS = {
    "near_surface_air_temperature": ("tas", "Temperatura", "Δ temperatura (°C)"),
    "precipitation": ("pr", "Precipitación", "Δ precipitación (%)"),
}

# Paleta de referencia (slots 1-3), fuentes y tintas del skill dataviz (modo claro)
COL = {"ssp1_2_6": "#2a78d6", "ssp2_4_5": "#eb6834", "ssp5_8_5": "#1baf7a", "historical": "#898781"}
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def serie_anual(path, v):
    da = xr.open_dataset(path)[v]
    da = da.mean(["lat", "lon"])
    if v == "pr":
        da = da * 86400  # kg m-2 s-1 -> mm/día
    else:
        da = da - 273.15
    s = da.groupby("time.year").mean().to_series()
    return s


# ---------- cargar ----------
series = {}  # (var, exp, modelo) -> Serie anual
for f in sorted(glob.glob(str(NC_DIR / "*.nc"))):
    m = re.match(r"(near_surface_air_temperature|precipitation)_(ssp\d_\d_\d|historical)_(.+)_(\d{4})-(\d{4})$",
                 os.path.basename(f)[:-3])
    var, exp, mod, _, _ = m.groups()
    series[(var, exp, mod)] = serie_anual(f, VARS[var][0])
modelos = sorted({k[2] for k in series})

# ---------- anomalías ----------
def anomalia(var, exp, mod, serie_exp=None):
    hist = series[(var, "historical", mod)]
    base = hist.loc[BASE[0]:BASE[1]].mean()
    s = series[(var, exp, mod)]
    if VARS[var][0] == "pr":
        return (s / base - 1) * 100, base
    return s - base, base


filas = []
for var in VARS:
    for exp in ESCENARIOS:
        for mod in modelos:
            an, base = anomalia(var, exp, mod)
            for plazo, (a, b) in PLAZOS.items():
                filas.append({"variable": VARS[var][1], "escenario": ESCENARIOS[exp], "exp": exp, "modelo": mod,
                              "plazo": plazo.replace("\n", " "), "plazo_key": plazo,
                              "linea_base_1995_2014": round(base, 3), "anomalia": round(an.loc[a:b].mean(), 3)})
df = pd.DataFrame(filas)
df.drop(columns=["exp", "plazo_key"]).to_csv(OUT / "anomalias_por_modelo.csv", index=False, encoding="utf-8-sig")

resumen = (df.groupby(["variable", "escenario", "plazo"])["anomalia"]
           .agg(media_ensamble="mean", minimo="min", maximo="max", desv_est="std").round(2).reset_index())
orden_p = {p.replace("\n", " "): i for i, p in enumerate(PLAZOS)}
resumen["o"] = resumen["plazo"].map(orden_p)
resumen = resumen.sort_values(["variable", "escenario", "o"]).drop(columns="o")
resumen.to_csv(OUT / "resumen_ensamble.csv", index=False, encoding="utf-8-sig")
print(resumen.to_string(index=False))

linea = df.drop_duplicates(["variable", "modelo"])[["variable", "modelo", "linea_base_1995_2014"]]
linea.to_csv(OUT / "linea_base_1995_2014.csv", index=False, encoding="utf-8-sig")
print("\nLínea base 1995-2014 (temp °C / precip mm/día):")
print(linea.pivot(index="modelo", columns="variable", values="linea_base_1995_2014").to_string())

# ---------- gráfico 1: barras por plazo y escenario ----------
def fmt(v, var):
    return f"{v:+.1f}" + ("%" if var == "precipitation" else "")

for var, (v, nombre, ylab) in VARS.items():
    fig, ax = plt.subplots(figsize=(10, 5.6))
    w = 0.24
    for gi, plazo in enumerate(PLAZOS):
        for si, exp in enumerate(ESCENARIOS):
            x = gi + (si - 1) * (w + 0.02)
            sub = df[(df.variable == nombre) & (df.exp == exp) & (df.plazo_key == plazo)]["anomalia"]
            ax.bar(x, sub.mean(), w, color=COL[exp], zorder=2, linewidth=0)
            ax.scatter([x] * len(sub), sub, s=26, color=SURF, edgecolor=INK2, linewidth=0.9, zorder=3)
            pos = sub.mean() >= 0
            ax.annotate(fmt(sub.mean(), var), (x, sub.mean()), xytext=(0, 4 if pos else -4),
                        textcoords="offset points", ha="center", va="bottom" if pos else "top",
                        fontsize=9, color=INK, fontweight="bold", zorder=5,
                        bbox=dict(boxstyle="round,pad=0.15", fc=SURF, ec="none", alpha=0.85))
    ax.axhline(0, color=AXIS, linewidth=1, zorder=1)
    ax.set_xticks(range(len(PLAZOS)), list(PLAZOS))
    ax.set_ylabel(ylab)
    ax.grid(axis="x", visible=False)
    ax.set_title(f"{nombre}: cambio respecto a 1995-2014, región del Meta", loc="left", fontsize=13, fontweight="bold")
    h = [plt.Rectangle((0, 0), 1, 1, color=COL[e]) for e in ESCENARIOS]
    h.append(plt.Line2D([], [], marker="o", ls="", markerfacecolor=SURF, markeredgecolor=INK2))
    ax.legend(h, list(ESCENARIOS.values()) + [f"Cada modelo (n={len(modelos)})"], frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=9, ncol=4)
    ax.set_title(f"{nombre}: cambio respecto a 1995-2014, región del Meta", loc="left", fontsize=13,
                 fontweight="bold", pad=34)
    fig.text(0.01, 0.01, "Barra = media del ensamble. Modelos: " + ", ".join(modelos), fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / f"anomalia_{v}_por_plazo.png", dpi=160)
    plt.close(fig)

# ---------- gráfico 2: series temporales (media móvil 10 años) ----------
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, (var, (v, nombre, ylab)) in zip(axes, VARS.items()):
    def suav(serie):
        return serie.rolling(10, center=True, min_periods=5).mean()
    # historical 1950-2014
    H = pd.DataFrame({m: suav(anomalia(var, "historical", m)[0]) for m in modelos}).loc[1950:2014]
    ax.fill_between(H.index, H.min(axis=1), H.max(axis=1), color=COL["historical"], alpha=0.18, linewidth=0)
    ax.plot(H.index, H.mean(axis=1), color=COL["historical"], linewidth=2, label="Historical")
    for exp in ESCENARIOS:
        S = pd.DataFrame({m: suav(anomalia(var, exp, m)[0]) for m in modelos})
        ax.fill_between(S.index, S.min(axis=1), S.max(axis=1), color=COL[exp], alpha=0.16, linewidth=0)
        ax.plot(S.index, S.mean(axis=1), color=COL[exp], linewidth=2, label=ESCENARIOS[exp])
    for a, b in PLAZOS.values():
        ax.axvspan(a, b, color=INK, alpha=0.04, linewidth=0)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_ylabel(ylab)
    ax.set_title(nombre, loc="left", fontsize=12, fontweight="bold")
    ax.grid(axis="x", visible=False)
axes[0].legend(frameon=False, fontsize=9, loc="upper left")
fig.suptitle("Meta: media del ensamble (línea) y rango entre modelos (banda), media móvil de 10 años, respecto a 1995-2014",
             x=0.01, ha="left", fontsize=12, fontweight="bold")
fig.text(0.01, 0.01, "Franjas grises = ventanas de corto, mediano y largo plazo.", fontsize=8, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 0.95))
fig.savefig(FIG / "series_temporales_ensamble.png", dpi=160)
plt.close(fig)
print("\nListo ->", OUT)
