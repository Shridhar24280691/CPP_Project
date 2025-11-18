from decimal import Decimal
import uuid, boto3
from uuid import uuid4
from datetime import datetime
from django.utils import timezone
from collections import defaultdict
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from .models import PurchaseOrderHistory, DistributorOrderHistory, CustomerOrderHistory
from .services import CognitoService
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now
import os, boto3
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.timezone import now

from supplychainlib.aws_lambda import LambdaInvoker
from supplychainlib.aws_s3 import S3Manager
from supplychainlib.aws_sns import SNSManager

from supplychainlib.aws_dynamodb import (
    DynamoDBManager,
    SupplierManager,
    RawMaterialManager,
    FinishedProductManager,
    PurchaseOrderManager,
    DistributorOrderManager,
    DistributorInventoryManager,
    DistributorManager, CustomerOrderManager
)
from supplychainlib.utility import InventoryUtility
from .services import (
    SupplierService,
    RawMaterialService,
    PurchaseOrderService,PurchaseOrderHistoryService,
    FinishedProductService,
    DistributorOrderService, DistributorOrderHistoryService, CustomerOrderHistoryService
)

# -------------------------------------------------------------------
# Service wiring
# -------------------------------------------------------------------

supplier_service = SupplierService(SupplierManager())
raw_service = RawMaterialService(RawMaterialManager())
po_service = PurchaseOrderService(PurchaseOrderManager(), raw_service)
fp_service = FinishedProductService(FinishedProductManager(), raw_service)
dist_order_service = DistributorOrderService(
    DistributorOrderManager(),
    DistributorInventoryManager(),
    FinishedProductManager(),
)

FINISHED_PRODUCT_PRICES = {
            "Espresso Blend": 30.0,
            "Roasted Beans": 25.0,
            }
# -------------------------------------------------------------------
# Home / Dashboard
# -------------------------------------------------------------------



class DashboardView(View):
    def get(self, request):

        suppliers = supplier_service.list_active()
        raw_items = raw_service.manager.scan()
        finished_items = fp_service.manager.scan()
        purchase_orders = PurchaseOrderHistory.objects.all()

        distributor_manager = DistributorManager()
        distributors = distributor_manager.scan()
        distributor_count = len(distributors)

        # FIX — replace broken service call with ORM
        distributor_orders = DistributorOrderHistory.objects.all()
        distributor_order_count = distributor_orders.count()

        # FIX — customer orders counted from ORM
        customer_order_count = CustomerOrderHistory.objects.count()

        context = {
            "supplier_count": len(suppliers),
            "po_count": purchase_orders.count(),
            "inventory_count": sum(int(i.get("quantity", 0)) for i in raw_items),
            "finished_count": sum(int(i.get("quantity", 0)) for i in finished_items),
            "order_count": distributor_order_count,
            "distributor_count": distributor_count,
            "customer_order_count": customer_order_count,
        }

        return render(request, "supplyapp/dashboard.html", context)


# -------------------------------------------------------------------
# Suppliers
# -------------------------------------------------------------------

class SupplierBase(View):
    table_name = "Suppliers"

    def get_table(self):
        return DynamoDBManager(self.table_name)


class SupplierListView(SupplierBase):
    def get(self, request):
        table = self.get_table()
        suppliers = table.scan_table()
        return render(request, "supplyapp/supplier_list.html", {"suppliers": suppliers})


class SupplierManagerView(SupplierBase):
    """Add, edit, or delete suppliers."""

    def get(self, request, supplier_id=None):
        table = self.get_table()
        action = request.GET.get("action", "add")

        supplier_id = supplier_id or request.GET.get("id")
        supplier = table.get_item({"id": supplier_id}) if supplier_id else None

        return render(
            request,
            "supplyapp/supplier_manage.html",
            {"supplier": supplier, "action": action},
        )
    def post(self, request, supplier_id=None):
        table = self.get_table()
        action = (request.POST.get("action") or "").lower()

        if action in ["add", "edit"]:
            sup_id = request.POST.get("supplier_id") or supplier_id
            if not sup_id and action == "add":
                sup_id = str(uuid.uuid4())

            item = {
                "id": sup_id,
                "name": request.POST.get("name"),
                "product": request.POST.get("product"),
                "price_per_unit": Decimal(str(request.POST.get("price_per_unit") or 0)),
                "origin": request.POST.get("origin"),
                "active": True,
            }

            table.put_item(item)
            messages.success(
                request,
                f"Supplier {'added' if action == 'add' else 'updated'} successfully.",
            )
            return redirect("supplier_list")

        if action == "delete":
            try:
                sup_id = request.POST.get("supplier_id") or supplier_id
                if not sup_id:
                    messages.error(request, "Missing supplier ID.")
                    return redirect("supplier_list")

                key = {"id": str(sup_id).strip()}
                table.delete_item(key)
                messages.success(request, "Supplier deleted successfully.")
            except Exception as exc:
                messages.error(request, f"Error deleting supplier: {exc}")
            return redirect("supplier_list")

        messages.error(request, "Invalid action.")
        return redirect("supplier_list")

