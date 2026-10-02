"""Gráficas PNG adicionales para el informe (CMIP6, Meta). Salida: resultados/figuras.

Complementa analisis_anomalias.py (que genera las tres primeras figuras). Misma
metodología: promedio de las celdas del recuadro, anomalía contra Historical 1995-2014
del mismo modelo (°C para temperatura, % para precipitación).
"""
import glob
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

PROY = Path(__file__).resolve().parents[1]
NC_DIR = Path(os.environ.get("CMIP6_NC_DIR", PROY / "datos" / "nc"))  # carpeta con los NetCDF (ruta sin tildes en Windows)
FIG = PROY / "resultados" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)

BASE = (1995, 2014)
PLAZOS = [("Corto", 2021, 2040), ("Mediano", 2041, 2060), ("Largo", 2081, 2100)]
ESC = [("ssp1_2_6", "SSP1-2.6 (bajas)", "#2a78d6"), ("ssp2_4_5", "SSP2-4.5 (medias)", "#eb6834"),
       ("ssp5_8_5", "SSP5-8.5 (altas)", "#1baf7a")]
HIST_COL = "#898781"
MOD = {"access_cm2": "ACCESS-CM2", "gfdl_esm4": "GFDL-ESM4", "mpi_esm1_2_lr": "MPI-ESM1-2-LR",
       "mri_esm2_0": "MRI-ESM2-0", "noresm2_mm": "NorESM2-MM"}
MIDS = list(MOD)
MCOL = dict(zip(MIDS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))  # slots 1-5, orden fijo
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
AREA = dict(N=5.0, S=2.0, W=-74.5, E=-71.0)

SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})

# ---------------- datos ----------------
mensual, malla = {}, {}
for f in sorted(glob.glob(str(NC_DIR / "*.nc"))):
    m = re.match(r"(near_surface_air_temperature|precipitation)_(ssp\d_\d_\d|historical)_(.+)_(\d{4})-(\d{4})$",
                 os.path.basename(f)[:-3])
    var, exp, mod, _, _ = m.groups()
    v = "tas" if var.startswith("near") else "pr"
    ds = xr.open_dataset(f)
    da = ds[v].mean(["lat", "lon"])
    da = da * 86400 if v == "pr" else da - 273.15
    mensual[(v, exp, mod)] = pd.Series(da.values, index=pd.MultiIndex.from_arrays(
        [da.time.dt.year.values, da.time.dt.month.values]))
    if v == "tas" and exp == "historical":
        lon = ((ds.lon.values + 180) % 360) - 180
        malla[mod] = (ds.lat.values, lon)
anual = {k: s.groupby(level=0).mean() for k, s in mensual.items()}
base = {(v, m): anual[(v, "historical", m)].loc[BASE[0]:BASE[1]].mean() for v in ("tas", "pr") for m in MIDS}


def anom(v, s, m):
    return (s / base[(v, m)] - 1) * 100 if v == "pr" else s - base[(v, m)]


def suav(s):
    return s.rolling(10, center=True, min_periods=5).mean()


def clim(v, exp, m, a, b):
    return mensual[(v, exp, m)].loc[a:b].groupby(level=1).mean()


def guardar(fig, nombre):
    fig.savefig(FIG / nombre, dpi=160)
    plt.close(fig)
    print("OK", nombre)


def titulo(fig, t, sub=None):
    fig.suptitle(t, x=0.01, ha="left", fontsize=13, fontweight="bold")
    if sub:
        fig.text(0.01, 0.01, sub, fontsize=8, color=MUTED)


# ============ 1. Malla de cada modelo en el recuadro ============
fig, axes = plt.subplots(1, 5, figsize=(16, 4.6), sharey=True)
for ax, m in zip(axes, MIDS):
    lat, lon = malla[m]
    ax.add_patch(Rectangle((AREA["W"], AREA["S"]), AREA["E"] - AREA["W"], AREA["N"] - AREA["S"],
                           fill=False, ec=INK2, lw=1.2, ls="--"))
    LL, LA = np.meshgrid(lon, lat)
    ax.scatter(LL, LA, s=70, color=MCOL[m], edgecolor=SURF, linewidth=1.5, zorder=3)
    ax.scatter([-73.63], [4.14], marker="*", s=110, color=INK, zorder=4)
    ax.annotate("Villavicencio", (-73.63, 4.14), xytext=(4, 6), textcoords="offset points", fontsize=7, color=INK2)
    ax.set_xlim(-75.3, -70.4)
    ax.set_ylim(1.4, 5.6)
    ax.set_title(f"{MOD[m]}\n{len(lat)} x {len(lon)} = {len(lat) * len(lon)} celdas", fontsize=10, loc="left")
    ax.set_xlabel("Longitud (°)")
