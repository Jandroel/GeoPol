"""XLSX uses the hardened XML parser required for untrusted uploaded files."""

import io
import zipfile

import pytest
from openpyxl import Workbook

from geopol.domain.ingestion import IngestionError, inspect_file


def test_xlsx_dtd_entities_are_rejected(tmp_path):
    stream = io.BytesIO()
    workbook = Workbook()
    workbook.active.append(["UBICACION", "UBIGEO"])
    workbook.active.append(["LUGAR FICTICIO", "150101"])
    workbook.save(stream)
    workbook.close()
    stream.seek(0)
    path = tmp_path / "entity.xlsx"
    with zipfile.ZipFile(stream) as source, zipfile.ZipFile(path, "w") as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "xl/workbook.xml":
                data = b'<!DOCTYPE workbook [<!ENTITY synthetic "DISALLOWED_ENTITY">]>' + data.replace(
                    b"Sheet", b"&synthetic;"
                )
            target.writestr(entry, data)
    with pytest.raises(IngestionError, match="No se pudo abrir"):
        inspect_file(path, "entity.xlsx")
