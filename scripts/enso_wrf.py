"""Integración del ONI (ENSO) y del WRF (4 km) con las proyecciones CMIP6 del Meta.

Bloques:
 1. ONI y fases; años WRF en el contexto ENSO.
 2. Efecto del ENSO en la temperatura y la lluvia observadas (regresión con tendencia, errores Newey-West).
 3. Validación del WRF (recuadro) frente a ERA5, y llanos frente a IDEAM.
 4. Zonas cordillera/llanos con el WRF y proyecciones por zona (offset constante sobre la proyección ajustada ERA5).
 5. Señal ENSO frente a señal de cambio climático; variabilidad interanual de los modelos CMIP6 frente a ERA5.
Salidas: tablas CSV en resultados/tablas y figuras en resultados/figuras.
Requiere haber ejecutado antes wrf_procesar.py y proyeccion_corregida.py.
"""
import io
import glob
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.patches import Rectangle

PROY = Path(__file__).resolve().parents[1]
OBS = PROY / "observaciones"
TAB, FIG = PROY / "resultados" / "tablas", PROY / "resultados" / "figuras"
NC_DIR = Path(os.environ.get("CMIP6_NC_DIR", PROY / "datos" / "nc"))  # carpeta con los NetCDF (ruta sin tildes en Windows)
AREA = dict(N=5.0, S=2.0, W=-74.5, E=-71.0)
WRF_ANIOS = [2000, 2011, 2013, 2014, 2015, 2016, 2018]
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
ESC = [("SSP1-2.6 (bajas)", "#2a78d6"), ("SSP2-4.5 (medias)", "#eb6834"), ("SSP5-8.5 (altas)", "#1baf7a")]
PLAZOS = ["Corto 2021-2040", "Mediano 2041-2060", "Largo 2081-2100"]
C_NINO, C_NINA, C_NEU = "#e34948", "#2a78d6", "#898781"
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def guardar(fig, n):
    fig.savefig(FIG / n, dpi=160)
    plt.close(fig)
    print("OK", n, flush=True)


def titulo(fig, t, sub=None):
    fig.suptitle(t, x=0.01, ha="left", fontsize=13, fontweight="bold")
    if sub:
        fig.text(0.01, 0.01, sub, fontsize=8, color=MUTED)


# ======================= datos =======================
def leer(path):
    txt = Path(path).read_bytes().decode("utf-8-sig", errors="replace")
    sep = ";" if ";" in txt.splitlines()[0] else ","
    df = pd.read_csv(io.StringIO(txt.replace(",", ".") if sep == ";" else txt), sep=sep)
    df.index = pd.PeriodIndex(df.iloc[:, 0].astype(str), freq="M")
    return df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")


o = pd.read_csv(OBS / "oni" / "oni_mensual.csv", parse_dates=["fecha"])
ONI = pd.Series(o.oni.values, index=pd.PeriodIndex(o.fecha, freq="M")).dropna()

