"""Create small, fully artificial Excel files for the isolated browser test."""
import json
from pathlib import Path
import sys

from openpyxl import Workbook

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)


def save(name, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Datos"
    for row in rows:
        sheet.append(row)
    book.save(root / (name + ".xlsx"))
    book.close()


polygon = json.dumps({"type": "Polygon", "coordinates": [[[-78, -13], [-76, -13], [-76, -11], [-78, -11], [-78, -13]]]})
line = json.dumps({"type": "LineString", "coordinates": [[-77.02, -12.04], [-77.021, -12.041]]})
save("pnp", [
    ["complaint_id", "location_original", "ubigeo", "street_type", "street_name", "door_number", "block_number", "extra_sintetico", "center_name", "district"],
    ["QA-PUERTA", "CALLE DEMOSTRACION 120", "150101", "CALLE", "DEMOSTRACION", "120", None, "A", None, None],
    ["QA-PUERTA", "CALLE DEMOSTRACION 120", "150101", "CALLE", "DEMOSTRACION", "120", None, "B", None, None],
    ["QA-ERRATA", "CALLE DEMOSTRACON 120", "150101", "CALLE", "DEMOSTRACON", "120", None, "C", None, None],
    ["QA-CUADRA", "CALLE SEGUNDA CUADRA 2", "150101", "CALLE", "SEGUNDA", None, "2", "D", None, None],
    ["QA-INCOMPLETA", "UBICACION SIN DATOS", "150101", None, None, None, None, "E", None, None],
    ["QA-NUCLEO", "CENTRO SINTETICO DISTRITO SINTETICO", "150101", None, None, None, None, "F", "CENTRO SINTETICO", "DISTRITO SINTETICO"],
])
save("doors", [["id", "ubigeo", "street_type", "street_name", "door_number", "latitude", "longitude"],
               ["D1", "150101", "CALLE", "DEMOSTRACION", "120", -12.04, -77.03]])
save("roads", [["id", "ubigeo", "kind", "street_type", "street_name", "block_number", "geometry"],
               ["B1", "150101", "block", "CALLE", "SEGUNDA", "2", line]])
save("centers", [["id", "ubigeo", "name", "latitude", "longitude"],
                 ["C1", "150101", "CENTRO SINTETICO", -12.042, -77.028]])
save("boundaries", [["id", "ubigeo", "name", "level", "geometry"],
                    ["L1", "150101", "DISTRITO SINTETICO", "district", polygon]])
save("jurisdictions", [["id", "ubigeo", "name", "geometry"],
                       ["J1", "150101", "COMISARIA SINTETICA", polygon]])
