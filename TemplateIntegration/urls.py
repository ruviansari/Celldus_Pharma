"""
URL configuration for TemplateIntegration project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # OpenAPI 3.0 Documentation (Swagger & ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Celldus Pharma ERP Versioned APIs (v1)
    path('api/v1/core/', include('erp_core.urls')),
    path('api/v1/masters/', include('erp_masters.urls')),
    path('api/v1/inventory/', include('erp_inventory.urls')),
    path('api/v1/procurement/', include('erp_procurement.urls')),
    path('api/v1/quality/', include('erp_quality.urls')),
    path('api/v1/manufacturing/', include('erp_manufacturing.urls')),
    path('api/v1/sales/', include('erp_sales.urls')),
    path('api/v1/crm/', include('erp_crm.urls')),
    path('api/v1/finance/', include('erp_finance.urls')),
    path('api/v1/hr/', include('erp_hr.urls')),
    path('api/v1/tracking/', include('erp_crm.tracking_urls')),

    # Frontend Website & Dashboards
    path('', include('main.urls')),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
