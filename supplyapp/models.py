from django.db import models
from supplychainlib.aws_dynamodb import DistributorInventoryManager

class PurchaseOrderHistory(models.Model):
    order_id = models.CharField(max_length=100, primary_key=True)
    supplier_id = models.CharField(max_length=100)
    raw_material = models.CharField(max_length=100) 
    raw_material_name = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=50)
    order_date = models.DateField()
    delivery_date = models.CharField(max_length=100, blank=True, null=True)
    def __str__(self):
        return f"PO {self.order_id} - {self.status}"


class DistributorOrderHistory(models.Model):
    order_id = models.CharField(max_length=100, primary_key=True)
    distributor_id = models.CharField(max_length=100)
    product_id = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=50)
    order_date = models.DateField()

    def __str__(self):
        return f"Distributor Order {self.order_id} - {self.status}"


class CustomerOrderHistory(models.Model):
    order_id = models.CharField(max_length=100, primary_key=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)     # allow blank/null for migration
    distributor_id = models.CharField(max_length=255, blank=True, null=True)
    distributor_name = models.CharField(max_length=255, blank=True, null=True)
    product_id = models.CharField(max_length=255, blank=True, null=True)
    product_name = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.PositiveIntegerField()
    address = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50)
    tracking_link = models.CharField(max_length=255, blank=True, null=True)
    order_date = models.DateField()
    
    def update_status_and_inventory(self, new_status):
        previous_status = self.status
        self.status = new_status
        self.save()

        # Inventory update logic
        if previous_status != "Delivered" and new_status == "Delivered":
            distributor_id = self.distributor_id
            product_id = self.product_id
            quantity = int(self.quantity)
            inventory_manager = DistributorInventoryManager()
            inv_id = f"{distributor_id}#{product_id}"
            key = {"id": inv_id}
            existing = inventory_manager.get_item(key)
            if existing and existing.get("quantity") is not None:
                current_qty = int(existing["quantity"])
                updated_qty = max(0, current_qty - quantity)
                inventory_manager.update_item(
                    key=key,
                    update_expr="SET quantity = :q",
                    values={":q": updated_qty}
                )
        elif previous_status == "Delivered" and new_status != "Delivered":
            # Optional: Restore inventory if moving away from "Delivered"
            distributor_id = self.distributor_id
            product_id = self.product_id
            quantity = int(self.quantity)
            inventory_manager = DistributorInventoryManager()
            inv_id = f"{distributor_id}#{product_id}"
            key = {"id": inv_id}
            existing = inventory_manager.get_item(key)
            if existing and existing.get("quantity") is not None:
                current_qty = int(existing["quantity"])
                updated_qty = current_qty + quantity
                inventory_manager.update_item(
                    key=key,
                    update_expr="SET quantity = :q",
                    values={":q": updated_qty}
                )
    
    def __str__(self):
        return f"{self.customer_name} - {self.product_name} x {self.quantity}"

