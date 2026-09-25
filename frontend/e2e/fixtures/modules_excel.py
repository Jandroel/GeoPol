"""Small synthetic SIDPOL workbook for the five-module browser flow."""

from pathlib import Path
import sys

from openpyxl import Workbook

directory = Path(sys.argv[1]).resolve()
directory.mkdir(parents=True, exist_ok=True)
book = Workbook()
sheet = book.active
sheet.title = "Datos"
sheet.append([
    "complaint_id", "location_original", "ubigeo", "street_type",
    "street_name", "door_number", "district", "FLAG", "extra_sintetico",
])
for row in [
    ["QA-MOD-EXACTA", "CALLE DEMOSTRACION 120", "150101", "CALLE", "DEMOSTRACION", "120", "DISTRITO SINTETICO", 1, "A"],
    ["QA-MOD-EXACTA", "CALLE DEMOSTRACION 120", "150101", "CALLE", "DEMOSTRACION", "120", "DISTRITO SINTETICO", 1, "B"],
    ["QA-MOD-ORIGEN10", "CALLE DEMOSTRACION 120", "150101", "CALLE", "DEMOSTRACION", "120", "DISTRITO SINTETICO", 10, "C"],
    ["QA-MOD-AUTO10", None, None, None, None, None, None, None, "D"],
    ["QA-MOD-SINMATCH", "LUGAR SINTETICO SIN REFERENCIA", "150101", None, None, None, "DISTRITO SINTETICO", None, "E"],
    ["QA-MOD-ERRATA", "CALLE DEMOSTRACON 120", "150101", "CALLE", "DEMOSTRACON", "120", "DISTRITO SINTETICO", 1, "F"],
]:
    sheet.append(row)
book.save(directory / "DATACRIM_25092026.xlsx")
book.close()