era_t = leer(OBS / "era5" / "era5_temperatura_mensual_region_1995-2025.csv")
era_t.columns = ["tmed", "tmax", "tmin"]
era_p = leer(OBS / "era5" / "era5_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0]
chi_p = leer(OBS / "chirps" / "chirps_precipitacion_mensual_region_1995-2025.csv").iloc[:, 0]
ide_p = leer(OBS / "ideam" / "precipitacion_ideam_mensual_promedio_region_1995-2025.csv").iloc[:, 0]
ide_t = leer(OBS / "ideam" / "temperatura_ideam_mensual_promedio_region_1995-2025.csv")
ide_t.columns = ["tmax", "tmin"]
ide_t["tmed"] = (ide_t.tmax + ide_t.tmin) / 2
IDX = era_t.index  # 1995-01 .. 2025-12
oni_obs = ONI.reindex(IDX)


# ======================= 1. ONI y fases =======================
def fase(v):
    return "El Niño" if v >= 0.5 else ("La Niña" if v <= -0.5 else "Neutro")


oni_anual = ONI.groupby(ONI.index.year).mean()
tab_anios = pd.DataFrame({"anio": WRF_ANIOS, "ONI_medio_anual": [round(oni_anual[y], 2) for y in WRF_ANIOS],
                          "ONI_max": [round(ONI[str(y)].max(), 2) for y in WRF_ANIOS],
                          "ONI_min": [round(ONI[str(y)].min(), 2) for y in WRF_ANIOS]})
tab_anios["fase_anual"] = tab_anios.ONI_medio_anual.map(fase)
print(tab_anios.to_string(index=False))
tab_anios.to_csv(TAB / "enso_anios_wrf_oni.csv", index=False, encoding="utf-8-sig")

# ======================= 2. ENSO -> temperatura y lluvia (regresión) =======================
def anom(s, relativa):
    clim = s.groupby(s.index.month).transform("mean")
    return (s / clim - 1) * 100 if relativa else s - clim


def ols_hac(y, X, L=12):
    """MCO con errores estándar Newey-West (L rezagos)."""
    n, k = X.shape
    b = np.linalg.solve(X.T @ X, X.T @ y)
    u = y - X @ b
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        G = Xu[l:].T @ Xu[:-l]
        S += w * (G + G.T)
    XtXi = np.linalg.inv(X.T @ X)
    cov = XtXi @ S @ XtXi
    return b, np.sqrt(np.diag(cov))


series = {"T ERA5 (°C)": (era_t.tmed, False), "T IDEAM aprox. (°C)": (ide_t.tmed, False),
          "P ERA5 (%)": (era_p, True), "P CHIRPS (%)": (chi_p, True), "P IDEAM (%)": (ide_p, True)}
filas, lag_corr = [], {}
for nombre, (s, rel) in series.items():
    a = anom(s.loc[IDX], rel)
    # detrend lineal para escoger el rezago
    t = np.arange(len(a))
    res = a.values - np.polyval(np.polyfit(t, a.values, 1), t)
    cors = [np.corrcoef(res[L:], oni_obs.shift(L).values[L:])[0, 1] for L in range(0, 7)]
    lag_corr[nombre] = cors
    Lb = int(np.argmax(np.abs(cors)))
    X = np.column_stack([np.ones(len(a)), t / 120.0, oni_obs.shift(Lb).values])
    ok = ~np.isnan(X[:, 2])
    b, se = ols_hac(a.values[ok], X[ok])
    filas.append({"variable": nombre, "rezago_meses": Lb, "corr_detrend": round(cors[Lb], 2),
                  "efecto_por_1C_ONI": round(b[2], 3), "error_NW": round(se[2], 3), "t": round(b[2] / se[2], 1),
                  "tendencia_por_decada": round(b[1] * 1.0, 3),
                  "unidad": "% por °C de ONI" if rel else "°C por °C de ONI"})
enso = pd.DataFrame(filas)
enso.to_csv(TAB / "enso_efecto_regresion.csv", index=False, encoding="utf-8-sig")
print("\nEfecto ENSO (regresión con tendencia, Newey-West):")
print(enso.to_string(index=False))
slope_T = float(enso.loc[enso.variable == "T ERA5 (°C)", "efecto_por_1C_ONI"].iloc[0])
se_T = float(enso.loc[enso.variable == "T ERA5 (°C)", "error_NW"].iloc[0])

# ---- composites anuales de T observada por fase (año calendario, rezago ya incluido en el año) ----
tanual = era_t.tmed.groupby(era_t.index.year).mean()
oni_a = ONI.groupby(ONI.index.year).mean().reindex(tanual.index)
t_ok = np.arange(len(tanual))
tanual_res = tanual - np.polyval(np.polyfit(t_ok, tanual.values, 1), t_ok) + tanual.mean()  # sin tendencia
fa = oni_a.map(fase)
comp_anual = pd.DataFrame({"anio": tanual.index, "ONI_medio": oni_a.round(2).values, "fase": fa.values,
                           "T_ERA5": tanual.round(2).values, "T_ERA5_sin_tendencia": tanual_res.round(2).values})
comp_anual.to_csv(TAB / "enso_temperatura_anual_era5_por_fase.csv", index=False, encoding="utf-8-sig")
print("\nT anual ERA5 (sin tendencia) por fase:", comp_anual.groupby("fase").T_ERA5_sin_tendencia.agg(["mean", "count"]).round(2).to_dict())

# ======================= 3. WRF =======================
Z = np.load(OBS / "wrf" / "wrf_tk_mensual_mapas.npz")
xlat, xlon = Z["xlat"], Z["xlon"]
M = {y: Z[f"y{y}"] for y in WRF_ANIOS}  # (12, ny, nx)
box = (xlat >= AREA["S"]) & (xlat <= AREA["N"]) & (xlon >= AREA["W"]) & (xlon <= AREA["E"])
media_multi = np.mean([M[y].mean(axis=0) for y in WRF_ANIOS], axis=0)
cord = box & (media_multi < 22.0)
lla = box & ~(media_multi < 22.0)
print(f"\nWRF: celdas del recuadro {box.sum()} | cordillera (<22 °C) {cord.sum()} ({100 * cord.sum() / box.sum():.1f} %) | llanos {lla.sum()}")


def zona(m, mask):
    return np.array([m[i][mask].mean() for i in range(12)])


wrf = pd.DataFrame([{"anio": y, "mes": i + 1, "recuadro": zona(M[y], box)[i], "cordillera": zona(M[y], cord)[i],
                     "llanos": zona(M[y], lla)[i]} for y in WRF_ANIOS for i in range(12)])
wrf["periodo"] = pd.PeriodIndex([f"{a}-{m:02d}" for a, m in zip(wrf.anio, wrf.mes)], freq="M")
wrf = wrf.set_index("periodo")
wrf.round(2).to_csv(TAB / "wrf_zonas_mensual.csv", encoding="utf-8-sig")

# validación mensual
val = pd.DataFrame({"WRF_recuadro": wrf.recuadro, "ERA5": era_t.tmed.reindex(wrf.index),
                    "WRF_llanos": wrf.llanos, "IDEAM_aprox": ide_t.tmed.reindex(wrf.index),
                    "WRF_cordillera": wrf.cordillera})
val.round(2).to_csv(TAB / "wrf_validacion_mensual.csv", encoding="utf-8-sig")
pd.DataFrame({"zona": ["cordillera", "llanos", "recuadro"], "celdas": [int(cord.sum()), int(lla.sum()), int(box.sum())]}).to_csv(
    TAB / "wrf_zonas_celdas.csv", index=False, encoding="utf-8-sig")
met = []
for a, b in (("WRF_recuadro", "ERA5"), ("WRF_llanos", "IDEAM_aprox")):
    d = val[a] - val[b]
    met.append({"comparacion": f"{a} vs {b}", "sesgo_C": round(d.mean(), 2), "RMSE_C": round(np.sqrt((d ** 2).mean()), 2),
                "correlacion_mensual": round(val[a].corr(val[b]), 3),
                "correl_anomalia_mensual": round((val[a] - val[a].groupby(val.index.month).transform("mean")).corr(
                    val[b] - val[b].groupby(val.index.month).transform("mean")), 3)})
met = pd.DataFrame(met)
met.to_csv(TAB / "wrf_validacion_metricas.csv", index=False, encoding="utf-8-sig")
print("\nValidación WRF:\n", met.to_string(index=False))

# anual por año
anual_wrf = wrf.groupby("anio")[["recuadro", "cordillera", "llanos"]].mean()
anual_wrf["ERA5"] = [era_t.tmed.loc[str(y)].mean() for y in anual_wrf.index]
anual_wrf["IDEAM_aprox"] = [ide_t.tmed.loc[str(y)].mean() for y in anual_wrf.index]
anual_wrf["ONI"] = [oni_anual[y] for y in anual_wrf.index]
anual_wrf["fase"] = anual_wrf.ONI.map(fase)
anual_wrf.round(2).to_csv(TAB / "wrf_anual_vs_era5_oni.csv", encoding="utf-8-sig")
print(anual_wrf.round(2).to_string())
print("Correlación entre años WRF y ERA5 (7 años):", round(anual_wrf.recuadro.corr(anual_wrf.ERA5), 2),
      "| con ONI WRF:", round(anual_wrf.recuadro.corr(anual_wrf.ONI), 2), "ERA5:", round(anual_wrf.ERA5.corr(anual_wrf.ONI), 2))

# ======================= 4. Zonas y proyección por zona =======================
clim_w = wrf.groupby("mes")[["recuadro", "cordillera", "llanos"]].mean()
off = pd.DataFrame({"cordillera": clim_w.cordillera - clim_w.recuadro, "llanos": clim_w.llanos - clim_w.recuadro})
off.index = MES
off.round(2).to_csv(TAB / "wrf_offsets_zona_vs_recuadro.csv", encoding="utf-8-sig")
print("\nOffset zona - recuadro (°C, media mensual WRF):", off.mean().round(2).to_dict())

pm = pd.read_csv(TAB / "proyeccion_ajustada_mensual.csv", encoding="utf-8-sig")
pt = pm[(pm.variable == "Temperatura") & (pm.referencia == "ERA5")].copy()
filas = []
for (esc, plz), g in pt.groupby(["escenario", "plazo"], sort=False):
    g = g.set_index("mes").loc[MES]
    for zn in ("recuadro", "cordillera", "llanos"):
        o_ = 0.0 if zn == "recuadro" else off[zn].values
        filas.append({"zona": zn, "escenario": esc, "plazo": plz,
                      "observado_ERA5_1995_2014": round((g.observado_1995_2014.values + o_).mean(), 2),
                      "media_ensamble": round((g.media_ensamble.values + o_).mean(), 2),
                      "minimo": round((g.minimo.values + o_).mean(), 2), "maximo": round((g.maximo.values + o_).mean(), 2)})
zp = pd.DataFrame(filas)
zp["cambio"] = (zp.media_ensamble - zp.observado_ERA5_1995_2014).round(2)
zp.to_csv(TAB / "proyeccion_temperatura_por_zona.csv", index=False, encoding="utf-8-sig")
print(zp[zp.plazo.str.startswith("Largo")].to_string(index=False))

# ======================= 5. ENSO vs cambio climático y variabilidad de modelos =======================
cc = pt.groupby(["escenario", "plazo"], sort=False).apply(
    lambda g: pd.Series({"cambio": g.media_ensamble.mean() - g.observado_1995_2014.mean()}), include_groups=False).reset_index()
eff_nino = slope_T * 1.5      # año con ONI sostenido +1,5 (El Niño fuerte)
eff_nina = slope_T * -1.0     # año con ONI sostenido -1,0 (La Niña moderada)
print(f"\nEfecto ENSO sobre T (ERA5): {slope_T:+.2f} ± {se_T:.2f} °C por °C de ONI -> El Niño fuerte (+1,5): {eff_nino:+.2f} °C; La Niña (-1,0): {eff_nina:+.2f} °C")
rows = []
for _, r in cc.iterrows():
    base = pt[(pt.escenario == r.escenario) & (pt.plazo == r.plazo)].media_ensamble.mean()
    rows.append({"escenario": r.escenario, "plazo": r.plazo, "T_proyectada_neutro": round(base, 2),
                 "T_en_año_El_Niño_fuerte": round(base + eff_nino, 2), "T_en_año_La_Niña": round(base + eff_nina, 2),
                 "cambio_climatico_vs_1995_2014": round(r.cambio, 2), "efecto_ENSO_El_Niño_fuerte": round(eff_nino, 2)})
pd.DataFrame(rows).to_csv(TAB / "proyeccion_temperatura_con_enso.csv", index=False, encoding="utf-8-sig")

# variabilidad interanual (sin tendencia) modelos vs ERA5, 1995-2014
def det_std(x):
    t = np.arange(len(x))
    return float(np.std(x - np.polyval(np.polyfit(t, x, 1), t), ddof=1))


var_rows = []
era_ta = era_t.tmed.loc["1995":"2014"].groupby(era_t.loc["1995":"2014"].index.year).mean().values
era_pa = era_p.loc["1995":"2014"].groupby(era_p.loc["1995":"2014"].index.year).sum().values
chi_pa = chi_p.loc["1995":"2014"].groupby(chi_p.loc["1995":"2014"].index.year).sum().values
var_rows.append({"fuente": "ERA5", "std_T_C": round(det_std(era_ta), 2), "std_P_%": round(100 * det_std(era_pa) / era_pa.mean(), 1)})
var_rows.append({"fuente": "CHIRPS", "std_T_C": np.nan, "std_P_%": round(100 * det_std(chi_pa) / chi_pa.mean(), 1)})
for f in sorted(glob.glob(str(NC_DIR / "*_historical_*.nc"))):
    mm = re.match(r".*(near_surface_air_temperature|precipitation)_historical_(.+)_1850-2014\.nc", f.replace("\\", "/"))
    if not mm or mm.group(1) != "near_surface_air_temperature":
        continue
    mod = mm.group(2)
    dt = xr.open_dataset(f)["tas"].mean(["lat", "lon"]) - 273.15
    dp = xr.open_dataset(f.replace("near_surface_air_temperature", "precipitation"))["pr"].mean(["lat", "lon"]) * 86400
    at = dt.groupby("time.year").mean().sel(year=slice(1995, 2014)).values
    ap = (dp.groupby("time.year").mean() * 365).sel(year=slice(1995, 2014)).values
    var_rows.append({"fuente": mod, "std_T_C": round(det_std(at), 2), "std_P_%": round(100 * det_std(ap) / ap.mean(), 1)})
var = pd.DataFrame(var_rows)
var.to_csv(TAB / "variabilidad_interanual_modelos_vs_obs.csv", index=False, encoding="utf-8-sig")
print("\nVariabilidad interanual 1995-2014 (sin tendencia):\n", var.to_string(index=False))

# ======================= FIGURAS =======================
# --- F1: ONI y años WRF ---
fig, ax = plt.subplots(figsize=(14, 4.6))
s = ONI.loc["1995":]
x = s.index.to_timestamp()
ax.fill_between(x, 0, s.values, where=s.values >= 0.5, color=C_NINO, alpha=0.85, lw=0, step="mid", label="El Niño (ONI ≥ +0,5)")
ax.fill_between(x, 0, s.values, where=s.values <= -0.5, color=C_NINA, alpha=0.85, lw=0, step="mid", label="La Niña (ONI ≤ -0,5)")
ax.fill_between(x, 0, s.values, where=(s.values > -0.5) & (s.values < 0.5), color=C_NEU, alpha=0.5, lw=0, step="mid", label="Neutro")
ax.axhline(0.5, color=AXIS, lw=0.8)
ax.axhline(-0.5, color=AXIS, lw=0.8)
for y in WRF_ANIOS:
    ax.axvspan(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31"), color=INK, alpha=0.06, lw=0)
    ax.text(pd.Timestamp(f"{y}-07-01"), 2.95, str(y), ha="center", va="top", fontsize=8, color=INK2)
ax.set_ylim(-2.4, 3.0)
ax.set_ylabel("ONI (°C)")
ax.grid(axis="x", visible=False)
ax.legend(frameon=False, fontsize=9, loc="lower left", ncol=3)
ax.annotate(f"jul-2026\nONI {ONI.iloc[-1]:+.1f}", (x[-1], ONI.iloc[-1]), xytext=(10, 4), textcoords="offset points", fontsize=9,
            ha="left", va="center", color=INK)
ax.set_xlim(x[0], x[-1] + pd.Timedelta(days=300))
titulo(fig, "ENSO 1995-2026 (ONI) y años con simulación WRF (franjas grises)",
       "El set WRF mezcla La Niña (2000, 2011), neutro (2013, 2014) y El Niño (2015, 2016); 2018 es neutro. ONI: anomalía de TSM en Niño 3.4, media móvil de 3 meses.")
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
guardar(fig, "enso_oni_serie_y_anios_wrf.png")

# --- F2: ENSO -> temperatura y lluvia ---
fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
ax = axes[0]
a = anom(era_t.tmed.loc[IDX], False)
t = np.arange(len(a))
res = a.values - np.polyval(np.polyfit(t, a.values, 1), t)
Lb = int(enso.loc[enso.variable == "T ERA5 (°C)", "rezago_meses"].iloc[0])
xo, yo = oni_obs.shift(Lb).values, res
okm = ~np.isnan(xo)
cols = np.where(xo[okm] >= 0.5, C_NINO, np.where(xo[okm] <= -0.5, C_NINA, C_NEU))
ax.scatter(xo[okm], yo[okm], c=cols, s=14, alpha=0.75, lw=0)
bb = np.polyfit(xo[okm], yo[okm], 1)
xx = np.linspace(-2, 2.8, 10)
ax.plot(xx, np.polyval(bb, xx), color=INK, lw=2)
ax.set_xlabel(f"ONI ({Lb} meses antes)")
ax.set_ylabel("Anomalía mensual de T ERA5 sin tendencia (°C)")
ax.set_title(f"Temperatura: {bb[0]:+.2f} °C por °C de ONI", loc="left", fontsize=11, fontweight="bold")
ax = axes[1]
w = 0.26
for i, (nom, col) in enumerate((("P ERA5 (%)", "#2a78d6"), ("P CHIRPS (%)", "#eb6834"), ("P IDEAM (%)", "#1baf7a"))):
    r_ = enso[enso.variable == nom].iloc[0]
    ax.bar(i, r_.efecto_por_1C_ONI, 0.6, color=col, zorder=2)
    ax.errorbar(i, r_.efecto_por_1C_ONI, yerr=1.96 * r_.error_NW, color=INK2, capsize=4, lw=1.4, zorder=3)
    ax.text(i, 0.35, f"t = {r_.t}", ha="center", va="bottom", fontsize=9, color=INK2)
ax.set_ylim(-11, 3)
ax.axhline(0, color=AXIS, lw=1)
ax.set_xticks(range(3), ["ERA5", "CHIRPS", "IDEAM"])
ax.set_ylabel("Cambio de lluvia por °C de ONI (%)")
ax.set_title("Lluvia: efecto débil e incierto", loc="left", fontsize=11, fontweight="bold")
ax.grid(axis="x", visible=False)
ax = axes[2]
for nom, col in (("T ERA5 (°C)", "#2a78d6"), ("T IDEAM aprox. (°C)", "#1baf7a"), ("P ERA5 (%)", "#eb6834"), ("P CHIRPS (%)", "#e87ba4")):
    ax.plot(range(7), lag_corr[nom], color=col, lw=2, marker="o", ms=4, label=nom)
ax.axhline(0, color=AXIS, lw=1)
ax.set_xlabel("Rezago (meses): ONI adelantado")
ax.set_ylabel("Correlación (sin tendencia)")
ax.set_title("La respuesta térmica llega con 2-4 meses", loc="left", fontsize=11, fontweight="bold")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="x", visible=False)
titulo(fig, "Efecto histórico del ENSO sobre el Meta (1995-2025, datos mensuales)",
       "Regresión anomalía ~ tendencia + ONI(rezago); barras de error = ±1,96 errores Newey-West (consideran autocorrelación mensual).")
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
guardar(fig, "enso_efecto_temperatura_lluvia.png")

# --- F3: ENSO frente a cambio climático ---
fig, ax = plt.subplots(figsize=(11, 5.4))
w = 0.25
for gi, plz in enumerate(PLAZOS):
    for si, (esc, col) in enumerate(ESC):
        v = float(cc[(cc.escenario == esc) & (cc.plazo == plz)].cambio.iloc[0])
        x = gi + (si - 1) * (w + 0.02)
        ax.bar(x, v, w, color=col, zorder=2)
        ax.text(x, v + 0.07, f"+{v:.1f}", ha="center", fontsize=8, color=INK, fontweight="bold")
ax.axhspan(eff_nina, eff_nino, color=INK, alpha=0.07, zorder=1)
l1 = ax.axhline(eff_nino, color=C_NINO, ls="--", lw=1.5, label=f"Efecto de un año El Niño fuerte (ONI +1,5): {eff_nino:+.1f} °C")
l2 = ax.axhline(eff_nina, color=C_NINA, ls="--", lw=1.5, label=f"Efecto de un año La Niña (ONI -1,0): {eff_nina:+.1f} °C")
ax.axhline(0, color=AXIS, lw=1)
ax.set_xticks(range(3), PLAZOS)
ax.set_ylabel("Δ temperatura respecto a 1995-2014 (°C)")
ax.grid(axis="x", visible=False)
h = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in ESC] + [l1, l2]
ax.legend(h, [e for e, _ in ESC] + [l1.get_label(), l2.get_label()], frameon=False, fontsize=9, loc="upper left")
titulo(fig, "Señal del cambio climático frente a la señal ENSO sobre la temperatura del Meta",
       f"Franja gris = efecto de un año ENSO sobre la T anual ({slope_T:+.2f} ± {1.96 * se_T:.2f} °C por °C de ONI, regresión ERA5). Se suma al cambio climático si el ENSO persiste todo el año.")
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
guardar(fig, "enso_vs_cambio_climatico.png")

