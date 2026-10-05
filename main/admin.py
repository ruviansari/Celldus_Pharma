from django.contrib import admin
from .models import Contact, Subscriber, Category, Product

admin.site.register(Contact)
admin.site.register(Subscriber)
admin.site.register(Category)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'selling_price', 'stock', 'size', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')