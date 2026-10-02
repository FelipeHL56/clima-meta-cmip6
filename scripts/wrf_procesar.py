"""Reduce los NetCDF horarios del WRF (4 km, TK en °C) a mapas de media mensual por año.

Entrada: <WRF_NC_DIR>/WRF_TK_Meta_<año>0101_<año>1231.nc
Salida:  observaciones/wrf/wrf_tk_mensual_mapas.npz  (maps[año] = (12, ny, nx); xlat, xlon)
Los meses se calculan en hora UTC del archivo (la diferencia con hora local, 5 h, es despreciable en medias mensuales).
Los NetCDF se copian a la carpeta temporal porque netCDF4 no abre rutas con tildes.
"""
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import xarray as xr

PROY = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("WRF_NC_DIR", PROY / "datos" / "wrf_nc"))
OUT = PROY / "observaciones" / "wrf"
OUT.mkdir(parents=True, exist_ok=True)
ANIOS = [2000, 2011, 2013, 2014, 2015, 2016, 2018]

maps, xlat, xlon, nhoras = {}, None, None, {}
for y in ANIOS:
    t = Path(tempfile.gettempdir()) / f"wrf_{y}.nc"
    shutil.copy(SRC / f"WRF_TK_Meta_{y}0101_{y}1231.nc", t)
    ds = xr.open_dataset(t)
    if xlat is None:
        xlat, xlon = ds["XLAT"].values.astype("float32"), ds["XLONG"].values.astype("float32")
    g = ds["TK_C"].groupby("time.month")
    maps[y] = g.mean().values.astype("float32")
    cuenta = g.count()[:, 0, 0].values
    nhoras[y] = cuenta.tolist()
    print(y, "meses", maps[y].shape, "horas por mes", cuenta.tolist(), flush=True)
    ds.close()
    os.remove(t)

np.savez_compressed(OUT / "wrf_tk_mensual_mapas.npz", xlat=xlat, xlon=xlon, anios=np.array(ANIOS),
                    **{f"y{y}": maps[y] for y in ANIOS})
print("Guardado", OUT / "wrf_tk_mensual_mapas.npz")