# --- F4: validación WRF mensual ---
fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharey=True)
for ax, y in zip(axes.ravel(), WRF_ANIOS):
    sel = val.loc[str(y)]
    ax.plot(range(12), sel.ERA5.values, color="#2a78d6", lw=2.2, label="ERA5 (recuadro)")
    ax.plot(range(12), sel.WRF_recuadro.values, color=INK, lw=2.2, ls="--", label="WRF recuadro")
    ax.plot(range(12), sel.IDEAM_aprox.values, color="#1baf7a", lw=1.8, label="IDEAM aprox.")
    ax.plot(range(12), sel.WRF_llanos.values, color="#1baf7a", lw=1.8, ls=":", label="WRF llanos")
    ax.set_xticks(range(0, 12, 2), MES[::2], fontsize=8)
    f_ = fase(oni_anual[y])
    ax.set_title(f"{y} · {f_} (ONI {oni_anual[y]:+.1f})", loc="left", fontsize=10, fontweight="bold",
                 color={"El Niño": C_NINO, "La Niña": C_NINA, "Neutro": INK2}[f_])
    ax.grid(axis="x", visible=False)
axes[0, 0].set_ylabel("Temperatura media (°C)")
axes[1, 0].set_ylabel("Temperatura media (°C)")
axl = axes.ravel()[-1]
axl.axis("off")
hs, ls = axes[0, 0].get_legend_handles_labels()
axl.legend(hs, ls, loc="center", frameon=False, fontsize=10)
titulo(fig, "WRF (4 km) frente a observaciones: media mensual por año",
       "WRF recuadro vs ERA5 (mismo recuadro). WRF llanos (celdas con media anual ≥ 22 °C) vs IDEAM (estaciones, T media aprox. (Tmax+Tmin)/2).")
