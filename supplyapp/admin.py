from django.contrib import admin
from .models import (
    PurchaseOrderHistory,
    DistributorOrderHistory,
    CustomerOrderHistory,
)

admin.site.register(PurchaseOrderHistory)
admin.site.register(DistributorOrderHistory)
admin.site.register(CustomerOrderHistory)