# -------------------------------------------------------------------
# Raw materials (AJAX)
# -------------------------------------------------------------------

class RawMaterialBySupplierView(View):
    """Return supplier product info as raw material options."""

    def get(self, request, supplier_id):
        try:
            table = DynamoDBManager("Suppliers")
            all_suppliers = table.scan_table()

            selected_supplier = next(
                (s for s in all_suppliers if s.get("id") == supplier_id), None
            )

            if not selected_supplier:
                return JsonResponse({"raw_materials": []})

            material = {
                "id": selected_supplier.get("id"),
                "name": selected_supplier.get("product", "Unnamed Material"),
                "origin": selected_supplier.get("origin", ""),
                "cost_per_pound": float(selected_supplier.get("price_per_unit", 0)),
                "supplier_id": selected_supplier.get("id"),
            }

            return JsonResponse({"raw_materials": [material]})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

# -------------------------------------------------------------------
# Purchase orders
# -------------------------------------------------------------------
class PurchaseOrderFormView(View):
    def get(self, request):
        suppliers = supplier_service.list_active()
        return render(
            request,
            "supplyapp/purchase_order_form.html",
            {"suppliers": suppliers},
        )

    def post(self, request):
        supplier_id = request.POST.get("supplier")
        material_id = request.POST.get("raw_material")
        quantity = int(request.POST.get("quantity") or 0)
        delivery_date = request.POST.get("delivery_date")

        try:
            po_service.create(supplier_id, material_id, quantity, delivery_date)
            messages.success(request, "Purchase order created.")

            # Trigger Lambda
            purchase_order = {
                "supplier_id": supplier_id,
                "material_id": material_id,
                "quantity": quantity,
                "delivery_date": delivery_date
            }
            invoker = LambdaInvoker(region_name="us-east-1")
            lambda_response = invoker.invoke_function('GenerateInvoiceLambda', purchase_order)
        except Exception as exc:
            messages.error(request, str(exc))

        return redirect("purchase_order_history")



class PurchaseOrderHistoryView(View):
    def get(self, request):
        orders = PurchaseOrderHistoryService().list_all()
        supplier_service = SupplierService(SupplierManager())
        suppliers = {s["id"]: s.get("name", "") for s in supplier_service.list_active()}
        raw_service = RawMaterialService(RawMaterialManager())
        raw_materials = {r["id"]: r.get("name", "") for r in raw_service.manager.scan()}  # <-- Corrected

        for o in orders:
            o.supplier_name = suppliers.get(o.supplier_id, "—")
            o.raw_material_name = getattr(o, "raw_material_name", None) or raw_materials.get(o.raw_material_id, "—")

        return render(request, "supplyapp/purchase_order_history.html", {"orders": orders})

class PO_StatusView(View):
    def post(self, request, po_id):
        """Update purchase order status and update inventory if delivered."""
        new_status = request.POST.get("status")
        try:
            # Use ORM to get the order
            po = PurchaseOrderHistory.objects.get(order_id=po_id)
        except PurchaseOrderHistory.DoesNotExist:
            messages.error(request, "Purchase order not found.")
            return redirect("purchase_order_history")

        # Update order status in ORM
        po.status = new_status
        po.save()

        # If delivered, update raw material stock (if needed)
        if new_status == "Delivered":
            raw_material_id = po.raw_material  # your models field, should match manager id
            quantity = int(po.quantity)
            raw_service.changequantity(raw_material_id, quantity)
            messages.success(request, f"Order {po_id} marked as Delivered. Inventory updated in DynamoDB.")

        else:
            messages.success(request, f"Purchase order status updated to {new_status}.")

        return redirect("purchase_order_history")