fig.tight_layout(rect=(0, 0.03, 1, 0.94))
guardar(fig, "wrf_validacion_mensual.png")

# --- F5: mapa WRF + malla CMIP6 ---
fig, ax = plt.subplots(figsize=(9.5, 7.4))
pc = ax.pcolormesh(xlon, xlat, media_multi, cmap="RdYlBu_r", shading="auto", vmin=8, vmax=28)
cs = ax.contour(xlon, xlat, media_multi, levels=[22], colors=[INK], linewidths=1.4)
ax.add_patch(Rectangle((AREA["W"], AREA["S"]), AREA["E"] - AREA["W"], AREA["N"] - AREA["S"], fill=False, ec=INK, lw=1.8, ls="--"))
MARK = {"access_cm2": ("o", "#2a78d6"), "gfdl_esm4": ("s", "#eb6834"), "mpi_esm1_2_lr": ("^", "#1baf7a"),
        "mri_esm2_0": ("D", "#eda100"), "noresm2_mm": ("P", "#e87ba4")}
NAMES = {"access_cm2": "ACCESS-CM2", "gfdl_esm4": "GFDL-ESM4", "mpi_esm1_2_lr": "MPI-ESM1-2-LR", "mri_esm2_0": "MRI-ESM2-0", "noresm2_mm": "NorESM2-MM"}
for mod, (mk, c) in MARK.items():
    ds = xr.open_dataset(NC_DIR / f"near_surface_air_temperature_historical_{mod}_1850-2014.nc")
    lon = ((ds.lon.values + 180) % 360) - 180
    LL, LA = np.meshgrid(lon, ds.lat.values)
    ax.scatter(LL, LA, marker=mk, s=70, c=c, edgecolor="white", linewidth=1.2, label=NAMES[mod], zorder=5)
