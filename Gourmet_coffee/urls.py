
from django.contrib import admin
from django.urls import path, include 
#from supplyapp.views import LoginView

urlpatterns = [
    #path('', LoginView.as_view(), name='user_login'),
    path('admin/', admin.site.urls),
    path('', include('supplyapp.urls')),

]