# -------------------------------------------------------------------
# Inventory / finished products
# -------------------------------------------------------------------
def list_invoices_s3():
    # List all invoice files in the S3 bucket under the "inventory/" prefix.
    s3 = boto3.client('s3')
    bucket = settings.AWS_S3_BUCKET_NAME
    prefix = "inventory/"
    files = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    result = []
    for obj in files.get('Contents', []):
        key = obj['Key']
        if key != prefix:  # Avoid directory entry
            result.append({
                'name': key.split('/')[-1],  # just filename, for display
                'key': key,                  # full S3 object key, for download/delete
                'url': f"https://{bucket}.s3.amazonaws.com/{key}"
            })
    return result 

class InventoryDashboardView(View):
    def get(self, request):
        raw_items_full = raw_service.manager.scan()
        finished_items = fp_service.manager.scan()

        # Raw Materials: Only show delivered in-stock (quantity > 0)
        raw_items = [i for i in raw_items_full if int(i.get("quantity", 0)) > 0]
        low_stock = [
            i for i in raw_items_full
            if int(i.get("quantity", 0)) == 0 and i.get("delivered", True)
        ]

        raw_total = sum(int(i.get("quantity", 0)) for i in raw_items)
        finished_total = sum(int(i.get("quantity", 0)) for i in finished_items)

        invoices = []
        try:
            files = s3.list_objects("invoices/purchase_orders/")
            for f in files:
                invoices.append({
                    "name": f.split("/")[-1],
                    "url": f"https://{s3.bucket_name}.s3.amazonaws.com/{f}"
                })
        except Exception as e:
            print(f"S3 list error: {e}")

        context = {
            "raw_total": raw_total,
            "finished_total": finished_total,
            "low_stock_items": low_stock,
            "raw_items": raw_items,
            "invoices": invoices,
        }
        context["invoices"] = list_invoices_s3()
        return render(request, "supplyapp/inventory_dashboard.html", context)

class ConvertRawToFinishedView(View):
    def post(self, request, material_id):
        try:
            valid_blends = ["Roasted Beans", "Espresso Blend"]
            blend_name = request.POST.get("blend_name")  # NEW: get selected product
            if blend_name not in valid_blends:
                messages.error(request, "Invalid blend selected.")
                return redirect("inventory_dashboard")
            material = next(
                (m for m in raw_service.manager.scan() if m.get("id") == material_id),
                None
            )

            if not material:
                messages.error(request, "Raw material not found.")
                return redirect("inventory_dashboard")

            quantity = int(material.get("quantity", 0))
            if quantity < 4:
                messages.warning(request, "At least 4 units of raw material required to convert (4 raw = 1 finished).")
                return redirect("inventory_dashboard")

            finished_units = quantity // 4
            remaining_raw = quantity % 4

            # Update the raw material quantity
            raw_service.manager.update_item(
                key={"id": material_id},
                update_expr="SET quantity = :q",
                values={":q": remaining_raw}
            )

            unit_price = FINISHED_PRODUCT_PRICES.get(blend_name, 0.0)
            finished_items = fp_service.manager.scan()
            match = next((fp for fp in finished_items if fp.get("blend_name") == blend_name), None)
            finished_key = "finished_id"

            if match:
                existing_qty = int(match.get("quantity", 0))
                fp_service.manager.update_item(
                    key={finished_key: match[finished_key]},
                    update_expr="SET quantity = :q",
                    values={":q": existing_qty + finished_units}
                )
            else:
                new_finished = {
                    finished_key: str(uuid.uuid4()),
                    "blend_name": blend_name,
                    "quantity": finished_units,
                    "unit_price": unit_price,
                }
                fp_service.manager.put_item(new_finished)

            messages.success(request, f"Converted {finished_units * 4} raw units to {finished_units} {blend_name}(s).")
        except Exception as e:
            messages.error(request, f"Conversion failed: {e}")

        return redirect("inventory_dashboard")

   
