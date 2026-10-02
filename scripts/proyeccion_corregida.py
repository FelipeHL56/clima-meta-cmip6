"""Proyecciones ajustadas con observaciones: factor de cambio mensual (método delta).

Temperatura:   T_proj(mes) = T_obs(mes, 1995-2014) + [T_modelo_escenario(mes) - T_modelo_hist(mes)]
Precipitación: P_proj(mes) = P_obs(mes, 1995-2014) x factor trimestral móvil [P_esc(3 meses) / P_hist(3 meses)],
               renormalizado para que el total anual cambie lo mismo que en el modelo. El factor puramente
               mensual infla el cambio anual 2-6 puntos (meses secos con base casi nula): queda como sensibilidad.
Se calcula por modelo y luego se promedia (ensamble) con rango mínimo-máximo entre modelos.
Referencia principal: ERA5 (T y P). Contraste en precipitación: CHIRPS.
Salidas: tablas CSV (mensual y anual) y figuras proy_*.png.
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
BASE = (1995, 2014)
PLAZOS = [("Corto", 2021, 2040), ("Mediano", 2041, 2060), ("Largo", 2081, 2100)]
ESC = [("ssp1_2_6", "SSP1-2.6 (bajas)", "#2a78d6"), ("ssp2_4_5", "SSP2-4.5 (medias)", "#eb6834"),
       ("ssp5_8_5", "SSP5-8.5 (altas)", "#1baf7a")]
MOD = {"access_cm2": "ACCESS-CM2", "gfdl_esm4": "GFDL-ESM4", "mpi_esm1_2_lr": "MPI-ESM1-2-LR",
       "mri_esm2_0": "MRI-ESM2-0", "noresm2_mm": "NorESM2-MM"}
MIDS = list(MOD)
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def leer(path):
    txt = Path(path).read_bytes().decode("utf-8-sig", errors="replace")
    pri = txt.splitlines()[0]
    sep = ";" if ";" in pri else ","
    df = pd.read_csv(io.StringIO(txt.replace(",", ".") if sep == ";" else txt), sep=sep)
    df.index = pd.PeriodIndex(df.iloc[:, 0].astype(str), freq="M")
    return df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")


def clim_obs(s):
    d = s[(s.index.year >= BASE[0]) & (s.index.year <= BASE[1])]
    return d.groupby(d.index.month).mean().values


T_ERA5 = clim_obs(leer(OBS / "era5" / "era5_temperatura_mensual_region_1995-2025.csv").iloc[:, 0])
P_ERA5 = clim_obs(leer(OBS / "era5" / "era5_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0])
P_CHI = clim_obs(leer(OBS / "chirps" / "chirps_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0])
REF = {("tas", "ERA5"): T_ERA5, ("pr", "ERA5"): P_ERA5, ("pr", "CHIRPS"): P_CHI}

# ---------------- modelos ----------------
mensual = {}
for f in sorted(glob.glob(str(NC_DIR / "*.nc"))):
    m = re.match(r"(near_surface_air_temperature|precipitation)_(ssp\d_\d_\d|historical)_(.+)_(\d{4})-(\d{4})$",
                 os.path.basename(f)[:-3])
    var, exp, mod, _, _ = m.groups()
    v = "tas" if var.startswith("near") else "pr"
    da = xr.open_dataset(f)[v].mean(["lat", "lon"])
    da = da * 86400 if v == "pr" else da - 273.15
    mensual[(v, exp, mod)] = pd.Series(da.values, index=pd.MultiIndex.from_arrays(
        [da.time.dt.year.values, da.time.dt.month.values]))


def clim(v, exp, mod, a, b):
    return mensual[(v, exp, mod)].loc[a:b].groupby(level=1).mean().values


# ---------------- proyección ajustada ----------------
filas_m, filas_a = [], []
dias = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def ventana3(x):  # suma móvil circular de 3 meses, centrada
    return np.array([x[(i - 1) % 12] + x[i] + x[(i + 1) % 12] for i in range(12)])



proy = {}  # (v, ref, exp, plazo) -> DataFrame 12 x modelos (valores absolutos mensuales)
for (v, ref), obs in REF.items():
    unidad = "°C" if v == "tas" else "mm/mes"
    for k, en, _ in ESC:
        for pn, a, b in PLAZOS:
            cols = {}
            for mod in MIDS:
                cb, cs = clim(v, "historical", mod, *BASE), clim(v, k, mod, a, b)
                if v == "tas":
                    cols[mod] = obs + (cs - cb)
                else:
                    # factor trimestral móvil (estable en meses secos) renormalizado para que el total
                    # anual cambie exactamente lo que cambia el modelo (ver hoja de sensibilidad)
                    cbm, csm = cb * dias, cs * dias
                    raw = obs * (ventana3(csm) / ventana3(cbm))
                    cols[mod] = raw * (obs.sum() * (csm.sum() / cbm.sum())) / raw.sum()
            D = pd.DataFrame(cols, index=range(1, 13))
            proy[(v, ref, k, pn)] = D
            for mi in range(12):
                filas_m.append({"variable": "Temperatura" if v == "tas" else "Precipitación", "referencia": ref,
                                "escenario": en, "plazo": f"{pn} {a}-{b}", "mes": MES[mi],
                                "observado_1995_2014": round(float(obs[mi]), 2),
                                "media_ensamble": round(D.iloc[mi].mean(), 2), "minimo": round(D.iloc[mi].min(), 2),
                                "maximo": round(D.iloc[mi].max(), 2), "unidad": unidad})
            ann = D.mean() if v == "tas" else D.sum()
            obs_ann = obs.mean() if v == "tas" else obs.sum()
            fila = {"variable": "Temperatura" if v == "tas" else "Precipitación", "referencia": ref,
                    "escenario": en, "plazo": f"{pn} {a}-{b}", "observado_1995_2014": round(float(obs_ann), 2)}
            for mod in MIDS:
                fila[MOD[mod]] = round(float(ann[mod]), 2)
            fila.update({"media_ensamble": round(float(ann.mean()), 2), "minimo": round(float(ann.min()), 2),
                         "maximo": round(float(ann.max()), 2), "cambio_vs_obs": round(float(ann.mean() - obs_ann), 2) if v == "tas"
                         else round(float((ann.mean() / obs_ann - 1) * 100), 1),
                         "unidad_anual": "°C" if v == "tas" else "mm/año", "unidad_cambio": "°C" if v == "tas" else "%"})
            filas_a.append(fila)
pd.DataFrame(filas_m).to_csv(TAB / "proyeccion_ajustada_mensual.csv", index=False, encoding="utf-8-sig")
anual = pd.DataFrame(filas_a)
anual.to_csv(TAB / "proyeccion_ajustada_anual.csv", index=False, encoding="utf-8-sig")
print(anual[["variable", "referencia", "escenario", "plazo", "observado_1995_2014", "media_ensamble", "minimo", "maximo", "cambio_vs_obs"]].to_string(index=False))


# ---------------- sensibilidad (precipitación, ERA5): ¿cuánto pesan los meses secos? ----------------
sens = []
for k, en, _ in ESC:
    for pn, a, b in PLAZOS:
        res = {"a) factor mensual": [], "b) factor trimestral móvil": [], "c) factor anual": [], "d) solo modelo (sin ajuste)": []}
        for mod in MIDS:
            cb, cs = clim("pr", "historical", mod, *BASE) * dias, clim("pr", k, mod, a, b) * dias
            o = P_ERA5
            res["a) factor mensual"].append((o * (cs / cb)).sum() / o.sum() - 1)
            res["b) factor trimestral móvil"].append((o * (ventana3(cs) / ventana3(cb))).sum() / o.sum() - 1)
            res["c) factor anual"].append(cs.sum() / cb.sum() - 1)
            res["d) solo modelo (sin ajuste)"].append(cs.sum() / cb.sum() - 1)
        fila = {"escenario": en, "plazo": f"{pn} {a}-{b}"}
        fila.update({m: round(100 * float(np.mean(v)), 1) for m, v in res.items()})
        sens.append(fila)
sens = pd.DataFrame(sens)
sens.to_csv(TAB / "proyeccion_ajustada_sensibilidad_precipitacion.csv", index=False, encoding="utf-8-sig")
print("\nSensibilidad: cambio de precipitación anual (%, media del ensamble, base ERA5)")
print(sens.to_string(index=False))


def guardar(fig, n):
    fig.savefig(FIG / n, dpi=160)
    plt.close(fig)
    print("OK", n)


# ---------------- figuras: ciclo estacional ajustado ----------------
for v, nombre, ylab in (("pr", "precipitación", "Precipitación (mm/mes)"), ("tas", "temperatura", "Temperatura media (°C)")):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (pn, a, b) in zip(axes, PLAZOS):
        for k, en, c in ESC:
            D = proy[(v, "ERA5", k, pn)]
            ax.fill_between(range(12), D.min(axis=1), D.max(axis=1), color=c, alpha=0.14, lw=0)
            ax.plot(range(12), D.mean(axis=1), color=c, lw=2.2, label=en)
        ax.plot(range(12), REF[(v, "ERA5")], color=INK, lw=2.6, ls="--", label="ERA5 observado 1995-2014")
        if v == "pr":
            ax.plot(range(12), REF[("pr", "CHIRPS")], color=MUTED, lw=1.6, ls=":", label="CHIRPS observado 1995-2014")
        ax.set_xticks(range(12), MES, fontsize=8)
        ax.set_title(f"{pn} {a}-{b}", loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel(ylab)
    hs, ls = axes[0].get_legend_handles_labels()
    fig.legend(hs, ls, frameon=False, fontsize=9, loc="lower center", ncol=len(ls), bbox_to_anchor=(0.5, 0.045))
    fig.suptitle(f"Meta: {nombre} proyectada y ajustada con ERA5 (media del ensamble y rango entre modelos)",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    metodo = ("Método: climatología observada 1995-2014 + cambio mensual de cada modelo."
              if v == "tas" else
              "Método: climatología observada 1995-2014 x factor trimestral móvil de cada modelo, renormalizado al cambio anual del modelo.")
    fig.text(0.01, 0.01, metodo, fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.12, 1, 0.93))
    guardar(fig, f"proy_ciclo_estacional_{v}.png")

# ---------------- figura: resumen anual absoluto ----------------
fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
for ax, v, ylab, fmt in ((axes[0], "tas", "Temperatura media anual (°C)", "{:.1f}"),
                         (axes[1], "pr", "Precipitación anual (mm/año)", "{:,.0f}")):
    w = 0.25
    sub = anual[(anual.variable == ("Temperatura" if v == "tas" else "Precipitación")) & (anual.referencia == "ERA5")]
    for gi, (pn, a, b) in enumerate(PLAZOS):
        for si, (k, en, c) in enumerate(ESC):
            r = sub[(sub.escenario == en) & (sub.plazo == f"{pn} {a}-{b}")].iloc[0]
            x = gi + (si - 1) * (w + 0.02)
            ax.bar(x, r.media_ensamble, w, color=c, zorder=2)
            ax.plot([x, x], [r.minimo, r.maximo], color=INK2, lw=1.4, zorder=3)
            ax.plot([x - 0.04, x + 0.04], [r.minimo] * 2, color=INK2, lw=1.4, zorder=3)
            ax.plot([x - 0.04, x + 0.04], [r.maximo] * 2, color=INK2, lw=1.4, zorder=3)
            ax.text(x, r.maximo, fmt.format(r.media_ensamble), ha="center", va="bottom", fontsize=8, color=INK, fontweight="bold")
    ax.axhline(REF[(v, "ERA5")].mean() if v == "tas" else REF[(v, "ERA5")].sum(), color=INK, ls="--", lw=1.4, zorder=1,
               label="ERA5 observado 1995-2014")
    if v == "pr":
        ax.axhline(REF[("pr", "CHIRPS")].sum(), color=MUTED, ls=":", lw=1.6, zorder=1, label="CHIRPS observado 1995-2014")
    lo = anual[anual.variable == ("Temperatura" if v == "tas" else "Precipitación")].minimo.min()
    hi = anual[anual.variable == ("Temperatura" if v == "tas" else "Precipitación")].maximo.max()
    ax.set_ylim(lo - (hi - lo) * 0.25 if v == "tas" else 0, hi + (hi - lo) * 0.12)
    ax.set_xticks(range(3), [f"{pn}\n{a}-{b}" for pn, a, b in PLAZOS])
    ax.set_ylabel(ylab)
    ax.grid(axis="x", visible=False)
    ax.set_title("Temperatura" if v == "tas" else "Precipitación", loc="left", fontsize=11, fontweight="bold")
h = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in ESC]
hs, ls = axes[1].get_legend_handles_labels()
fig.legend(h + hs, [e for _, e, _ in ESC] + ls, frameon=False, fontsize=9, loc="lower center", ncol=6, bbox_to_anchor=(0.5, 0.0))
fig.suptitle("Meta: valores anuales proyectados y ajustados con ERA5 (barra = media del ensamble; bigote = rango entre modelos)",
             x=0.01, ha="left", fontsize=13, fontweight="bold")
fig.tight_layout(rect=(0, 0.08, 1, 0.93))
guardar(fig, "proy_resumen_anual_absoluto.png")
