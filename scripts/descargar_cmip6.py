"""Descarga CMIP6 mensual desde CDS para el Meta (Colombia).

Escenarios: SSP1-2.6 (bajas), SSP2-4.5 (medias), SSP5-8.5 (altas) + Historical.
Variables: temperatura (tas) y precipitación (pr). Modelos: NorESM2-MM, MRI-ESM2-0, MPI-ESM1-2-LR, GFDL-ESM4, ACCESS-CM2 (EC-Earth3 falla en el CDS: RoocsValueError).
Requiere ~/.cdsapirc con el token y la licencia aceptada en el CDS.
Las combinaciones que fallan quedan en datos/fallidas.log.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cdsapi

OUT_DIR = Path(__file__).resolve().parents[1] / "datos_crudos" / "cmip6_zip"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AREA = [5.0, -74.5, 2.0, -71.0]  # N, W, S, E

MODELOS = ["noresm2_mm", "mri_esm2_0", "mpi_esm1_2_lr", "gfdl_esm4", "access_cm2"]
VARIABLES = ["near_surface_air_temperature", "precipitation"]
EXPERIMENTOS = [  # (experimento, anio_ini, anio_fin)
    ("ssp1_2_6", 2015, 2100),
    ("ssp2_4_5", 2015, 2100),
    ("ssp5_8_5", 2015, 2100),
    ("historical", 1850, 2014),
]

# Primero temperatura (todos los escenarios), luego precipitación.
DESCARGAS = [
    (exp, var, modelo, a0, a1)
    for var in VARIABLES
    for exp, a0, a1 in EXPERIMENTOS
    for modelo in MODELOS
]


def descargar(item):
    exp, var, modelo, a0, a1 = item
    destino = OUT_DIR / f"{var}_{exp}_{modelo}_{a0}-{a1}.zip"
    if destino.exists():
        print(f"Ya existe: {destino.name}", flush=True)
        return
    try:
        cdsapi.Client(quiet=True).retrieve(
            "projections-cmip6",
            {
                "temporal_resolution": "monthly",
                "experiment": exp,
                "variable": var,
                "model": modelo,
                "year": [str(y) for y in range(a0, a1 + 1)],
                "month": [f"{m:02d}" for m in range(1, 13)],
                "area": AREA,
            },
            str(destino),
        )
        print(f"OK: {destino.name}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"FALLO: {destino.name} -> {e}", flush=True)
        with open(OUT_DIR / "fallidas.log", "a", encoding="utf-8") as f:
            f.write(f"{destino.name}\t{e}\n")


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(descargar, DESCARGAS))
    print("TERMINADO", flush=True)