class UploadInventoryFileView(View):
    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            messages.error(request, "Please select a file to upload.")
            return redirect("inventory_dashboard")

        temp_path = default_storage.save(file_obj.name, file_obj)
        temp_file_path = os.path.join(settings.MEDIA_ROOT, temp_path)

        timestamp = now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"inventory/{timestamp}_{file_obj.name}"

        try:
            s3 = S3Manager(settings.AWS_S3_BUCKET_NAME)
            s3.upload_file(temp_file_path, s3_key)
            messages.success(request, "Inventory file uploaded successfully.")
        except Exception as exc:
            messages.error(request, f"Error uploading file: {exc}")

        default_storage.delete(temp_path)

        return redirect("inventory_dashboard")

class DeleteInvoiceView(View):
    def post(self, request):
        # Retrieve the full S3 key from the POST request
        file_key = request.POST.get('file_key')
        if not file_key:
            messages.error(request, "No invoice file specified for deletion.")
            return redirect("inventory_dashboard")
        try:
            s3 = S3Manager(settings.AWS_S3_BUCKET_NAME)
            s3.delete_file(file_key)  # This expects the full S3 key, not just the filename
            messages.success(request, "Invoice file deleted.")
        except Exception as exc:
            messages.error(request, f"Error deleting file: {exc}")
        return redirect("inventory_dashboard")

# -------------------------------------------------------------------
# Distributor orders
# -------------------------------------------------------------------

class DistributorListView(View):
    def get(self, request):
        manager = DistributorManager()
        distributors = [d for d in manager.scan() if d.get("active", True)]
        return render(request, "supplyapp/distributor_list.html", {"distributors": distributors})

class DistributorManageView(View):
    def get(self, request, distributor_id=None):
        manager = DistributorManager()
        distributor = manager.get_item({"id": distributor_id}) if distributor_id else None
        return render(request, "supplyapp/distributor_manage.html", {"distributor": distributor})

    def post(self, request, distributor_id=None):
        manager = DistributorManager()
        action = request.POST.get("action", "add").lower()
        name = request.POST.get("name", "").strip()
        region = request.POST.get("region", "").strip()
        contact = request.POST.get("contact", "").strip()
        active = request.POST.get("active", "on") == "on"

        # Handle deletion
        if action == "delete" and distributor_id:
            manager.delete_item({"id": distributor_id})
            messages.success(request, "Distributor deleted successfully.")
            return redirect("distributor_list")

        # Required field validation
        if not name or not region or not contact:
            messages.error(request, "Name, region, and contact are required.")
            distributor = manager.get_item({"id": distributor_id}) if distributor_id else None
            return render(request, "supplyapp/distributor_manage.html", {"distributor": distributor})

        # Prevent duplicate entries only for add (not for edit)
        if not distributor_id:
            all_distributors = manager.scan()
            duplicate = any(
                d.get("name", "").strip().lower() == name.lower()
                for d in all_distributors
            )
            if duplicate:
                messages.error(request, "Distributor name already exists.")
                return render(request, "supplyapp/distributor_manage.html", {"distributor": None})

        dist_id = distributor_id or str(uuid4())
        item = {
            "id": dist_id,
            "name": name,
            "region": region,
            "contact": contact,
            "active": active,
        }
        manager.put_item(item)
        messages.success(request, f"Distributor {'added' if not distributor_id else 'updated'} successfully.")
        return redirect("distributor_list")
class DistributorOrderFormView(View):
    def get(self, request):
        manager = DistributorManager()
        distributors = [d for d in manager.scan() if d.get("active")]
        finished_manager = FinishedProductManager()
        finished_products = []
        for fp in finished_manager.scan():
            if int(fp.get("quantity", 0)) > 0:
                price = FINISHED_PRODUCT_PRICES.get(fp.get("blend_name"), 0)
                finished_products.append({
                    "id": fp.get("finished_id"),
                    "blend_name": fp.get("blend_name"),
                    "unit_price": price,
                })

        return render(
            request,
            "supplyapp/distributor_order_form.html",
            {
                "distributors": distributors,
                "finished_products": finished_products,
            }
        )

    def post(self, request):
        distributor_id = request.POST.get("distributor")
        product_id = request.POST.get("finished_product")
        quantity = int(request.POST.get("quantity") or 0)
        delivery_date = request.POST.get("delivery_date")
        order_date = datetime.strptime(delivery_date, "%Y-%m-%d").date() if delivery_date else now().date()
        status = "Processing"
    
        DistributorOrderHistory.objects.create(
            order_id=str(uuid.uuid4()),
            distributor_id=distributor_id,
            product_id=product_id,
            quantity=quantity,
            status=status,
            order_date=order_date
        )
        messages.success(request, "Distributor order created.")
        return redirect("distributor_order_history")

