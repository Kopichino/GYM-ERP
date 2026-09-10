import json

import openpyxl
from django.http import HttpResponse
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin

from .mapping import BILLING, FIELDS, MEMBER, REQUIRED, TRAINER, detect_columns
from .services import ImportError_, build_rows, commit_rows, parse_file

KINDS = (MEMBER, BILLING, TRAINER)
PREVIEW_LIMIT = 25


def _prepare(request):
    """Shared front half of preview and commit: validate the kind, parse the
    file, and settle on a column mapping (an explicit one from the UI beats
    detection)."""
    kind = request.data.get("kind", MEMBER)
    if kind not in KINDS:
        raise ImportError_(f"Unknown import type '{kind}'. Expected one of: {', '.join(KINDS)}.")

    uploaded = request.FILES.get("file")
    if not uploaded:
        raise ImportError_("No file uploaded.")

    headers, rows = parse_file(uploaded)
    override = request.data.get("mapping")
    if override:
        mapping = {k: v for k, v in json.loads(override).items() if v}
    else:
        mapping = detect_columns(headers, kind)
    return kind, headers, build_rows(rows, mapping, kind), mapping


class ImportPreviewView(APIView):
    """Parses an uploaded file and reports what *would* happen. Writes nothing.

    The response carries the detected column mapping so the admin can correct
    it before committing -- necessary because most gym platforms don't publish
    their export headers, so detection is a best guess, not a guarantee."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        try:
            kind, headers, built, mapping = _prepare(request)
        except ImportError_ as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "kind": kind,
                "headers": headers,
                "mapping": mapping,
                "available_fields": list(FIELDS[kind]),
                "required_fields": REQUIRED[kind],
                "total_rows": len(built),
                "create_count": sum(1 for r in built if r["action"] == "create" and not r["errors"]),
                "update_count": sum(1 for r in built if r["action"] == "update" and not r["errors"]),
                "error_count": sum(1 for r in built if r["errors"]),
                "rows": built[:PREVIEW_LIMIT],
                "truncated": len(built) > PREVIEW_LIMIT,
            }
        )


class ImportCommitView(APIView):
    """Re-parses the same file with a confirmed mapping and writes the rows."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        try:
            kind, _headers, built, _mapping = _prepare(request)
            result = commit_rows(built, kind, actor=request.user)
        except ImportError_ as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(result)


class ImportTemplateView(APIView):
    """Blank .xlsx with the canonical headers, for admins who'd rather start
    from our format than map a vendor export."""

    permission_classes = [IsAdmin]

    def get(self, request, kind=MEMBER, *args, **kwargs):
        if kind not in KINDS:
            return Response({"detail": f"Unknown import type '{kind}'."}, status=400)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = kind.title()
        sheet.append([f.replace("_", " ").title() for f in FIELDS[kind]])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f"attachment; filename=ironcore_{kind}_template.xlsx"
        workbook.save(response)
        return response