axes[0].set_ylabel("Latitud (°)")
titulo(fig, "Celdas de cada modelo dentro del recuadro del Meta (línea punteada)",
       "Cada punto es el centro de una celda del modelo (los modelos son de ~100 a ~200 km). Solo entran celdas con centro dentro del recuadro N 5, S 2, O -74,5, E -71.")
fig.tight_layout(rect=(0, 0.04, 1, 0.92))
guardar(fig, "malla_modelos_recuadro.png")

# ============ 2. Mapas de calor: acuerdo entre modelos ============
div = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
seq = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#2a78d6", "#0d366b"])
filas = [(k, n, pn, a, b) for k, n, _ in ESC for pn, a, b in PLAZOS]
for v, nombre, unidad, cmap, fmtv in (("tas", "temperatura", "°C", seq, "{:+.1f}"), ("pr", "precipitación", "%", div, "{:+.0f}")):
    M = np.array([[float(anom(v, anual[(v, k, m)], m).loc[a:b].mean()) for m in MIDS] for k, _, _, a, b in filas])
    M = np.column_stack([M, M.mean(axis=1)])
    fig, ax = plt.subplots(figsize=(10, 6.2))
    if v == "pr":
        lim = np.abs(M).max()
        im = ax.imshow(M, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    else:
        im = ax.imshow(M, cmap=cmap, aspect="auto", vmin=0)
    ax.set_xticks(range(6), [MOD[m] for m in MIDS] + ["Media ensamble"], rotation=20, ha="right")
    ax.set_yticks(range(len(filas)), [f"{n.split(' ')[0]} · {pn} {a}-{b}" for _, n, pn, a, b in filas])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            c = "#ffffff" if (v == "tas" and M[i, j] > 2.2) else INK
            txt = fmtv.format(M[i, j])
            if float(txt) == 0:
                txt = "0"  # evita "-0" / "+0"
            ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=c,
                    fontweight="bold" if j == 5 else "normal")
    for y in (2.5, 5.5):
        ax.axhline(y, color=SURF, lw=4)
    ax.axvline(4.5, color=SURF, lw=4)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(f"Δ {nombre} ({unidad})", color=INK2)
    titulo(fig, f"Cambio de {nombre} por modelo, escenario y plazo (respecto a 1995-2014)",
           "Si los colores de una fila coinciden entre modelos, hay acuerdo; si cambian de signo (solo en precipitación), hay desacuerdo.")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    guardar(fig, f"mapa_calor_{v}_modelos.png")

# ============ 3. Trayectorias por modelo (3 escenarios) ============
for v, nombre, ylab in (("tas", "temperatura", "Δ temperatura (°C)"), ("pr", "precipitación", "Δ precipitación (%)")):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (k, n, c) in zip(axes, ESC):
        for m in MIDS:
            h = suav(anom(v, anual[(v, "historical", m)], m)).loc[1980:2014]
            s = suav(anom(v, anual[(v, k, m)], m))
            ax.plot(np.r_[h.index, s.index], np.r_[h.values, s.values], color=MCOL[m], lw=1.3, alpha=0.9, label=MOD[m])
        ens = pd.concat([suav(anom(v, anual[(v, k, m)], m)) for m in MIDS], axis=1).mean(axis=1)
        ax.plot(ens.index, ens.values, color=INK, lw=2.6, label="Media ensamble")
        ax.axvline(2014.5, color=AXIS, lw=1)
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_title(n, loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel(ylab)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    titulo(fig, f"Trayectoria de {nombre} por modelo (media móvil de 10 años, 1980-2100)",
           "Línea vertical = 2014/2015 (fin de Historical, inicio de los escenarios). Línea negra = media del ensamble.")
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    guardar(fig, f"trayectorias_modelos_{v}.png")

# ============ 4. Series con banda (una figura por variable) ============
for v, nombre, ylab in (("tas", "temperatura", "Δ temperatura (°C)"), ("pr", "precipitación", "Δ precipitación (%)")):
    fig, ax = plt.subplots(figsize=(11, 5.6))
    H = pd.DataFrame({m: suav(anom(v, anual[(v, "historical", m)], m)) for m in MIDS}).loc[1950:2014]
    ax.fill_between(H.index, H.min(axis=1), H.max(axis=1), color=HIST_COL, alpha=0.18, lw=0)
    ax.plot(H.index, H.mean(axis=1), color=HIST_COL, lw=2.2)
    ax.text(1950, H.mean(axis=1).iloc[0], "Historical ", ha="right", va="center", fontsize=9, color=INK2)
    finales = []
    for k, n, c in ESC:
        S = pd.DataFrame({m: suav(anom(v, anual[(v, k, m)], m)) for m in MIDS})
        ax.fill_between(S.index, S.min(axis=1), S.max(axis=1), color=c, alpha=0.16, lw=0)
        ax.plot(S.index, S.mean(axis=1), color=c, lw=2.2, label=n)
        finales.append([float(S.mean(axis=1).iloc[-1]), n.split(" ")[0]])
    # etiquetas finales sin solaparse: separación mínima del 5 % del rango del eje
    ymin, ymax = ax.get_ylim()
    sep = 0.05 * (ymax - ymin)
    finales.sort()
    pos = [f[0] for f in finales]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + sep)
    for (val, txt), y in zip(finales, pos):
        ax.text(2101, y, txt, va="center", fontsize=9, color=INK2)
    for (pn, a, b) in PLAZOS:
        ax.axvspan(a, b, color=INK, alpha=0.045, lw=0)
        ax.text((a + b) / 2, 1.0, pn, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=8, color=MUTED)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlim(1945, 2112)
    ax.set_ylabel(ylab)
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 0.93))
    titulo(fig, f"Meta: {nombre}, media del ensamble y rango entre modelos (respecto a 1995-2014)",
           "Línea = media de los 5 modelos; banda = mínimo-máximo entre modelos; media móvil de 10 años; franjas = ventanas de corto, mediano y largo plazo.")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    guardar(fig, f"serie_{v}_ensamble.png")