class ChangeDistributorOrderStatusView(View):
    def post(self, request, order_id):
        new_status = request.POST.get("status")
        try:
            order = DistributorOrderHistory.objects.get(order_id=order_id)
            order.status = new_status
            order.save()

            if new_status == "Delivered":
                distributor_id = order.distributor_id
                product_id = order.product_id
                quantity = int(order.quantity)

                # Update distributor inventory in DynamoDB
                distributor_inventory = DistributorInventoryManager()
                # ---- Robust logic: add or update stock correctly ----
                inv_id = f"{distributor_id}#{product_id}"  # Use as single PK
                key = {"id": inv_id}
                existing = distributor_inventory.get_item(key)
                if existing and existing.get("quantity") is not None:
                    new_qty = int(existing["quantity"]) + quantity
                    distributor_inventory.update_item(
                        key=key,
                        update_expr="SET quantity = :q",
                        values={":q": new_qty}
                    )
                else:
                    distributor_inventory.put_item({ "id": inv_id,
                        "distributor_id": distributor_id,
                        "product_id": product_id,
                        "quantity": quantity
                    })

                # Decrement finished product central stock
                finished_manager = FinishedProductManager()
                product = finished_manager.get_item({"finished_id": product_id})
                if product:
                    current_qty = int(product.get("quantity", 0))
                    updated_qty = max(0, current_qty - quantity)
                    finished_manager.update_item(
                        key={"finished_id": product_id},
                        update_expr="SET quantity = :q",
                        values={":q": updated_qty}
                    )
                messages.success(request, f"Order {order_id} marked as Delivered. Inventory updated.")
            else:
                messages.success(request, f"Order {order_id} status updated to {new_status}.")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")
        return redirect("distributor_order_history")


class DistributorOrderHistoryView(View):
    def get(self, request):
        orders = DistributorOrderHistoryService().list_all()
        manager = DistributorManager()
        distributors = {d["id"]: d.get("name", "") for d in manager.scan()}
        products = {p.get("finished_id"): p.get("blend_name", "") for p in FinishedProductManager().scan()}

        for o in orders:
            o.distributor_name = distributors.get(o.distributor_id, "—")
            o.product_name = products.get(o.product_id, "—")

        return render(request, "supplyapp/distributor_order_history.html", {"orders": orders})

class DistributorInventoryView(View):
    def get(self, request):
        distributors = DistributorManager().scan()
        all_distributors = {d["id"]: d.get("name", "") for d in distributors}
        finished_products = FinishedProductManager().scan()
        products = {p.get("finished_id"): p.get("blend_name", "") for p in finished_products}

        inventory_records = DistributorInventoryManager().scan()
        stock_table = self.aggregate_inventory(inventory_records)

        table = []
        for (dist_id, prod_id), quantity in stock_table.items():
            if quantity > 0:
                table.append({
                    "distributor_name": all_distributors.get(dist_id, dist_id),
                    "product_name": products.get(prod_id, prod_id),
                    "quantity": quantity,
                })
        return render(request, "supplyapp/distributor_inventory.html", {"table": table})

    @staticmethod
    def aggregate_inventory(records):
        stock_table = defaultdict(int)

        for record in records:
            dist_id = record.get("distributor_id")
            prod_id = record.get("product_id")

            # Fallback for composite id "distributor#product"
            if not dist_id or not prod_id:
                inv_id = record.get("id", "")
                parts = inv_id.split("#")
                if len(parts) == 2:
                    dist_id, prod_id = parts

            if not dist_id or not prod_id:
                continue

            qty = int(record.get("quantity", 0))
            if qty > 0:
                stock_table[(dist_id, prod_id)] += qty

        return stock_table


