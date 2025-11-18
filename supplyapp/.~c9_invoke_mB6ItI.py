from django.db import models

class Supplier(models.Model):
    name = models.CharField(max_length=100)
    product = models.CharField(max_length=100)
    price_per_unit = models.FloatField()
    origin = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    product = models.CharField(max_length=100)
    quantity = models.IntegerField()
    delivery_date = models.DateField()
    status = models.CharField(max_length=40, default='Draft')

class RawMaterial(models.Model):
    bean_type = models.CharField(max_length=100)
    quantity = models.IntegerField()
    warehouse_location = models.CharField(max_length=100)

class FinishedProduct(models.Model):
    blend_name = models.CharField(max_length=100)
    quantity = models.IntegerField()
    stock_updated = models.DateTimeField(auto_now=True)

class Order(models.Model):
    customer_name = models.CharField(max_length=100)
    blends = models.CharField(max_length=255)
    quantity = models.IntegerField()
    address = models.TextField()
    status = models.CharField(max_length=40, default='Processing')
    tracking_link = models.URLField(blank=True, null=True)
