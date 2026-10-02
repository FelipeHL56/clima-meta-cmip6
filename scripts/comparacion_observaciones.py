"""Compara CMIP6 Historical (1995-2014) con ERA5, CHIRPS e IDEAM (promedios regionales mensuales).

Entradas: NetCDF Historical en cmip6_meta y CSV en observaciones/. Salidas: figuras en
resultados/figuras (prefijo comp_) y tablas en resultados/tablas.
Notas: IDEAM solo trae Tmax y Tmin, así que su temperatura media es (Tmax+Tmin)/2 (aproximada);
la precipitación de los modelos (mm/día) se pasa a mm/mes con los días de cada mes.
"""
import glob
import io
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

PROY = Path(__file__).resolve().parents[1]
OBS = PROY / "observaciones"
NC_DIR = Path(os.environ.get("CMIP6_NC_DIR", PROY / "datos" / "nc"))  # carpeta con los NetCDF (ruta sin tildes en Windows)
FIG, TAB = PROY / "resultados" / "figuras", PROY / "resultados" / "tablas"
PER = (1995, 2014)
MOD = {"access_cm2": "ACCESS-CM2", "gfdl_esm4": "GFDL-ESM4", "mpi_esm1_2_lr": "MPI-ESM1-2-LR",
       "mri_esm2_0": "MRI-ESM2-0", "noresm2_mm": "NorESM2-MM"}
MIDS = list(MOD)
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
OBS_COL = {"ERA5": "#2a78d6", "CHIRPS": "#eb6834", "IDEAM": "#1baf7a"}
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


# ---------------- observaciones ----------------
def leer(path):
    raw = Path(path).read_bytes()
    txt = raw.decode("utf-8-sig") if raw[:3] == b"\xef\xbb\xbf" else raw.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(txt.replace(",", ".") if ";" in txt.splitlines()[0] else txt), sep=";" if ";" in txt.splitlines()[0] else ",")
    df.index = pd.PeriodIndex(df.iloc[:, 0].astype(str), freq="M")
    return df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")