class CustomerOrderFormView(View):
    def get(self, request):
        distributors = [d for d in DistributorManager().scan() if d.get("active")]
        selected_dist_id = request.GET.get("distributor") or ""
        user_email = request.session.get("user_email", "")
        customer_name = request.GET.get("customer_name", "")
        quantity = request.GET.get("quantity", "")
        address = request.GET.get("address", "")

        finished_products = []

        if selected_dist_id:
            inventory_records = DistributorInventoryManager().scan()

            product_stock = {}
            for inv in inventory_records:
                dist_id = inv.get("distributor_id")
                prod_id = inv.get("product_id")

                # Fallback for composite primary key in "id"
                if not dist_id or not prod_id:
                    inv_id = inv.get("id", "")
                    parts = inv_id.split("#")
                    if len(parts) == 2:
                        dist_id, prod_id = parts

                if not dist_id or not prod_id:
                    continue

                qty = int(inv.get("quantity", 0))
                if dist_id == selected_dist_id and qty > 0:
                    product_stock[prod_id] = product_stock.get(prod_id, 0) + qty

            all_products = FinishedProductManager().scan()
            for p in all_products:
                prod_id = p.get("finished_id")
                if prod_id in product_stock:
                    finished_products.append({
                        "finished_id": prod_id,
                        "blend_name": p.get("blend_name"),
                        "unit_price": float(p.get("unit_price", 0)),
                        "quantity": product_stock[prod_id],
                    })

        context = {
            "distributors": distributors,
            "selected_dist_id": selected_dist_id,
            "customer_name": user_email,
            "quantity": quantity,
            "address": address,
            "finished_products": finished_products,
        }
        return render(request, "supplyapp/customer_order_form.html", context)

    def post(self, request):
        # Fetch form data
        customer_name = request.POST.get("customer_name", "")
        distributor_id = request.POST.get("distributor", "")
        product_id = request.POST.get("finished_product", "")
        quantity = request.POST.get("quantity", "")
        address = request.POST.get("address", "")

        if not customer_name:
            customer_name = request.session.get("user_email", "")
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 0
        
        distributor_name = ""
        for d in DistributorManager().scan():
            if d.get("id") == distributor_id:
                distributor_name = d.get("name", "")
                break

        product_name = ""
        for p in FinishedProductManager().scan():
            if p.get("finished_id") == product_id:
                product_name = p.get("blend_name", "")
                break

        # Simple validation
        if not (customer_name and distributor_name and product_name and quantity > 0 and address):
            messages.error(request, "All fields are required and quantity must be greater than zero.")
            return redirect("customer_order_form")

        # Save order to history
        order = CustomerOrderHistory.objects.create(
            order_id=str(uuid.uuid4()),
            customer_name=customer_name,
            distributor_id=distributor_id,
            distributor_name=distributor_name,
            product_id=product_id,
            product_name=product_name,            
            quantity=quantity,
            address=address,
            status="Processing",
            tracking_link="",
            order_date=timezone.now().date()
        )

        messages.success(request, "Customer order placed successfully.")
        return redirect("customer_order_form")


class ProductDetailsAjaxView(View):
    def get(self, request):
        product_id = request.GET.get("product_id")

        product = FinishedProductManager().get_item({"finished_id": product_id})
        if not product:
            return JsonResponse({"error": "Not found"}, status=404)

        # FIX: return correct stock for THIS distributor
        distributor_id = request.GET.get("distributor_id")

        stock = 0
        inventory_items = DistributorInventoryManager().scan()
        for inv in inventory_items:
            if inv.get("distributor_id") == distributor_id and inv.get("product_id") == product_id:
                stock = int(inv.get("quantity", 0))

        return JsonResponse({
            "unit_price": float(product.get("unit_price", 0)),
            "stock": stock,
        })
        
class CustomerOrderDetailsView(View):
    def get(self, request):
        email = request.session.get("user_email")

        if not email:
            return redirect("login")

        # Fetch ALL orders placed by this user
        orders = CustomerOrderHistory.objects.filter(
            customer_name=email
        ).order_by("-order_date")

        return render(request, "supplyapp/customer_order_details.html", {"orders": orders})

class CustomerOrderHistoryView(View):
    def get(self, request):
        orders = CustomerOrderHistoryService().list_all()
        distributors = {d["id"]: d.get("name", "") for d in DistributorManager().scan()}
        products = {p.get("finished_id"): p.get("blend_name", "") for p in FinishedProductManager().scan()}

        for o in orders:
            o.distributor_name = distributors.get(getattr(o, "distributor_id", ""), o.distributor_name or "-")
            o.product_name = products.get(getattr(o, "product_id", ""), o.product_name or "-")

        return render(request, "supplyapp/customer_order_history.html", {"orders": orders})


