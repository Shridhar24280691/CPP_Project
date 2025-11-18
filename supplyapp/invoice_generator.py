# invoice_generator.py
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from supplychainlib.aws_s3 import S3Manager
from django.conf import settings

def generate_and_upload_invoice(purchase_order):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(100, 800, f"Purchase Order Invoice #{purchase_order['id']}")
    pdf.drawString(100, 780, f"Supplier: {purchase_order['supplier_name']}")
    pdf.drawString(100, 760, f"Product: {purchase_order['product_name']}")
    pdf.drawString(100, 740, f"Quantity: {purchase_order['quantity']}")
    pdf.drawString(100, 720, f"Delivery Date: {purchase_order['delivery_date']}")
    pdf.drawString(100, 700, f"Status: {purchase_order['status']}")
    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    s3 = S3Manager(settings.AWS_S3_BUCKET_NAME)
    s3_key = f"invoices/po_{purchase_order['id']}.pdf"
    s3.upload_fileobj(buffer, s3_key)
    return s3_key