era_t = leer(OBS / "era5" / "era5_temperatura_mensual_region_1995-2025.csv")
era_t.columns = ["tmed", "tmax", "tmin"]
era_p = leer(OBS / "era5" / "era5_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0].rename("ERA5")
chi_p = leer(OBS / "chirps" / "chirps_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0].rename("CHIRPS")
ide_p = leer(OBS / "ideam" / "precipitacion_ideam_mensual_promedio_region_1995-2025.csv").iloc[:, 0].rename("IDEAM")
ide_t = leer(OBS / "ideam" / "temperatura_ideam_mensual_promedio_region_1995-2025.csv")
ide_t.columns = ["tmax", "tmin"]
ide_t["tmed"] = (ide_t.tmax + ide_t.tmin) / 2

obs_tas = pd.concat([era_t.tmed.rename("ERA5"), ide_t.tmed.rename("IDEAM")], axis=1)
obs_pr = pd.concat([era_p, chi_p, ide_p], axis=1)


def clim_obs(df):
    d = df[(df.index.year >= PER[0]) & (df.index.year <= PER[1])]
    return d.groupby(d.index.month).mean()


c_tas, c_pr = clim_obs(obs_tas), clim_obs(obs_pr)

# ---------------- modelos (Historical) ----------------
dias = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
m_tas, m_pr = {}, {}
for mod in MIDS:
    for v, store in (("near_surface_air_temperature", m_tas), ("precipitation", m_pr)):
        f = NC_DIR / f"{v}_historical_{mod}_1850-2014.nc"
        ds = xr.open_dataset(f)
        k = "tas" if v.startswith("near") else "pr"
        da = ds[k].mean(["lat", "lon"])
        s = pd.Series(da.values, index=pd.MultiIndex.from_arrays([da.time.dt.year.values, da.time.dt.month.values]))
        s = s.loc[PER[0]:PER[1]].groupby(level=1).mean()
        store[mod] = (s - 273.15).values if k == "tas" else (s * 86400).values * dias
M_tas, M_pr = pd.DataFrame(m_tas, index=range(1, 13)), pd.DataFrame(m_pr, index=range(1, 13))
M_tas["Ensamble"], M_pr["Ensamble"] = M_tas[MIDS].mean(axis=1), M_pr[MIDS].mean(axis=1)

# ---------------- métricas ----------------
filas = []
for var, M, C, unidad in (("Temperatura", M_tas, c_tas, "°C"), ("Precipitación", M_pr, c_pr, "mm/mes")):
    for ref in C.columns:
        for col in M.columns:
            sesgo = M[col].mean() - C[ref].mean()
            filas.append({"variable": var, "referencia": ref, "modelo": MOD.get(col, col),
                          "media_modelo": round(M[col].mean(), 2), "media_obs": round(C[ref].mean(), 2),
                          "sesgo": round(sesgo, 2),
                          "sesgo_%": round(100 * sesgo / C[ref].mean(), 1) if var == "Precipitación" else np.nan,
                          "RMSE_ciclo": round(float(np.sqrt(((M[col] - C[ref]) ** 2).mean())), 2),
                          "correl_ciclo": round(float(np.corrcoef(M[col], C[ref])[0, 1]), 3), "unidad": unidad})
met = pd.DataFrame(filas)
met.to_csv(TAB / "comparacion_modelos_vs_observaciones.csv", index=False, encoding="utf-8-sig")
clim_tab = pd.concat([M_tas.add_prefix("tas_"), c_tas.add_prefix("obs_tas_"), M_pr.add_prefix("pr_"), c_pr.add_prefix("obs_pr_")], axis=1).round(2)
clim_tab.index = MES
clim_tab.to_csv(TAB / "climatologia_modelos_y_observaciones_1995_2014.csv", encoding="utf-8-sig")
print(met.to_string(index=False))


def guardar(fig, n):
    fig.savefig(FIG / n, dpi=160)
    plt.close(fig)
    print("OK", n)


# ---------------- figura 1: ciclo estacional ----------------
fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
for ax, M, C, ylab in ((axes[0], M_tas, c_tas, "Temperatura media (°C)"), (axes[1], M_pr, c_pr, "Precipitación (mm/mes)")):
    for mod in MIDS:
        ax.plot(range(12), M[mod].values, color="#c3c2b7", lw=1.2, zorder=1)
    ax.plot(range(12), M["Ensamble"].values, color=INK, lw=3, ls="--", label="Modelos: media del ensamble", zorder=3)
    ax.plot([], [], color="#c3c2b7", lw=1.2, label="Cada modelo (n=5)")
    for ref in C.columns:
        ax.plot(range(12), C[ref].values, color=OBS_COL[ref], lw=2.6, marker="o", ms=4, label=ref + (" (aprox. (Tmax+Tmin)/2)" if ref == "IDEAM" and M is M_tas else ""), zorder=4)
    ax.set_xticks(range(12), MES)
    ax.set_ylabel(ylab)
    ax.grid(axis="x", visible=False)
axes[0].legend(frameon=False, fontsize=8, loc="lower left")
axes[1].legend(frameon=False, fontsize=8, loc="upper right")
fig.suptitle("Ciclo estacional 1995-2014: modelos CMIP6 (Historical) frente a observaciones, región del Meta",
             x=0.01, ha="left", fontsize=13, fontweight="bold")
fig.text(0.01, 0.01, "ERA5 usa el mismo recuadro que los modelos (lat 2-5, lon -74,5 a -71). IDEAM es el promedio de estaciones; CHIRPS, el promedio de la región.", fontsize=8, color=MUTED)
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
guardar(fig, "comp_ciclo_estacional_modelos_vs_obs.png")

# ---------------- figura 2: sesgo por modelo ----------------
fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
for ax, var, unidad, usar_pct in ((axes[0], "Temperatura", "°C", False), (axes[1], "Precipitación", "% respecto a la observación", True)):
    sub = met[met.variable == var]
    refs = list(sub.referencia.unique())
    nombres = [MOD[m] for m in MIDS] + ["Ensamble"]
    w = 0.8 / len(refs)
    for i, ref in enumerate(refs):
        vals = [sub[(sub.referencia == ref) & (sub.modelo == n)][("sesgo_%" if usar_pct else "sesgo")].iloc[0] for n in nombres]
        x = np.arange(len(nombres)) + (i - (len(refs) - 1) / 2) * w
        ax.bar(x, vals, w * 0.92, color=OBS_COL[ref], label=f"vs {ref}", zorder=2)
        for xi, vv in zip(x, vals):
            ax.text(xi, vv, f"{vv:+.1f}", ha="center", va="bottom" if vv >= 0 else "top", fontsize=7, color=INK)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(range(len(nombres)), nombres, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel(f"Sesgo del modelo ({unidad})")
    ax.set_title("Temperatura media" if var == "Temperatura" else "Precipitación anual", loc="left", fontsize=11, fontweight="bold")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=8)
fig.suptitle("Sesgo de cada modelo respecto a las observaciones (media 1995-2014; positivo = el modelo sobreestima)",
             x=0.01, ha="left", fontsize=13, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.93))
guardar(fig, "comp_sesgo_modelos.png")

# ---------------- figura 3: las observaciones entre sí ----------------
fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
ap = obs_pr[(obs_pr.index.year >= 1995)].groupby(obs_pr[(obs_pr.index.year >= 1995)].index.year).sum(min_count=12)
for ref in ap.columns:
    axes[0].plot(ap.index, ap[ref], color=OBS_COL[ref], lw=2.2, label=ref)
axes[0].set_ylabel("Precipitación anual (mm/año)")
axes[0].set_title("Las tres fuentes no coinciden entre sí", loc="left", fontsize=11, fontweight="bold")
axes[0].legend(frameon=False, fontsize=9)
axes[0].grid(axis="x", visible=False)
at = obs_tas.groupby(obs_tas.index.year).mean()
for ref in at.columns:
    axes[1].plot(at.index, at[ref], color=OBS_COL[ref], lw=2.2, label=ref + (" (aprox.)" if ref == "IDEAM" else ""))
axes[1].set_ylabel("Temperatura media anual (°C)")
axes[1].set_title("Temperatura: ERA5 vs IDEAM", loc="left", fontsize=11, fontweight="bold")
axes[1].legend(frameon=False, fontsize=9)
axes[1].grid(axis="x", visible=False)
fig.suptitle("Observaciones 1995-2025: incertidumbre entre fuentes", x=0.01, ha="left", fontsize=13, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.93))
guardar(fig, "comp_observaciones_entre_si.png")

print("\nObservaciones, media anual 1995-2014:")
print(c_pr.sum().round(0).to_string(), "\n", c_tas.mean().round(2).to_string())
print("Modelos (mm/año, °C):")
print(M_pr.sum().round(0).to_string(), "\n", M_tas.mean().round(2).to_string())