ax.scatter([-73.63], [4.14], marker="*", s=200, color=INK, edgecolor="white", zorder=6)
ax.annotate("Villavicencio", (-73.63, 4.14), xytext=(6, -12), textcoords="offset points", fontsize=8, color=INK, fontweight="bold")
cb = fig.colorbar(pc, ax=ax, fraction=0.04, pad=0.02)
cb.set_label("Temperatura media 2000-2018 (7 años WRF, °C)", color=INK2)
ax.set_xlabel("Longitud (°)")
ax.set_ylabel("Latitud (°)")
ax.grid(False)
ax.legend(frameon=True, facecolor=SURF, fontsize=8, loc="upper right", title="Celdas CMIP6", title_fontsize=8)
ax.set_title("Cordillera y llanos que los modelos globales no distinguen", loc="left", fontsize=12, fontweight="bold")
ax.text(0.01, 0.01, "Línea negra = isoterma 22 °C (límite cordillera/llanos). Recuadro punteado = zona de estudio.", transform=ax.transAxes,
        fontsize=8, color=INK, bbox=dict(boxstyle="round", fc=SURF, ec="none", alpha=0.8))
fig.tight_layout()
guardar(fig, "wrf_mapa_temperatura_y_malla_cmip6.png")

# --- F6: anual WRF vs ERA5 y ENSO ---
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
ax = axes[0]
xs = np.arange(len(anual_wrf))
ax.bar(xs - 0.2, anual_wrf.ERA5, 0.38, color="#2a78d6", label="ERA5", zorder=2)
ax.bar(xs + 0.2, anual_wrf.recuadro, 0.38, color=INK2, label="WRF recuadro", zorder=2)
ax.set_ylim(22, 25.2)
ax.set_xticks(xs, [f"{y}\n{fase(anual_wrf.ONI[y])}" for y in anual_wrf.index])
for xi, y in zip(xs, anual_wrf.index):
    col = {"El Niño": C_NINO, "La Niña": C_NINA, "Neutro": INK2}[fase(anual_wrf.ONI[y])]
    ax.get_xticklabels()[list(xs).index(xi)].set_color(col)
