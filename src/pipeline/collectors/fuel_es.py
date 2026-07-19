import gzip
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from pipeline.collectors.base import polite_get

API_URL = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes"
    "/PreciosCarburantes/EstacionesTerrestres/"
)

# our fuel code -> field name in the API response
FUELS = {
    "g95": "Precio Gasolina 95 E5",
    "g98": "Precio Gasolina 98 E5",
    "diesel": "Precio Gasoleo A",
}


def parse_price(raw: str) -> Decimal | None:
    """Spanish decimal comma to Decimal: '1,479' -> 1.479; blank -> None."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price: {raw!r}") from exc


def _coord(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    return float(raw.replace(",", "."))


def iter_products(payload: dict) -> Iterator[dict]:
    """Yield one dict per station x fuel that actually has a price."""
    for station in payload["ListaEESSPrecio"]:
        attrs = {
            "brand": station["Rótulo"],
            "province": station["Provincia"],
            "municipality": station["Municipio"],
            "address": station["Dirección"],
            "lat": _coord(station["Latitud"]),
            "lon": _coord(station["Longitud (WGS84)"]),
        }
        for fuel, field in FUELS.items():
            price = parse_price(station.get(field, ""))
            if price is None:
                continue
            yield {
                "external_id": f"{station['IDEESS']}:{fuel}",
                "title": f"{station['Rótulo']} — {station['Municipio']} ({fuel})",
                "category": fuel,
                "price_eur": price,
                "attrs": attrs,
            }


def collect(out_dir: Path, *, client: httpx.Client | None = None) -> Path:
    """One request to the API; store the response body as-is, gzipped."""
    resp = polite_get(API_URL, client=client)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "fuel_es.json.gz"
    with gzip.open(path, "wb") as f:
        f.write(resp.content)
    return path
