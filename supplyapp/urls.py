from django.urls import path

from .views import (
    DashboardView,
    SupplierListView,
    SupplierManagerView,
    RawMaterialBySupplierView,
    PurchaseOrderFormView,
    PurchaseOrderHistoryView,
    PO_StatusView,
    InventoryDashboardView,
    ConvertRawToFinishedView,
    UploadInventoryFileView,
    DeleteInvoiceView,
    DistributorListView,
    DistributorManageView,
    DistributorOrderFormView,
    ChangeDistributorOrderStatusView,
    DistributorOrderHistoryView,
    DistributorInventoryView,
    CustomerOrderFormView,  CustomerOrderDetailsView,
    ProductDetailsAjaxView,
    CustomerOrderHistoryView,
    ShipmentTrackingView,
    SignupView, LoginView, LogoutView, ForgotPasswordView
    )
'''RegisterView, LoginView, logout_view, check_email_exists_ajax'''

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    
    # suppliers
    path('suppliers/', SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/manage/', SupplierManagerView.as_view(), name='supplier_manage'),
    path('suppliers/manage/<str:supplier_id>/', SupplierManagerView.as_view(), name='supplier_edit'),
    path('suppliers/manage/<str:supplier_id>/delete/', SupplierManagerView.as_view(), name='supplier_delete'),
    # purchase orders
    path(
    'suppliers/<str:supplier_id>/raw-materials/',
    RawMaterialBySupplierView.as_view(),
    name='supplier_raw_materials',
    ),
    path(
        "purchase-orders/new/",
        PurchaseOrderFormView.as_view(),
        name="purchase_order_form",
    ),
    path(
        "purchase-orders/history/",
        PurchaseOrderHistoryView.as_view(),
        name="purchase_order_history",
    ),
    path("purchase-orders/<str:po_id>/update-status/", PO_StatusView.as_view(), name="update_purchase_order_status",),

    # inventory
    path("inventory/", InventoryDashboardView.as_view(), name="inventory_dashboard",),
    path("inventory/raw/<str:material_id>/convert/",ConvertRawToFinishedView.as_view(),name="convert_to_finished"),
    path('inventory/upload/', UploadInventoryFileView.as_view(), name='upload_inventory_file'),
    path('inventory/delete_invoice/', DeleteInvoiceView.as_view(), name='delete_invoice'),
    
    # distributor orders
    path('distributors/', DistributorListView.as_view(), name="distributor_list",),
    path("distributors/manage/", DistributorManageView.as_view(), name="distributor_add"),
    path("distributors/manage/<str:distributor_id>/", DistributorManageView.as_view(), name="distributor_edit"),
    path("distributor/orders/new/",DistributorOrderFormView.as_view(),name="distributor_order_form",),
    path("distributor/orders/<str:order_id>/change-status/",ChangeDistributorOrderStatusView.as_view(),name="change_distributor_order_status",),
    path("distributor/orders/history/",DistributorOrderHistoryView.as_view(),name="distributor_order_history",),
    path("distributor/inventory/", DistributorInventoryView.as_view(), name="distributor_inventory"),path("distributor/inventory/", DistributorInventoryView.as_view(), name="distributor_inventory"),

    path("customer/orders/new/", CustomerOrderFormView.as_view(), name="customer_order_form"),
    path("get-product-details/", ProductDetailsAjaxView.as_view(), name="get_product_details"),
    path("customer/orders/details/", CustomerOrderDetailsView.as_view(), name="customer_order_details"),
    path("customer/orders/history/", CustomerOrderHistoryView.as_view(), name="customer_order_history"),
    
    path("shipment-tracking/<str:shipment_id>/", ShipmentTrackingView.as_view(), name="shipment_tracking"),
    
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),

]