ax.set_ylabel("Temperatura media anual (°C)")
ax.legend(frameon=False, fontsize=9, loc="upper left")
ax.grid(axis="x", visible=False)
ax.set_title("Años simulados con WRF", loc="left", fontsize=11, fontweight="bold")
ax = axes[1]
ax.scatter(anual_wrf.ERA5, anual_wrf.recuadro, s=70, c=[{"El Niño": C_NINO, "La Niña": C_NINA, "Neutro": C_NEU}[fase(v)] for v in anual_wrf.ONI], zorder=3)
for y, r in anual_wrf.iterrows():
    ax.annotate(str(y), (r.ERA5, r.recuadro), xytext=(5, 4), textcoords="offset points", fontsize=8, color=INK2)
lo, hi = min(anual_wrf.ERA5.min(), anual_wrf.recuadro.min()) - 0.2, max(anual_wrf.ERA5.max(), anual_wrf.recuadro.max()) + 0.2
bf = np.polyfit(anual_wrf.ERA5, anual_wrf.recuadro, 1)
xx = np.linspace(anual_wrf.ERA5.min(), anual_wrf.ERA5.max(), 5)
ax.plot(xx, np.polyval(bf, xx), color=INK, lw=1.4)
ax.set_xlabel("ERA5 (°C)")
ax.set_ylabel("WRF recuadro (°C)")
ax.set_title(f"¿Reproduce el WRF las diferencias entre años? r = {anual_wrf.recuadro.corr(anual_wrf.ERA5):.2f} (n = 7)", loc="left",
             fontsize=11, fontweight="bold")
