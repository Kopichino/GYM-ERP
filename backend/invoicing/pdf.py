"""Renders an invoice to PDF with reportlab.

Deliberately plain: a tax invoice is a document someone may have to produce for
an auditor, so it favours the statutory fields being unambiguous over matching
the look of the rest of the app.
"""

import io

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render_invoice(invoice):
    """Returns the PDF bytes for one invoice."""
    payment = invoice.payment
    member = payment.member
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=invoice.number,
    )
    styles = getSampleStyleSheet()
    story = []

    from branding.identity import address as gym_address, contact_line, gym_name

    story.append(Paragraph("<b>%s</b>" % gym_name(), styles["Title"]))
    for line in (gym_address(), contact_line()):
        if line:
            story.append(Paragraph(line.replace(chr(10), "<br/>"), styles["Normal"]))
    if invoice.seller_gstin:
        story.append(Paragraph("GSTIN: %s" % invoice.seller_gstin, styles["Normal"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("<b>TAX INVOICE</b>", styles["Heading2"]))

    meta = [
        ["Invoice number", invoice.number],
        ["Invoice date", invoice.issued_on.strftime("%d %b %Y")],
        ["Billed to", member.get_full_name() or member.username],
        ["Place of supply", invoice.place_of_supply or "-"],
    ]
    if invoice.buyer_gstin:
        meta.append(["Buyer GSTIN", invoice.buyer_gstin])

    meta_table = Table(meta, colWidths=[45 * mm, 110 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6 * mm))

    # Line items are assembled as a list so adding products later doesn't
    # change the layout code.
    rows = [["Description", "Period", "Amount"]]
    rows.append(
        [
            "%s membership" % payment.plan.name,
            "%s - %s" % (
                payment.period_start.strftime("%d %b %Y"),
                payment.period_end.strftime("%d %b %Y"),
            ),
            str(invoice.taxable_value),
        ]
    )

    if payment.discount_amount:
        label = (
            "Discount (%s)" % payment.discount.code
            if payment.discount
            else "Discount"
        )
        rows.append([label, "", "- %s" % payment.discount_amount])

    if invoice.igst:
        rows.append(["IGST @ %s%%" % invoice.tax_rate, "", str(invoice.igst)])
    else:
        half = invoice.tax_rate / 2
        rows.append(["CGST @ %s%%" % half, "", str(invoice.cgst)])
        rows.append(["SGST @ %s%%" % half, "", str(invoice.sgst)])

    rows.append(["", "Total", str(invoice.total)])

    table = Table(rows, colWidths=[85 * mm, 45 * mm, 25 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.7, colors.black),
                ("GRID", (0, 0), (-1, -2), 0.25, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Paid by %s on %s."
            % (payment.get_method_display(), payment.paid_date.strftime("%d %b %Y")),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "<font size=7 color='grey'>Amounts are inclusive of GST. "
            "This is a computer-generated invoice.</font>",
            styles["Normal"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