class ShipmentTrackingView(View):
    def get(self, request, shipment_id):
        # Retrieve order by shipment_id (assuming order_id)
        order = get_object_or_404(CustomerOrderHistory, order_id=shipment_id)
        return render(request, 'supplyapp/shipment_tracking.html', {'order': order})

    def post(self, request, shipment_id):
        order = get_object_or_404(CustomerOrderHistory, order_id=shipment_id)

        new_status = request.POST.get('status')
        tracking_no = request.POST.get('tracking_no')

        # Update order details
        order.tracking_link = tracking_no
        order.update_status_and_inventory(new_status)

        # Send customer notification using SNSManager
        sns = SNSManager(topic_arn=settings.AWS_SNS_TOPIC_ARN)

        message = (
            f"Order Update:\n"
            f"Order ID: {order.order_id}\n"
            f"Status: {new_status}\n"
            f"Product: {order.product_name}\n"
            f"Quantity: {order.quantity}\n"
            f"Distributor: {order.distributor_name}\n"
            f"Tracking No: {tracking_no or 'Not Assigned'}\n"
        )

        sns.publish_message(
            subject="Order Status Update",
            message=message
        )

        messages.success(request, "Shipment updated and customer notified.")
        return redirect("customer_order_history")



class ChangeCustomerOrderStatusView(View):
    def post(self, request, order_id):
        new_status = request.POST.get("status")
        order = get_object_or_404(CustomerOrderHistory, order_id=order_id)
        order.update_status_and_inventory(new_status)
        return redirect("customer_order_history")
        
        sns = SNSManager(topic_arn=settings.AWS_SNS_TOPIC_ARN)

        sns.publish_message(
            subject="Order Update",
            message=f"Your order {self.order_id} status changed to {new_status}.",
            message_attributes={
                "customer_email": {
                    "DataType": "String",
                    "StringValue": self.customer_name
                }
            }
        )


class CognitoUserAuth:
    """Shared Cognito service instance for auth views."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cognito = CognitoService()


class SignupView(CognitoUserAuth, View):
    template_name = "supplyapp/signup.html"

    def get(self, request):
        # Render signup page
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        # Basic validation
        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, self.template_name)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, self.template_name)

        # Check if user already exists in Cognito
        if self.cognito.user_exists(email):
            messages.error(request, "Account already exists. Please log in.")
            return redirect("login")

        # Sign up user in Cognito
        signup_result = self.cognito.sign_up(email, password)
        print("DEBUG SIGNUP RESULT:", signup_result)
        if "error" in signup_result:
            messages.error(request, signup_result["error"])
            return render(request, self.template_name)

        # Auto-confirm the user and mark email as verified
        confirm_result = self.cognito.auto_confirm_user(email)
        if "error" in confirm_result:
            messages.error(request, confirm_result["error"])
            return render(request, self.template_name)
        messages.success(request, "Account created successfully. Please log in.")
        return redirect("login")
        
        sns = SNSManager(topic_arn=settings.AWS_SNS_TOPIC_ARN)
        sns.subscribe_with_filter(
        protocol="email",
        endpoint=email,
        filter_policy={"customer_email": [email]}
        )

class LoginView(CognitoUserAuth, View):
    template_name = "supplyapp/login.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, self.template_name)

        # Check if the user exists before authenticating
        if not self.cognito.user_exists(email):
            messages.error(request, "Account does not exist. Please sign up first.")
            return redirect("signup")

        login_result = self.cognito.login(email, password)
        if "error" in login_result:
            messages.error(request, login_result["error"])
            return render(request, self.template_name)

        tokens = login_result.get("tokens", {})
        request.session["access_token"] = tokens.get("AccessToken")
        request.session["id_token"] = tokens.get("IdToken")
        request.session["refresh_token"] = tokens.get("RefreshToken")
        request.session["user_email"] = email
        request.session.modified = True
        print("DEBUG LOGIN: session after save:", dict(request.session))

        return redirect("customer_order_form")  # Replace with your actual URL name

        
class LogoutView(CognitoUserAuth, View):
    def get(self, request):
        return self.post(request)

    def post(self, request):
        access_token = request.session.get("access_token")

        if access_token:
            self.cognito.logout(access_token)

        request.session.flush()
        return redirect("login")

class ForgotPasswordView(View):
    def get(self, request):
        return render(request, "supplyapp/forgot_password.html")
