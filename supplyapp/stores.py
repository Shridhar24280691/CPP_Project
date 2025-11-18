import boto3
from botocore.exceptions import ClientError


# ===============================================================
# Base class for DynamoDB interactions
# ===============================================================
class DynamoBase:
    """Base class providing common DynamoDB CRUD methods."""

    def __init__(self, table_name, key_name, region_name='us-east-1'):
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
        self.table_name = table_name
        self.key_name = key_name

    # Create / insert a record
    def create_item(self, item):
        try:
            self.table.put_item(Item=item)
            print(f"Item added to {self.table_name}: {item}")
            return item
        except ClientError as e:
            print(f"Error inserting into {self.table_name}: {e}")
            return None

    # Get a record by key
    def get_item(self, key_value):
        try:
            response = self.table.get_item(Key={self.key_name: key_value})
            return response.get('Item')
        except ClientError as e:
            print(f"Error fetching item from {self.table_name}: {e}")
            return None

    # List all records
    def list_items(self):
        try:
            response = self.table.scan()
            return response.get('Items', [])
        except ClientError as e:
            print(f"Error scanning {self.table_name}: {e}")
            return []

    # Update record by key
    def update_item(self, key_value, update_expression, values_dict, names=None):
        try:
            kwargs = {
                "Key": {self.key_name: key_value},
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": values_dict
            }
            if names:
                kwargs["ExpressionAttributeNames"] = names
            self.table.update_item(**kwargs)
            print(f"Item updated in {self.table_name}: {key_value}")
        except ClientError as e:
            print(f"Error updating item in {self.table_name}: {e}")

    # Delete record by key
    def delete_item(self, key_value):
        try:
            self.table.delete_item(Key={self.key_name: key_value})
            print(f"Item deleted from {self.table_name}: {key_value}")
        except ClientError as e:
            print(f"Error deleting item from {self.table_name}: {e}")
# ===============================================================
# Table-specific classes
# ===============================================================


class SupplierStore(DynamoBase):
    """Handles Supplier data stored in DynamoDB."""

    def __init__(self):
        super().__init__("Suppliers", "id")

    def create(self, name, product, price, origin):
        item = {
            "id": f"SPL-{name[:3].upper()}",
            "name": name,
            "product": product,
            "price": float(price),
            "origin": origin
        }
        return self.create_item(item)


class RawMaterialStore(DynamoBase):
    """Handles Raw Materials data stored in DynamoDB."""

    def __init__(self):
        super().__init__("Inventory", "product_id")

    def create(self, name, supplier, origin, cost, qty):
        item = {
            "product_id": f"RM-{name[:3].upper()}",
            "name": name,
            "supplier": supplier,
            "origin": origin,
            "cost_per_pound": float(cost),
            "quantity": int(qty)
        }
        return self.create_item(item)


class FinishedProductStore(DynamoBase):
    """Handles Finished Products stored in DynamoDB."""

    def __init__(self):
        super().__init__("FinishedProducts", "finished_id")

    def create(self, blend_name, raw_material, qty, price):
        item = {
            "finished_id": f"FP-{blend_name[:3].upper()}",
            "blend_name": blend_name,
            "raw_material": raw_material,
            "quantity": int(qty),
            "unit_price": float(price)
        }
        return self.create_item(item)


class PurchaseOrderStore(DynamoBase):
    """Handles Purchase Orders stored in DynamoDB."""

    def __init__(self):
        super().__init__("PurchaseOrders", "po_id")

    def create(self, supplier, raw_material, qty, delivery_date):
        po_id = f"PO-{supplier[:3].upper()}-{raw_material[:3].upper()}"
        item = {
            "po_id": po_id,
            "supplier": supplier,
            "raw_material": raw_material,
            "quantity": int(qty),
            "delivery_date": str(delivery_date),
            "status": "Sent"
        }
        return self.create_item(item)


class DistributorOrderStore(DynamoBase):
    """Handles Distributor Orders stored in DynamoDB."""

    def __init__(self):
        super().__init__("DistributorOrders", "order_id")

    def create(self, distributor_name, product_name, qty):
        order_id = f"DORD-{distributor_name[:3].upper()}"
        item = {
            "order_id": order_id,
            "distributor_name": distributor_name,
            "product_name": product_name,
            "quantity": int(qty),
            "status": "Placed",
            "order_date": str(now().date())
        }
        return self.create_item(item)
