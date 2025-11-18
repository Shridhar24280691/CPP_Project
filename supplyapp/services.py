from dataclasses import dataclass
from typing import List
import uuid
import boto3
from supplychainlib.aws_lambda import LambdaInvoker
from botocore.exceptions import ClientError
from supplychainlib.aws_dynamodb import (
    DynamoDBManager,
    SupplierManager,
    RawMaterialManager,
    FinishedProductManager,
    PurchaseOrderManager,
    DistributorOrderManager,
    DistributorInventoryManager,
)
from supplychainlib.utility import TrackingUtility
from django.conf import settings
from .models import PurchaseOrderHistory, DistributorOrderHistory, CustomerOrderHistory
from .invoice_generator import generate_and_upload_invoice
from django.utils.timezone import now

@dataclass
class SupplierService:
    manager: SupplierManager

    def list_active(self) -> List[dict]:
        return self.manager.scan()

    def create(self, name: str, product: str, price: float, origin: str) -> dict:
        item = {
            "id": TrackingUtility.generate("SUP"),
            "name": name,
            "product": product,
            "price_per_unit": float(price),
            "origin": origin,
            "active": True,
        }
        self.manager.put(item)
        return item

@dataclass
class RawMaterialService:
    manager: RawMaterialManager

    def list_for_supplier(self, supplier_id: str) -> List[dict]:
        return self.manager.list_for_supplier(supplier_id)

    def create(self, supplier_id: str, name: str, cost: float, location: str, quantity: int) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "supplier_id": supplier_id,
            "name": name,
            "cost": float(cost),
            "location": location,
            "quantity": int(quantity),
        }
        self.manager.put_item(item)
        return item

    def changequantity(self, materialid: str, delta: int) -> None:
        existing = self.manager.get_item({"id": materialid})
        if not existing:
            purchase_order = PurchaseOrderHistory.objects.filter(raw_material=materialid).last()
            product_name = None
            cost_per_pound = 0.0
            origin = "Unknown"
            if purchase_order:
                supplier = SupplierManager().get_item({"id": purchase_order.supplier_id})
                if supplier:
                    product_name = supplier.get("product", "") or "Unnamed Material"
                    cost_per_pound = float(supplier.get("price_per_unit", 0))
                    origin = supplier.get("origin", "Unknown")
            if not product_name:
                product_name = "Unnamed Material"
            
            self.manager.put_item({
                "id": materialid,
                "name": product_name,
                "quantity": int(delta),
                "origin": origin,
                "cost_per_pound": cost_per_pound,
            })
            return
        
        # If it exists, just update quantity...
        self.manager.update_item(
            key={"id": materialid},
            update_expr="SET quantity = if_not_exists(quantity, :z) + :d",
            values={":d": int(delta), ":z": 0},
        )
        
@dataclass
class PurchaseOrderService:
    manager: PurchaseOrderManager
    raw_materials: RawMaterialService

    def create(self, supplier_id: str, material_id: str, quantity: int, delivery_date: str) -> dict:
        po_id = TrackingUtility.generate("PO")
        supplier_table = DynamoDBManager("Suppliers")
        suppliers = supplier_table.scan_table()
        supplier = next((s for s in suppliers if s.get("id") == supplier_id), None)
        raw_material_name = None
        price_per_unit = 0.0
        origin = ""
        if supplier:
            raw_material_name = supplier.get("product", "Unknown Material")
            price_per_unit = float(supplier.get("price_per_unit", 0))
            origin = supplier.get("origin", "")
        item = {
            "po_id": po_id,
            "supplier_id": supplier_id,
            "raw_material": material_id,
            "raw_material_name": raw_material_name,
            "origin": origin,
            "price_per_unit": price_per_unit,
            "quantity": int(quantity),
            "delivery_date": delivery_date,
            "status": "Sent",
        }
        # save to Django ORM ---
        try:
            PurchaseOrderHistory.objects.create(
                order_id=po_id,
                supplier_id=supplier_id,
                raw_material=material_id,
                raw_material_name=raw_material_name,
                quantity=int(quantity),
                status="Sent",
                order_date=now().date(),
                delivery_date=delivery_date, 
        )
        except Exception as e:
            print("ORM error:", e)
      
        try:
            invoker = LambdaInvoker(region_name="us-east-1")
            lambda_response = invoker.invoke_function('GenerateInvoiceLambda', item)
            print(f"Lambda invoked for PO {po_id}: {lambda_response}")
        except Exception as e:
            print(f"Lambda invoice generation failed for PO {po_id}: {e}")
        return item

    def mark_received(self, po_id: str) -> None:
        po = self.manager.get_item(po_id)
        if not po:
            return
        self.manager.update_item(
            key={"po_id": po_id},
            update_expr="SET #s = :r",
            values={":r": "Received"},
            names={"#s": "status"},
        )
        material_id = po.get("raw_material")
        qty = int(po.get("quantity", 0))
        if material_id and qty:
            self.raw_materials.change_quantity(material_id, qty)

@dataclass
class FinishedProductService:
    manager: FinishedProductManager
    raw_materials: RawMaterialService

    def create_from_raw(self, material_id: str, blend_name: str, units: int, unit_price: float) -> dict:
        material = self.raw_materials.manager.get({"id": material_id})
        if not material:
            raise ValueError("Raw material not found")
        if units <= 0 or units > int(material.get("quantity", 0)):
            raise ValueError("Invalid quantity")
        self.raw_materials.change_quantity(material_id, -units)
        product_id = TrackingUtility.generate("FP")
        item = {
            "id": product_id,
            "blend_name": blend_name,
            "raw_material": material_id,
            "quantity": int(units),
            "unit_price": float(unit_price),
        }
        self.manager.put(item)
        return item