titulo(fig, "WRF frente a ERA5: temperatura media anual del recuadro",
       "Rojo = El Niño, azul = La Niña, gris = neutro (ONI medio anual ±0,5). Con 7 años la correlación es solo indicativa; parte viene de la tendencia de calentamiento compartida (2000 es el año más frío y 2016 el más cálido).")
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
guardar(fig, "wrf_anual_vs_era5_enso.png")

# --- F7: proyección por zona ---
fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
for ax, zn, nom in zip(axes, ("llanos", "recuadro", "cordillera"), ("Llanos (≥ 22 °C)", "Recuadro completo", "Cordillera (< 22 °C)")):
    sub = zp[zp.zona == zn]
    w = 0.25
    for gi, plz in enumerate(PLAZOS):
        for si, (esc, col) in enumerate(ESC):
            r = sub[(sub.escenario == esc) & (sub.plazo == plz)].iloc[0]
            x = gi + (si - 1) * (w + 0.02)
            ax.bar(x, r.media_ensamble, w, color=col, zorder=2)
            ax.plot([x, x], [r.minimo, r.maximo], color=INK2, lw=1.2, zorder=3)
            ax.text(x, r.maximo + 0.1, f"{r.media_ensamble:.1f}", ha="center", fontsize=8, color=INK, fontweight="bold")
    base_ = sub.observado_ERA5_1995_2014.iloc[0]
    ax.axhline(base_, color=INK, ls="--", lw=1.3, label=f"Base 1995-2014: {base_:.1f} °C")
    lo = sub.minimo.min()
    ax.set_ylim(lo - 1.5, sub.maximo.max() + 1.0)
    ax.set_xticks(range(3), [p.replace(" ", "\n") for p in PLAZOS])
    ax.set_title(nom, loc="left", fontsize=11, fontweight="bold")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.grid(axis="x", visible=False)
axes[0].set_ylabel("Temperatura media anual proyectada (°C)")
h = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in ESC]
fig.legend(h, [e for e, _ in ESC], frameon=False, fontsize=9, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.03))
titulo(fig, "Temperatura proyectada por zona: llanos, recuadro y cordillera (ERA5 + cambio CMIP6 + offset WRF)",
       "Supuesto: el calentamiento es el mismo en toda la zona (el WRF solo aporta la diferencia espacial). La cordillera podría calentarse algo más; no se evalúa aquí.")
fig.tight_layout(rect=(0, 0.1, 1, 0.93))
guardar(fig, "zonas_proyeccion_temperatura.png")
print("Listo.")