# ============ 5. Ciclo estacional de la línea base ============
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
for ax, v, ylab in ((axes[0], "tas", "Temperatura (°C)"), (axes[1], "pr", "Precipitación (mm/día)")):
    C = pd.DataFrame({m: clim(v, "historical", m, *BASE) for m in MIDS})
    for m in MIDS:
        ax.plot(range(12), C[m].values, color=MCOL[m], lw=1.4, label=MOD[m])
    ax.plot(range(12), C.mean(axis=1).values, color=INK, lw=2.8, label="Media ensamble")
    ax.set_xticks(range(12), MES)
    ax.set_ylabel(ylab)
    ax.grid(axis="x", visible=False)
axes[1].axvspan(2.5, 10.5, color=INK, alpha=0.04, lw=0)
axes[1].text(6.5, 1.0, "estación lluviosa (abr-nov)", transform=axes[1].get_xaxis_transform(), ha="center", va="top", fontsize=8, color=MUTED)
axes[0].legend(frameon=False, fontsize=8, loc="lower left")
titulo(fig, "Ciclo estacional simulado, línea base 1995-2014, región del Meta",
       "Es lo que los modelos reproducen para el periodo histórico; sirve para compararlo luego con ERA5, CHIRPS e IDEAM.")
fig.tight_layout(rect=(0, 0.04, 1, 0.92))
guardar(fig, "ciclo_estacional_linea_base.png")

# ============ 6. Cambio mensual (precipitación y temperatura) ============
for v, nombre, ylab in (("pr", "precipitación", "Δ precipitación (%)"), ("tas", "temperatura", "Δ temperatura (°C)")):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)
    for ax, (pn, a, b) in zip(axes, PLAZOS):
        for k, n, c in ESC:
            vals = []
            for m in MIDS:
                cb, cs = clim(v, "historical", m, *BASE), clim(v, k, m, a, b)
                vals.append(((cs / cb - 1) * 100) if v == "pr" else (cs - cb))
            ax.plot(range(12), pd.concat(vals, axis=1).mean(axis=1).values, color=c, lw=2.2, label=n)
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_xticks(range(12), MES, fontsize=8)
        ax.set_title(f"{pn} {a}-{b}", loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel(ylab)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    nota = ("Cuidado: en dic-feb la base es ~0,5-1 mm/día y los porcentajes se inflan; en la estación lluviosa son más confiables."
            if v == "pr" else "Media del ensamble por mes.")
    titulo(fig, f"Cambio mensual de {nombre} por escenario y plazo (media del ensamble, respecto a 1995-2014)", nota)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    guardar(fig, f"cambio_mensual_{v}.png")

# ============ 7. Línea base por modelo ============
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
for ax, v, ylab, f in ((axes[0], "tas", "Temperatura media 1995-2014 (°C)", "{:.1f}"),
                       (axes[1], "pr", "Precipitación media 1995-2014 (mm/año)", "{:,.0f}")):
    vals = [base[(v, m)] * (365 if v == "pr" else 1) for m in MIDS]
    y = np.arange(len(MIDS))
    ax.barh(y, vals, color=[MCOL[m] for m in MIDS], height=0.6, zorder=2)
    for yi, val in zip(y, vals):
        ax.text(val, yi, " " + f.format(val), va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [MOD[m] for m in MIDS])
    ax.invert_yaxis()
    ax.set_xlabel(ylab)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(vals) * 1.15)
titulo(fig, "Línea base simulada por cada modelo (Historical 1995-2014, región del Meta)",
       "La dispersión de precipitación entre modelos es grande; por eso conviene corregir sesgo contra observaciones.")
fig.tight_layout(rect=(0, 0.05, 1, 0.92))
guardar(fig, "linea_base_por_modelo.png")
print("Listo ->", FIG)
