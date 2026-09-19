"""Piccolo helper generico per generare un export .xlsx in memoria (nessun
file temporaneo su disco), usato dai bottoni "Esporta Excel" del modulo
Statistiche - sia quelli dell'amministratore (app/api/v1/statistics.py) sia
quelli del promoter nel suo portale (app/api/v1/portal_statistics.py). Vedi
docs/STATISTICS.md."""
import io
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.services.statistics_service import ALL_METRIC_COLUMNS

# Intestazioni delle colonne metriche, nell'ordine di ALL_METRIC_COLUMNS: le
# stesse per ogni export del modulo, admin o portale. Definite qui e non nel
# router perche' due router le usano - se vivessero in uno dei due, l'altro
# importerebbe da un modulo API o (peggio) se ne terrebbe una copia destinata a
# divergere al primo tipo di metrica nuovo.
METRIC_COLUMN_LABELS: dict[str, str] = {
    "reactions": "Reazioni",
    "likes": "Mi piace",
    "views": "Visualizzazioni",
    "impressions": "Impression",
    "reach": "Copertura",
    "follows": "Nuovi iscritti",
    "clicks": "Clic",
    "comments": "Commenti",
    "shares": "Condivisioni",
    "engagement_rate": "Tasso di coinvolgimento (%)",
}
METRIC_HEADERS: list[str] = [METRIC_COLUMN_LABELS[c] for c in ALL_METRIC_COLUMNS]


def metric_values(totals: dict[str, Any]) -> list[Any]:
    """I valori delle metriche nello stesso ordine di METRIC_HEADERS."""
    return [totals.get(c) for c in ALL_METRIC_COLUMNS]


def xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_xlsx(sheet_title: str, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # limite Excel sul nome del foglio

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            # Excel/openpyxl non accetta datetime timezone-aware
            if isinstance(value, datetime) and value.tzinfo is not None:
                value = value.replace(tzinfo=None)
            ws.cell(row=row_idx, column=col_idx, value=value)

    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
