from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    home, about, product, our_blog, faq, product_detail, blog_details, contact_page, splashscreen, subscribe,
    # Dashboard Auth
    dashboard_login, dashboard_logout,
    # Dashboard main
    dashboard_index,
    # Categories
    dashboard_categories, dashboard_category_add, dashboard_category_edit, dashboard_category_delete,
    # Products
    dashboard_products, dashboard_product_add, dashboard_product_edit, dashboard_product_delete,
    # Customers
    dashboard_customers, dashboard_inquiry_delete, dashboard_subscriber_delete,
    # Users
    dashboard_users, dashboard_user_add, dashboard_user_toggle, dashboard_user_delete, dashboard_user_change_password,
    # Custom Reset Views
    custom_forgot_password, custom_reset_confirm
)
from django.shortcuts import redirect
from . import dashboard_erp_views

urlpatterns = [
    path('', splashscreen, name='splashscreen'),
    path('home/', home, name='home'),
    path('home_page/', home, name='home_page'),
    path('home_page.html', lambda r: redirect('home', permanent=True)),
    path('product_details/<int:id>/home_page.html', lambda r, id: redirect('home', permanent=True)),
    path('about_us/', about, name='about_us'),
    path('product/', product, name='product'),
    path('our_blog/', our_blog, name='our_blog'),
    path('faq/', faq, name='faq'),
    path('product_details/<int:id>/', product_detail, name='product_details'),
    path('blog_details/<int:id>/', blog_details, name='blog_details'),
    path('contact/', contact_page, name='contact'),
    path('subscribe/', subscribe, name='subscribe'),
    
    # Dashboard Auth routes
    path('dashboard/login/', dashboard_login, name='dashboard_login'),
    path('dashboard/logout/', dashboard_logout, name='dashboard_logout'),
    
    # Dashboard main panel
    path('dashboard/', dashboard_index, name='dashboard_index'),
    
    # Category Management URLs
    path('dashboard/categories/', dashboard_categories, name='dashboard_categories'),
    path('dashboard/categories/add/', dashboard_category_add, name='dashboard_category_add'),
    path('dashboard/categories/edit/<int:id>/', dashboard_category_edit, name='dashboard_category_edit'),
    path('dashboard/categories/delete/<int:id>/', dashboard_category_delete, name='dashboard_category_delete'),
    
    # Product Management URLs
    path('dashboard/products/', dashboard_products, name='dashboard_products'),
    path('dashboard/products/add/', dashboard_product_add, name='dashboard_product_add'),
    path('dashboard/products/edit/<int:id>/', dashboard_product_edit, name='dashboard_product_edit'),
    path('dashboard/products/delete/<int:id>/', dashboard_product_delete, name='dashboard_product_delete'),
    
    # Customer module (Inquiries/Subscribers) URLs
    path('dashboard/customers/', dashboard_customers, name='dashboard_customers'),
    path('dashboard/customers/inquiry/delete/<int:id>/', dashboard_inquiry_delete, name='dashboard_inquiry_delete'),
    path('dashboard/customers/subscriber/delete/<int:id>/', dashboard_subscriber_delete, name='dashboard_subscriber_delete'),
    
    # User Management URLs
    path('dashboard/users/', dashboard_users, name='dashboard_users'),
    path('dashboard/users/add/', dashboard_user_add, name='dashboard_user_add'),
    path('dashboard/users/toggle/<int:id>/', dashboard_user_toggle, name='dashboard_user_toggle'),
    path('dashboard/users/delete/<int:id>/', dashboard_user_delete, name='dashboard_user_delete'),
    path('dashboard/users/change-password/<int:id>/', dashboard_user_change_password, name='dashboard_user_change_password'),
    
    # Password Reset URLs
    path('password-reset/', custom_forgot_password, name='password_reset'),
    path('password-reset-confirm/<uidb64>/<token>/', custom_reset_confirm, name='password_reset_confirm'),

    # ==========================================
    # ENTERPRISE PHARMA ERP DASHBOARD UI ROUTES
    # ==========================================
    path('dashboard/lots/', dashboard_erp_views.dashboard_inventory_lots, name='dashboard_inventory_lots'),
    path('dashboard/lots/action/<uuid:lot_id>/', dashboard_erp_views.dashboard_lot_action, name='dashboard_lot_action'),
    path('dashboard/quality/', dashboard_erp_views.dashboard_quality, name='dashboard_quality'),
    path('dashboard/quality/disposition/<uuid:inspection_id>/', dashboard_erp_views.dashboard_qa_execute_disposition, name='dashboard_qa_execute_disposition'),
    path('dashboard/procurement/', dashboard_erp_views.dashboard_procurement, name='dashboard_procurement'),
    path('dashboard/procurement/po/add/', dashboard_erp_views.dashboard_po_create, name='dashboard_po_create'),
    path('dashboard/procurement/po-approve/<uuid:po_id>/', dashboard_erp_views.dashboard_po_approve, name='dashboard_po_approve'),
    path('dashboard/procurement/grn/create/<uuid:po_id>/', dashboard_erp_views.dashboard_grn_create, name='dashboard_grn_create'),
    path('dashboard/production/', dashboard_erp_views.dashboard_production, name='dashboard_production'),
    path('dashboard/production/complete/<uuid:order_id>/', dashboard_erp_views.dashboard_batch_complete, name='dashboard_batch_complete'),
    path('dashboard/sales/', dashboard_erp_views.dashboard_sales, name='dashboard_sales'),
    path('dashboard/sales/order/add/', dashboard_erp_views.dashboard_so_create, name='dashboard_so_create'),
    path('dashboard/sales/approve/<uuid:order_id>/', dashboard_erp_views.dashboard_so_approve_fefo, name='dashboard_so_approve_fefo'),
    path('dashboard/sales/dispatch/<uuid:order_id>/', dashboard_erp_views.dashboard_so_dispatch, name='dashboard_so_dispatch'),
    path('dashboard/sales/invoice/<uuid:invoice_id>/', dashboard_erp_views.dashboard_invoice_view, name='dashboard_invoice_view'),
    path('dashboard/crm/', dashboard_erp_views.dashboard_crm, name='dashboard_crm'),
    path('dashboard/crm/lead/add/', dashboard_erp_views.dashboard_lead_create, name='dashboard_lead_create'),
    path('dashboard/crm/lead/edit/<uuid:lead_id>/', dashboard_erp_views.dashboard_lead_edit, name='dashboard_lead_edit'),
    path('dashboard/crm/lead/stage/<uuid:lead_id>/', dashboard_erp_views.dashboard_lead_stage_update, name='dashboard_lead_stage_update'),
    path('dashboard/crm/lead/convert/<uuid:lead_id>/', dashboard_erp_views.dashboard_lead_convert, name='dashboard_lead_convert'),
    path('dashboard/crm/lead/delete/<uuid:lead_id>/', dashboard_erp_views.dashboard_lead_delete, name='dashboard_lead_delete'),
    path('dashboard/crm/task/add/', dashboard_erp_views.dashboard_task_create, name='dashboard_task_create'),
    path('dashboard/crm/task/update/<uuid:task_id>/', dashboard_erp_views.dashboard_task_update_status, name='dashboard_task_update_status'),
    path('dashboard/crm/task/delete/<uuid:task_id>/', dashboard_erp_views.dashboard_task_delete, name='dashboard_task_delete'),
    path('dashboard/crm/import/', dashboard_erp_views.dashboard_crm_bulk_import, name='dashboard_crm_bulk_import'),
    path('dashboard/crm/sample-csv/', dashboard_erp_views.dashboard_crm_sample_csv, name='dashboard_crm_sample_csv'),

    # Employee CRM & Workforce Operations
    path('dashboard/employee/', dashboard_erp_views.dashboard_employee, name='dashboard_employee'),
    path('dashboard/employee/add/', dashboard_erp_views.dashboard_employee_create, name='dashboard_employee_create'),
    path('dashboard/employee/edit/<uuid:employee_id>/', dashboard_erp_views.dashboard_employee_edit, name='dashboard_employee_edit'),
    path('dashboard/employee/toggle/<uuid:employee_id>/', dashboard_erp_views.dashboard_employee_toggle_status, name='dashboard_employee_toggle_status'),
    path('dashboard/employee/attendance/mark/', dashboard_erp_views.dashboard_attendance_mark, name='dashboard_attendance_mark'),
    path('dashboard/employee/leave/add/', dashboard_erp_views.dashboard_leave_create, name='dashboard_leave_create'),
    path('dashboard/employee/leave/<uuid:leave_id>/<str:action>/', dashboard_erp_views.dashboard_leave_action, name='dashboard_leave_action'),
    path('dashboard/audit-trail/', dashboard_erp_views.dashboard_audit_trail, name='dashboard_audit_trail'),
    path('dashboard/procurement/po/<uuid:po_id>/print/', dashboard_erp_views.dashboard_po_view, name='dashboard_po_view'),
    path('dashboard/invoices/', dashboard_erp_views.dashboard_invoices, name='dashboard_invoices'),
    path('dashboard/masters/', dashboard_erp_views.dashboard_masters, name='dashboard_masters'),
    path('dashboard/masters/item/add/', dashboard_erp_views.dashboard_item_create, name='dashboard_item_create'),
    path('dashboard/masters/supplier/add/', dashboard_erp_views.dashboard_supplier_create, name='dashboard_supplier_create'),
    path('dashboard/masters/customer/add/', dashboard_erp_views.dashboard_customer_create, name='dashboard_customer_create'),
    path('dashboard/masters/customer/<uuid:customer_id>/edit/', dashboard_erp_views.dashboard_customer_edit, name='dashboard_customer_edit'),
    path('dashboard/masters/customer/<uuid:customer_id>/toggle-status/', dashboard_erp_views.dashboard_customer_toggle_status, name='dashboard_customer_toggle_status'),
    path('dashboard/masters/warehouse/add/', dashboard_erp_views.dashboard_warehouse_create, name='dashboard_warehouse_create'),
    path('dashboard/masters/bin/add/', dashboard_erp_views.dashboard_storage_bin_create, name='dashboard_storage_bin_create'),
    path('dashboard/masters/bom/add/', dashboard_erp_views.dashboard_bom_create, name='dashboard_bom_create'),

    # Field Force Tracking & SFA Operations
    path('dashboard/field/portal/', dashboard_erp_views.dashboard_field_portal, name='dashboard_field_portal'),
    path('dashboard/field/tracking/', dashboard_erp_views.dashboard_field_tracking, name='dashboard_field_tracking'),
    path('dashboard/field/reports/', dashboard_erp_views.dashboard_field_reports, name='dashboard_field_reports'),

    # Expense Tracking & General Ledger Management
    path('dashboard/expenses/', dashboard_erp_views.dashboard_expenses, name='dashboard_expenses'),
    path('dashboard/expenses/create/', dashboard_erp_views.dashboard_expense_create, name='dashboard_expense_create'),
    path('dashboard/expenses/action/<uuid:claim_id>/', dashboard_erp_views.dashboard_expense_action, name='dashboard_expense_action'),
    path('dashboard/expenses/disburse/<uuid:claim_id>/', dashboard_erp_views.dashboard_expense_disburse, name='dashboard_expense_disburse'),
    path('dashboard/expenses/delete/<uuid:claim_id>/', dashboard_erp_views.dashboard_expense_delete, name='dashboard_expense_delete'),
]