@dataclass
class DistributorOrderService:
    orders: DistributorOrderManager
    inventory: DistributorInventoryManager
    finished: FinishedProductManager

    def create(self, distributor_id: str, product_id: str, quantity: int) -> dict:
        product = self.finished.get({"id": product_id})
        if not product:
            raise ValueError("Product not found")
        if quantity <= 0 or quantity > int(product.get("quantity", 0)):
            raise ValueError("Insufficient stock")
        order_id = TrackingUtility.generate("DORD")
        item = {
            "id": order_id,
            "distributor_id": distributor_id,
            "product_id": product_id,
            "quantity": int(quantity),
            "status": "Placed",
        }
        self.orders.put(item)
        return item

    def mark_received(self, order_id: str) -> None:
        order = self.orders.get({"id": order_id})
        if not order:
            return
        self.orders.update(
            key={"id": order_id},
            update_expr="SET #s = :r",
            values={":r": "Received"},
            names={"#s": "status"},
        )
        self.inventory.add_stock(
            distributor_id=order["distributor_id"],
            product_id=order["product_id"],
            quantity=int(order.get("quantity", 0)),
        )
        self.finished.update(
            key={"id": order["product_id"]},
            update_expr="SET quantity = quantity - :q",
            values={":q": int(order.get("quantity", 0))},
        )

# HISTORY SERVICES - NO @dataclass, NO ARGS IN CONSTRUCTOR

class PurchaseOrderHistoryService:
    def list_all(self):
        return PurchaseOrderHistory.objects.all()

    def get_by_id(self, order_id):
        return PurchaseOrderHistory.objects.get(order_id=order_id)

    def update_status(self, order_id, new_status):
        order = self.get_by_id(order_id)
        order.status = new_status
        order.save()
        return order

class DistributorOrderHistoryService:
    def list_all(self):
        return DistributorOrderHistory.objects.all()

    def get_by_id(self, order_id):
        return DistributorOrderHistory.objects.get(order_id=order_id)

    def update_status(self, order_id, new_status):
        order = self.get_by_id(order_id)
        order.status = new_status
        order.save()
        return order

class CustomerOrderService:
    """
    Service for managing live customer orders using DynamoDB.
    """
    def __init__(self):
        self.manager = CustomerOrderManager()

    def create(self, customer_id, product_id, quantity, status):
        """
        Create a customer order in DynamoDB.
        """
        order_id = str(uuid.uuid4())
        item = {
            "id": order_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "status": status,
        }
        self.manager.put(item)
        return item

class CustomerOrderHistoryService:
    """
    Service for managing customer order history using Django ORM.
    """
    def create(self, customer_id, product_id, quantity, status):
        """
        Create a historical record in Django ORM.
        """
        return CustomerOrderHistory.objects.create(
            order_id=str(uuid.uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            status=status,
            order_date=now().date()
        )

    def list_all(self):
        """
        List all historical customer orders.
        """
        return CustomerOrderHistory.objects.all().order_by("-order_date")

class InventoryService:
    def __init__(self):
        self.bucket_name = settings.AWS_S3_BUCKET_NAME
        self.s3_manager = S3Manager(self.bucket_name)
        self.invoice_generator = InvoiceGenerator()

    def generate_and_upload_invoice(self, po):
        invoice_key = self.invoice_generator.generate_po_invoice(po)
        return invoice_key

    def get_invoice_url(self, s3_key):
        try:
            url = self.s3_manager.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )
            return url
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return None

    def upload_invoice_file(self, file_obj, object_name):
        try:
            self.s3_manager.upload_fileobj(file_obj, object_name)
            return True
        except Exception as e:
            print(f"Upload failed: {e}")
            return False


class CognitoService:
    def __init__(self):
        self.client = boto3.client(
            "cognito-idp",
            region_name=settings.COGNITO_REGION
        )

    def sign_up(self, email, password):
        try:
            response = self.client.sign_up(
                ClientId=settings.COGNITO_CLIENT_ID,
                Username=email,
                Password=password,
                UserAttributes=[
                    {"Name": "email", "Value": email}
                ]
            )
            return {"success": True, "response": response}

        except ClientError as e:
            return {"error": e.response["Error"]["Message"]}

    def auto_confirm_user(self, email):
        try:
            # STEP 1: confirm user
            self.client.admin_confirm_sign_up(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email
            )

            # STEP 2: mark email verified
            self.client.admin_update_user_attributes(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {"Name": "email_verified", "Value": "true"}
                ]
            )

            return {"success": True}

        except ClientError as e:
            return {"error": e.response["Error"]["Message"]}

    def login(self, email, password):
        try:
            response = self.client.initiate_auth(
                ClientId=settings.COGNITO_CLIENT_ID,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password
                }
            )
            return {"success": True, "tokens": response["AuthenticationResult"]}

        except ClientError as e:
            return {"error": e.response["Error"]["Message"]}

    def user_exists(self, email):
        try:
            self.client.admin_get_user(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email
            )
            return True
        except self.client.exceptions.UserNotFoundException:
            return False
        except ClientError:
            return False

    def logout(self, access_token):
        try:
            response = self.client.global_sign_out(
                AccessToken=access_token
            )
            return {"success": True, "response": response}
        except ClientError as e:
            return {"error": e.response["Error"]["Message"]}
