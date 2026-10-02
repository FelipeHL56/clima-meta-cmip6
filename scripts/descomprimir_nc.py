"""Descomprime los zip del CDS y deja un NetCDF por archivo en datos/nc (nombre = nombre del zip)."""
import zipfile
from pathlib import Path

PROY = Path(__file__).resolve().parents[1]
ZIPS = PROY / "datos_crudos" / "cmip6_zip"
OUT = PROY / "datos" / "nc"
OUT.mkdir(parents=True, exist_ok=True)
for z in sorted(ZIPS.glob("*.zip")):
    with zipfile.ZipFile(z) as zf:
        ncs = [n for n in zf.namelist() if n.endswith(".nc")]
        assert len(ncs) == 1, f"{z.name}: se esperaba 1 .nc y hay {len(ncs)}"
        (OUT / f"{z.stem}.nc").write_bytes(zf.read(ncs[0]))
        print("OK", z.stem)
