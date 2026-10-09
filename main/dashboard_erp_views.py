import csv
import io
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction, models
from django.db.models import Q

# ERP Modules Imports
from django.conf import settings
from erp_core.models import AuditLog, Branch, ERPUserRole, DocumentSequence
from erp_core.security import audit_log_event, check_prevent_self_approval
from erp_masters.models import (
    ItemMaster, SupplierMaster, CustomerMaster, Territory,
    Warehouse, StorageBin, UnitOfMeasure,
    QualitySpecification, BOMHeader
)
from erp_inventory.models import InventoryLot, StockLedger, CycleCountSession
from erp_inventory.services import get_fefo_allocations
from erp_procurement.models import PurchaseRequisition, PurchaseOrder, PurchaseOrderLine, GoodsReceiptNote, GoodsReceiptNoteLine
from erp_procurement.services import post_grn_receipt
from erp_quality.models import QCInspectionRequest, QCTestResult, QADispositionRecord, QualityDeviation, ProductRecall
from erp_quality.services import execute_qa_disposition
from erp_manufacturing.models import ProductionOrder, BatchProcessStep
from erp_manufacturing.services import complete_production_batch
from erp_sales.models import SalesOrder, SalesOrderLine, SalesOrderLotAllocation, SalesDispatchInvoice
from erp_sales.services import approve_sales_order_and_reserve_fefo, dispatch_sales_order
from erp_crm.models import Lead, FollowUpTask, LeadImportBatch, DailyBeatPlan, FieldVisit, EmployeeLocationEvent, VisitOrderBooking
from erp_crm.services import process_lead_import_rows
from erp_crm.tracking_permissions import get_authenticated_employee, is_sales_manager, is_system_or_hr_admin
from erp_hr.models import Employee, AttendanceRecord, LeaveApplication


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff, login_url='dashboard_login')(view_func)


# ==========================================
# 1. INVENTORY & FEFO LOTS DASHBOARD
# ==========================================
@staff_required
def dashboard_inventory_lots(request):
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

    lots_qs = InventoryLot.objects.select_related('item', 'warehouse', 'bin', 'uom').order_by('expiry_date')

    if status_filter:
        lots_qs = lots_qs.filter(status=status_filter)
    if search:
        lots_qs = lots_qs.filter(lot_number__icontains=search) | lots_qs.filter(batch_no__icontains=search) | lots_qs.filter(item__name__icontains=search)

    today = timezone.now().date()
    context = {
        'lots': lots_qs[:100],
        'total_lots': InventoryLot.objects.count(),
        'quarantine_count': InventoryLot.objects.filter(status='QUARANTINE').count(),
        'available_count': InventoryLot.objects.filter(status='AVAILABLE').count(),
        'blocked_count': InventoryLot.objects.filter(status='BLOCKED').count(),
        'expired_count': InventoryLot.objects.filter(expiry_date__lt=today).count(),
        'status_filter': status_filter,
        'search_query': search,
        'items': ItemMaster.objects.filter(active_flag=True).order_by('name'),
    }
    return render(request, 'dashboard/erp_lots.html', context)


@staff_required
def dashboard_lot_action(request, lot_id):
    """Admin / QA Regulatory Action: Release, Block, Unblock, or Reject Lot with 21 CFR Part 11 rationale."""
    lot = get_object_or_404(InventoryLot, id=lot_id)
    if request.method == "POST":
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()

        if not reason or len(reason) < 5:
            messages.error(request, "21 CFR Part 11 Violation: A detailed regulatory rationale (minimum 5 characters) is mandatory.")
            return redirect('dashboard_inventory_lots')

        if action == "BLOCK":
            lot.status = 'BLOCKED'
            lot.save(update_fields=['status', 'updated_at'])
            audit_log_event(request.user, 'UPDATE', 'InventoryLot', lot.id, lot.lot_number, reason=f"Lot placed on quarantine/blocked hold: {reason}")
            messages.warning(request, f"Lot {lot.lot_number} has been placed on BLOCKED hold.")
        elif action in ["UNBLOCK", "RELEASE"]:
            lot.status = 'AVAILABLE'
            lot.released_at = timezone.now()
            lot.released_by = request.user
            lot.save(update_fields=['status', 'released_at', 'released_by', 'updated_at'])
            audit_log_event(request.user, 'UPDATE', 'InventoryLot', lot.id, lot.lot_number, reason=f"Regulatory Release authorized by {request.user.username}: {reason}")
            messages.success(request, f"Lot {lot.lot_number} authorized & released to AVAILABLE status.")
        elif action == "REJECT":
            lot.status = 'REJECTED'
            lot.save(update_fields=['status', 'updated_at'])
            audit_log_event(request.user, 'UPDATE', 'InventoryLot', lot.id, lot.lot_number, reason=f"Lot rejected by QA: {reason}")
            messages.error(request, f"Lot {lot.lot_number} has been rejected & quarantined for material disposal.")

    return redirect('dashboard_inventory_lots')


# ==========================================
# 2. QUALITY CONTROL & QA DISPOSITION DASHBOARD
# ==========================================
@staff_required
def dashboard_quality(request):
    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('q', '').strip()

    inspections = QCInspectionRequest.objects.select_related('lot', 'item', 'specification', 'sampler', 'analyst').order_by('-created_at')
    
    pending_sampling_count = QCInspectionRequest.objects.filter(status='PENDING_SAMPLING').count()
    testing_count = QCInspectionRequest.objects.filter(status='SAMPLED').count()
    dispositioned_count = QCInspectionRequest.objects.filter(status='DISPOSITIONED').count()
    total_count = QCInspectionRequest.objects.count()

    if status_filter:
        inspections = inspections.filter(status=status_filter)
    if search:
        inspections = inspections.filter(
            Q(document_no__icontains=search) |
            Q(item__name__icontains=search) |
            Q(item__item_code__icontains=search) |
            Q(lot__lot_number__icontains=search) |
            Q(lot__batch_no__icontains=search)
        )

    dispositions = QADispositionRecord.objects.select_related('lot', 'inspection', 'authorized_qa_person').order_by('-disposition_date')[:20]
    deviations = QualityDeviation.objects.select_related('affected_lot').order_by('-created_at')[:20]

    context = {
        'inspections': inspections[:50],
        'dispositions': dispositions,
        'deviations': deviations,
        'pending_sampling_count': pending_sampling_count,
        'testing_count': testing_count,
        'dispositioned_count': dispositioned_count,
        'total_count': total_count,
        'status_filter': status_filter,
        'search_query': search,
    }
    return render(request, 'dashboard/erp_quality.html', context)


@staff_required
def dashboard_qa_execute_disposition(request, inspection_id):
    """Form to execute formal QA batch release, reject, or hold."""
    if request.method == "POST":
        disp_choice = request.POST.get('disposition')
        reason = request.POST.get('reason', '').strip()
        coa_number = request.POST.get('coa_number', '').strip()

        if not disp_choice or not reason:
            messages.error(request, "Disposition decision and detailed regulatory reason are required.")
            return redirect('dashboard_quality')

        if len(reason) < 5:
            messages.error(request, "21 CFR Part 11 Violation: Detailed regulatory reason must have at least 5 characters.")
            return redirect('dashboard_quality')

        if disp_choice == 'RELEASE' and not coa_number:
            messages.error(request, "Pharmaceutical Compliance Error: A valid Certificate of Analysis (COA) number is mandatory to release stock.")
            return redirect('dashboard_quality')

        try:
            disp_record = execute_qa_disposition(inspection_id, disp_choice, reason, request.user, coa_number)
            if disp_choice == 'RELEASE':
                messages.success(request, f"Batch {disp_record.lot.batch_no} (Lot {disp_record.lot.lot_number}) successfully RELEASED for commercial distribution. COA: {coa_number}")
            elif disp_choice == 'REJECT':
                messages.error(request, f"Batch {disp_record.lot.batch_no} REJECTED and segregated.")
            else:
                messages.warning(request, f"Batch {disp_record.lot.batch_no} placed on QA Quarantine HOLD.")
        except Exception as e:
            messages.error(request, f"QA Execution Error: {str(e)}")

    return redirect('dashboard_quality')


# ==========================================
# 3. PROCUREMENT & GOODS RECEIPT (GRN)
# ==========================================
@staff_required
def dashboard_procurement(request):
    prs = PurchaseRequisition.objects.order_by('-created_at')[:20]
    pos = PurchaseOrder.objects.select_related('supplier', 'branch').prefetch_related('lines__item', 'lines__uom').order_by('-created_at')[:30]
    grns = GoodsReceiptNote.objects.select_related('po', 'supplier', 'warehouse').prefetch_related('lines__item', 'lines__lot').order_by('-created_at')[:30]

    context = {
        'prs': prs,
        'pos': pos,
        'grns': grns,
        'suppliers': SupplierMaster.objects.filter(status='QUALIFIED'),
        'items': ItemMaster.objects.filter(active_flag=True),
        'warehouses': Warehouse.objects.all(),
        'branches': Branch.objects.filter(is_active=True),
        'bins': StorageBin.objects.select_related('warehouse').all(),
        'today': timezone.now().date(),
    }
    return render(request, 'dashboard/erp_procurement.html', context)


@staff_required
def dashboard_po_create(request):
    if request.method == "POST":
        supplier_id = request.POST.get('supplier_id')
        branch_id = request.POST.get('branch_id')
        order_date = request.POST.get('order_date') or timezone.now().date()
        expected_date = request.POST.get('expected_delivery_date')
        payment_terms = request.POST.get('payment_terms', 'Net 30 Days')

        item_id = request.POST.get('item_id')
        qty_val = request.POST.get('ordered_qty')
        rate_val = request.POST.get('rate')
        tax_pct_val = request.POST.get('tax_percent', '12.00')
        discount_pct_val = request.POST.get('discount_percent', '0.00')

        if not supplier_id or not expected_date or not item_id or not qty_val or not rate_val:
            messages.error(request, "Supplier, Delivery Date, Item, Quantity, and Rate are mandatory to generate PO.")
            return redirect('dashboard_procurement')

        try:
            qty = Decimal(str(qty_val))
            rate = Decimal(str(rate_val))
            tax_pct = Decimal(str(tax_pct_val or '0'))
            discount_pct = Decimal(str(discount_pct_val or '0'))
            if qty <= Decimal('0') or rate <= Decimal('0'):
                messages.error(request, "Ordered Quantity and Unit Rate must be greater than zero.")
                return redirect('dashboard_procurement')
        except Exception:
            messages.error(request, "Invalid numerical inputs.")
            return redirect('dashboard_procurement')

        supplier = get_object_or_404(SupplierMaster, id=supplier_id)
        item = get_object_or_404(ItemMaster, id=item_id)
        branch = Branch.objects.filter(id=branch_id).first() or Branch.objects.first()

        try:
            with transaction.atomic():
                po = PurchaseOrder(
                    supplier=supplier,
                    branch=branch,
                    order_date=order_date,
                    expected_delivery_date=expected_date,
                    payment_terms=payment_terms,
                    status='SUBMITTED',
                    created_by=request.user
                )
                po.save()

                line = PurchaseOrderLine(
                    order=po,
                    item=item,
                    ordered_qty=qty,
                    uom=item.base_uom,
                    rate=rate,
                    discount_percent=discount_pct,
                    tax_percent=tax_pct,
                    created_by=request.user
                )
                line.save()

                base = line.ordered_qty * line.rate * (Decimal('1.00') - (line.discount_percent / Decimal('100.00')))
                tax = base * (line.tax_percent / Decimal('100.00'))
                po.subtotal = base
                po.tax_total = tax
                po.grand_total = base + tax
                po.save(update_fields=['subtotal', 'tax_total', 'grand_total'])

                audit_log_event(
                    user=request.user,
                    action='CREATE',
                    entity_name='PurchaseOrder',
                    entity_id=po.id,
                    document_no=po.document_no,
                    reason=f"Generated Purchase Order for {supplier.legal_name} - Grand Total: ₹{po.grand_total}",
                    request=request
                )
                messages.success(request, f"Purchase Order [{po.document_no}] generated successfully for ₹{po.grand_total}!")
        except Exception as e:
            messages.error(request, f"Error generating PO: {str(e)}")

    return redirect('dashboard_procurement')


@staff_required
def dashboard_grn_create(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    if request.method == "POST":
        po_line = po.lines.first()
        if not po_line:
            messages.error(request, "This Purchase Order has no item lines to receive.")
            return redirect('dashboard_procurement')

        delivery_challan = request.POST.get('delivery_challan_no', '').strip()
        supplier_batch = request.POST.get('supplier_batch_no', '').strip()
        mfg_date = request.POST.get('manufacturing_date')
        exp_date = request.POST.get('expiry_date')
        received_qty_val = request.POST.get('received_qty')
        warehouse_id = request.POST.get('warehouse_id')
        bin_id = request.POST.get('bin_id') or None

        if not delivery_challan or not supplier_batch or not mfg_date or not exp_date or not received_qty_val or not warehouse_id:
            messages.error(request, "Delivery Challan, Batch No, Mfg Date, Expiry Date, Quantity, and Warehouse are mandatory.")
            return redirect('dashboard_procurement')

        try:
            received_qty = Decimal(str(received_qty_val))
            if received_qty <= Decimal('0'):
                messages.error(request, "Received quantity must be greater than zero.")
                return redirect('dashboard_procurement')
        except Exception:
            messages.error(request, "Invalid numerical received quantity.")
            return redirect('dashboard_procurement')

        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        bin_obj = StorageBin.objects.filter(id=bin_id).first() if bin_id else None

        try:
            with transaction.atomic():
                grn = GoodsReceiptNote(
                    po=po,
                    supplier=po.supplier,
                    warehouse=warehouse,
                    branch=po.branch,
                    delivery_challan_no=delivery_challan,
                    status='QUARANTINED',
                    created_by=request.user
                )
                grn.save()

                GoodsReceiptNoteLine.objects.create(
                    grn=grn,
                    po_line=po_line,
                    item=po_line.item,
                    supplier_batch_no=supplier_batch,
                    manufacturing_date=mfg_date,
                    expiry_date=exp_date,
                    received_qty=received_qty,
                    uom=po_line.uom,
                    bin=bin_obj,
                    created_by=request.user
                )

                post_grn_receipt(grn.id, request.user)

                po.status = 'PARTIALLY_RECEIVED' if received_qty < po_line.ordered_qty else 'COMPLETED'
                po.save(update_fields=['status'])

                audit_log_event(
                    user=request.user,
                    action='CREATE',
                    entity_name='GoodsReceiptNote',
                    entity_id=grn.id,
                    document_no=grn.document_no,
                    reason=f"Inward GRN receipt against PO {po.document_no} - Batch {supplier_batch} quarantined for QC",
                    request=request
                )
                messages.success(request, f"GRN [{grn.document_no}] received! Material placed into QUARANTINE Lot and QC Inspection Request created.")
        except Exception as e:
            messages.error(request, f"GRN Inward Error: {str(e)}")

    return redirect('dashboard_procurement')


@staff_required
def dashboard_po_approve(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    if request.method == "POST":
        try:
            check_prevent_self_approval(po, request.user)
            po.status = 'APPROVED'
            po.approved_by = request.user
            po.approved_at = timezone.now()
            po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
            audit_log_event(request.user, 'APPROVE', 'PurchaseOrder', po.id, po.document_no, reason="PO approved from ERP Dashboard")
            messages.success(request, f"Purchase Order {po.document_no} approved.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect('dashboard_procurement')


# ==========================================
# 4. MANUFACTURING & BMR BATCH RECORDS
# ==========================================
@staff_required
def dashboard_production(request):
    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('q', '').strip()

    orders = ProductionOrder.objects.select_related('product', 'bom', 'uom', 'target_warehouse', 'finished_lot').order_by('-created_at')
    
    active_count = ProductionOrder.objects.filter(status__in=['RELEASED', 'IN_PROGRESS']).count()
    completed_count = ProductionOrder.objects.filter(status='COMPLETED').count()
    total_count = ProductionOrder.objects.count()

    if status_filter == 'ACTIVE':
        orders = orders.filter(status__in=['RELEASED', 'IN_PROGRESS'])
    elif status_filter == 'COMPLETED':
        orders = orders.filter(status='COMPLETED')
    elif status_filter:
        orders = orders.filter(status=status_filter)

    if search:
        orders = orders.filter(
            Q(document_no__icontains=search) |
            Q(batch_no__icontains=search) |
            Q(product__name__icontains=search) |
            Q(product__item_code__icontains=search) |
            Q(bom__bom_code__icontains=search)
        )

    boms = BOMHeader.objects.filter(status='APPROVED').select_related('product')
    warehouses = Warehouse.objects.all()

    context = {
        'orders': orders[:50],
        'boms': boms,
        'warehouses': warehouses,
        'active_batches': active_count,
        'completed_batches': completed_count,
        'total_batches': total_count,
        'status_filter': status_filter,
        'search_query': search,
    }
    return render(request, 'dashboard/erp_production.html', context)


@staff_required
def dashboard_batch_complete(request, order_id):
    if request.method == "POST":
        actual_qty = request.POST.get('actual_produced_qty')
        scrap_qty = request.POST.get('scrap_qty', 0)

        if not actual_qty:
            messages.error(request, "Actual produced quantity is required.")
            return redirect('dashboard_production')

        try:
            actual_dec = Decimal(str(actual_qty))
            scrap_dec = Decimal(str(scrap_qty or 0))
        except Exception:
            messages.error(request, "Quantities must be valid numerical values.")
            return redirect('dashboard_production')

        if actual_dec <= Decimal('0'):
            messages.error(request, "Actual produced quantity must be greater than zero.")
            return redirect('dashboard_production')
        if scrap_dec < Decimal('0'):
            messages.error(request, "Scrap quantity cannot be negative.")
            return redirect('dashboard_production')

        try:
            order = complete_production_batch(order_id, actual_dec, scrap_dec, request.user)
            messages.success(request, f"Batch {order.batch_no} completed ({actual_qty} {order.uom.code}). Yield: {order.yield_percentage}%. Finished goods quarantined and submitted to QC.")
        except Exception as e:
            messages.error(request, f"Production Completion Error: {str(e)}")

    return redirect('dashboard_production')


# ==========================================
# 5. SALES, FEFO RESERVATION & DISPATCH
# ==========================================
@staff_required
def dashboard_sales(request):
    orders = SalesOrder.objects.select_related('customer', 'branch').prefetch_related('lines__product', 'lines__lot_allocations__lot').order_by('-created_at')
    invoices = SalesDispatchInvoice.objects.select_related('order', 'customer', 'branch').order_by('-invoice_date')[:50]

    context = {
        'orders': orders[:50],
        'invoices': invoices,
        'customers': CustomerMaster.objects.all(),
        'finished_goods': ItemMaster.objects.filter(item_type='FINISHED_GOOD', active_flag=True),
        'branches': Branch.objects.filter(is_active=True),
        'uoms': UnitOfMeasure.objects.all(),
        'today': timezone.now().date(),
    }
    return render(request, 'dashboard/erp_sales.html', context)


@staff_required
def dashboard_so_create(request):
    if request.method == "POST":
        customer_id = request.POST.get('customer_id')
        branch_id = request.POST.get('branch_id')
        order_date = request.POST.get('order_date') or timezone.now().date()
        delivery_date = request.POST.get('requested_delivery_date')

        product_id = request.POST.get('product_id')
        qty_val = request.POST.get('ordered_qty')
        price_val = request.POST.get('unit_price')
        tax_pct_val = request.POST.get('tax_percent', '12.00')
        discount_pct_val = request.POST.get('discount_percent', '0.00')

        if not customer_id or not product_id or not delivery_date or not qty_val or not price_val:
            messages.error(request, "Customer, Product, Delivery Date, Quantity, and Unit Price are required.")
            return redirect('dashboard_sales')

        try:
            qty = Decimal(str(qty_val))
            price = Decimal(str(price_val))
            tax_pct = Decimal(str(tax_pct_val or '0'))
            discount_pct = Decimal(str(discount_pct_val or '0'))
            if qty <= Decimal('0') or price <= Decimal('0'):
                messages.error(request, "Quantity and Unit Price must be greater than zero.")
                return redirect('dashboard_sales')
        except Exception:
            messages.error(request, "Invalid numeric input.")
            return redirect('dashboard_sales')

        customer = get_object_or_404(CustomerMaster, id=customer_id)
        product = get_object_or_404(ItemMaster, id=product_id)
        branch = Branch.objects.filter(id=branch_id).first() or Branch.objects.first()

        try:
            with transaction.atomic():
                so = SalesOrder(
                    customer=customer,
                    branch=branch,
                    order_date=order_date,
                    requested_delivery_date=delivery_date,
                    status='DRAFT',
                    created_by=request.user
                )
                so.save()

                line = SalesOrderLine(
                    order=so,
                    product=product,
                    ordered_qty=qty,
                    uom=product.base_uom,
                    unit_price=price,
                    discount_percent=discount_pct,
                    tax_percent=tax_pct,
                    created_by=request.user
                )
                line.save()

                base = line.ordered_qty * line.unit_price * (Decimal('1.00') - (line.discount_percent / Decimal('100.00')))
                tax = base * (line.tax_percent / Decimal('100.00'))
                so.subtotal = base
                so.tax_total = tax
                so.grand_total = base + tax
                so.save(update_fields=['subtotal', 'tax_total', 'grand_total'])

                audit_log_event(
                    user=request.user,
                    action='CREATE',
                    entity_name='SalesOrder',
                    entity_id=so.id,
                    document_no=so.document_no,
                    reason=f"Generated Customer Sales Order {so.document_no} for {customer.name} - Grand Total: ₹{so.grand_total}",
                    request=request
                )
                messages.success(request, f"Sales Order [{so.document_no}] created for {customer.name}! Now allocate stock using FEFO.")
        except Exception as e:
            messages.error(request, f"Sales Order Error: {str(e)}")

    return redirect('dashboard_sales')


@staff_required
def dashboard_so_approve_fefo(request, order_id):
    if request.method == "POST":
        try:
            order = approve_sales_order_and_reserve_fefo(order_id, request.user)
            messages.success(request, f"Sales Order {order.document_no} approved. Batches successfully reserved via FEFO.")
        except Exception as e:
            messages.error(request, f"Order Approval Error: {str(e)}")
    return redirect('dashboard_sales')


@staff_required
def dashboard_so_dispatch(request, order_id):
    if request.method == "POST":
        transporter = request.POST.get('transporter', 'Express Fleet').strip()
        docket_no = request.POST.get('docket_no', '').strip()
        eway_bill_no = request.POST.get('eway_bill_no', '').strip()
        vehicle_no = request.POST.get('vehicle_no', '').strip()

        if not transporter:
            messages.error(request, "Transporter / logistics carrier name is mandatory.")
            return redirect('dashboard_sales')
        if not eway_bill_no:
            messages.error(request, "Government E-Way Bill Number is mandatory for pharmaceutical dispatch.")
            return redirect('dashboard_sales')

        try:
            invoice = dispatch_sales_order(order_id, transporter, docket_no, eway_bill_no, vehicle_no, request.user)
            messages.success(request, f"Order dispatched! Tax Invoice: {invoice.document_no} | E-Way Bill: {eway_bill_no}")
        except Exception as e:
            messages.error(request, f"Dispatch Error: {str(e)}")
    return redirect('dashboard_sales')


@staff_required
def dashboard_invoice_view(request, invoice_id):
    invoice = get_object_or_404(SalesDispatchInvoice.objects.select_related('order', 'customer', 'branch', 'created_by'), id=invoice_id)
    allocations = SalesOrderLotAllocation.objects.filter(line__order=invoice.order).select_related('line__product', 'lot', 'lot__item', 'uom')
    context = {
        'invoice': invoice,
        'order': invoice.order,
        'customer': invoice.customer,
        'allocations': allocations,
        'today': timezone.now().date(),
    }
    return render(request, 'dashboard/tax_invoice.html', context)


# ==========================================
# 6. CRM DISTRIBUTION LEADS & PIPELINE
# ==========================================
@staff_required
def dashboard_crm(request):
    search = request.GET.get('q', '').strip()
    stage_filter = request.GET.get('stage', '').strip()
    type_filter = request.GET.get('type', '').strip()
    owner_filter = request.GET.get('owner', '').strip()
    task_filter = request.GET.get('task_status', 'ALL').strip()
    active_tab = request.GET.get('tab', 'leads').strip()

    today = timezone.now().date()

    # Base querysets
    all_leads_qs = Lead.objects.select_related('owner').prefetch_related('tasks').order_by('-created_at')
    leads_qs = all_leads_qs

    # Search & filters for Leads
    if search:
        leads_qs = leads_qs.filter(
            Q(organization_name__icontains=search) |
            Q(contact_person__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search) |
            Q(city__icontains=search) |
            Q(lead_id__icontains=search) |
            Q(tax_or_drug_license__icontains=search)
        )

    if stage_filter and stage_filter != 'ALL':
        leads_qs = leads_qs.filter(stage=stage_filter)

    if type_filter and type_filter != 'ALL':
        leads_qs = leads_qs.filter(lead_type=type_filter)

    if owner_filter and owner_filter != 'ALL':
        leads_qs = leads_qs.filter(owner_id=owner_filter)

    # Tasks Queryset & Filtering
    tasks_qs = FollowUpTask.objects.select_related('lead', 'assigned_to').order_by('due_date')
    if task_filter == 'PENDING':
        tasks_qs = tasks_qs.filter(status='PENDING')
    elif task_filter == 'COMPLETED':
        tasks_qs = tasks_qs.filter(status='COMPLETED')
    elif task_filter == 'DUE_TODAY':
        tasks_qs = tasks_qs.filter(due_date=today, status='PENDING')
    elif task_filter == 'OVERDUE':
        tasks_qs = tasks_qs.filter(due_date__lt=today, status='PENDING')

    # Metrics
    total_leads = Lead.objects.count()
    active_pipeline_count = Lead.objects.filter(stage__in=['NEW', 'CONTACTED', 'FOLLOW_UP', 'QUALIFIED', 'QUOTATION']).count()
    converted_count = Lead.objects.filter(stage='CONVERTED').count()
    lost_count = Lead.objects.filter(stage='LOST').count()
    conversion_rate = round((converted_count / total_leads * 100), 1) if total_leads > 0 else 0
    tasks_due_today = FollowUpTask.objects.filter(due_date=today, status='PENDING').count()
    tasks_overdue = FollowUpTask.objects.filter(due_date__lt=today, status='PENDING').count()
    total_tasks = FollowUpTask.objects.count()

    # Stage funnel counts for badges and quick filter
    stage_counts = {
        'NEW': Lead.objects.filter(stage='NEW').count(),
        'CONTACTED': Lead.objects.filter(stage='CONTACTED').count(),
        'FOLLOW_UP': Lead.objects.filter(stage='FOLLOW_UP').count(),
        'QUALIFIED': Lead.objects.filter(stage='QUALIFIED').count(),
        'QUOTATION': Lead.objects.filter(stage='QUOTATION').count(),
        'CONVERTED': Lead.objects.filter(stage='CONVERTED').count(),
        'LOST': Lead.objects.filter(stage='LOST').count(),
    }

    # Pipeline Kanban Columns
    pipeline_columns = [
        {
            'stage': 'NEW',
            'title': 'New Leads',
            'badge_color': '#3b82f6',
            'leads': all_leads_qs.filter(stage='NEW')[:20]
        },
        {
            'stage': 'CONTACTED',
            'title': 'Contacted',
            'badge_color': '#8b5cf6',
            'leads': all_leads_qs.filter(stage='CONTACTED')[:20]
        },
        {
            'stage': 'FOLLOW_UP',
            'title': 'Active Follow-Up',
            'badge_color': '#06b6d4',
            'leads': all_leads_qs.filter(stage='FOLLOW_UP')[:20]
        },
        {
            'stage': 'QUALIFIED',
            'title': 'Qualified',
            'badge_color': '#f59e0b',
            'leads': all_leads_qs.filter(stage='QUALIFIED')[:20]
        },
        {
            'stage': 'QUOTATION',
            'title': 'Quotation Sent',
            'badge_color': '#ec4899',
            'leads': all_leads_qs.filter(stage='QUOTATION')[:20]
        },
        {
            'stage': 'CONVERTED',
            'title': 'Converted (Won)',
            'badge_color': '#10b981',
            'leads': all_leads_qs.filter(stage='CONVERTED')[:20]
        },
    ]

    import_batches = LeadImportBatch.objects.select_related('created_by').order_by('-created_at')[:30]
    staff_users = User.objects.filter(is_active=True).order_by('username')
    all_leads_dropdown = Lead.objects.only('id', 'lead_id', 'organization_name').order_by('organization_name')

    context = {
        'leads': leads_qs[:150],
        'all_leads_dropdown': all_leads_dropdown,
        'tasks': tasks_qs[:100],
        'pipeline_columns': pipeline_columns,
        'import_batches': import_batches,
        'staff_users': staff_users,
        'stage_choices': Lead.STAGE_CHOICES,
        'lead_type_choices': Lead.LEAD_TYPE_CHOICES,
        'activity_choices': FollowUpTask.ACTIVITY_CHOICES,
        'task_priority_choices': (('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')),
        'task_status_choices': FollowUpTask.STATUS_CHOICES,
        # Analytics
        'total_leads': total_leads,
        'active_pipeline_count': active_pipeline_count,
        'converted_count': converted_count,
        'lost_count': lost_count,
        'conversion_rate': conversion_rate,
        'tasks_due_today': tasks_due_today,
        'tasks_overdue': tasks_overdue,
        'total_tasks': total_tasks,
        'stage_counts': stage_counts,
        # Current active states
        'today': today,
        'search_query': search,
        'stage_filter': stage_filter,
        'type_filter': type_filter,
        'owner_filter': owner_filter,
        'task_filter': task_filter,
        'active_tab': active_tab,
    }
    return render(request, 'dashboard/erp_crm.html', context)


@staff_required
def dashboard_lead_create(request):
    if request.method == "POST":
        org = request.POST.get('organization_name', '').strip()
        contact = request.POST.get('contact_person', '').strip()
        lead_type = request.POST.get('lead_type', 'DISTRIBUTOR')
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        territory = request.POST.get('territory', '').strip()
        tax_or_drug_license = request.POST.get('tax_or_drug_license', '').strip()
        source = request.POST.get('source', 'Field Inquiry').strip()
        stage = request.POST.get('stage', 'NEW')
        owner_id = request.POST.get('owner')
        next_follow_up_date = request.POST.get('next_follow_up_date') or None
        notes = request.POST.get('notes', '').strip()
        lost_reason = request.POST.get('lost_reason', '').strip()

        if not org or not contact or not city or not state:
            messages.error(request, "Organization Name, Contact Person, City, and State are required fields.")
            return redirect('/dashboard/crm/?tab=leads')

        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) < 10:
                messages.error(request, "Contact phone number must have at least 10 digits.")
                return redirect('/dashboard/crm/?tab=leads')

        owner = None
        if owner_id:
            try:
                owner = User.objects.get(id=owner_id)
            except User.DoesNotExist:
                pass

        try:
            lead = Lead(
                organization_name=org,
                contact_person=contact,
                lead_type=lead_type,
                phone=phone,
                email=email,
                city=city,
                state=state,
                territory=territory,
                tax_or_drug_license=tax_or_drug_license,
                source=source,
                stage=stage,
                owner=owner,
                next_follow_up_date=next_follow_up_date,
                notes=notes,
                lost_reason=lost_reason if stage == 'LOST' else '',
                created_by=request.user
            )
            lead.save()

            # Schedule initial follow-up task if requested
            task_activity = request.POST.get('initial_task_activity')
            task_due = request.POST.get('initial_task_due')
            task_purpose = request.POST.get('initial_task_purpose', '').strip()
            if task_activity and task_due and task_purpose:
                FollowUpTask.objects.create(
                    lead=lead,
                    activity_type=task_activity,
                    purpose=task_purpose,
                    due_date=task_due,
                    assigned_to=owner or request.user,
                    priority='MEDIUM',
                    created_by=request.user
                )

            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='Lead',
                entity_id=lead.id,
                document_no=lead.lead_id,
                reason=f"Registered new CRM Lead: {lead.organization_name}",
                request=request
            )
            messages.success(request, f"Lead [{lead.lead_id}] '{lead.organization_name}' created successfully!")
        except Exception as e:
            messages.error(request, f"Error creating lead: {str(e)}")

    return redirect('/dashboard/crm/?tab=leads')


@staff_required
def dashboard_lead_edit(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == "POST":
        org = request.POST.get('organization_name', '').strip()
        contact = request.POST.get('contact_person', '').strip()
        lead_type = request.POST.get('lead_type', 'DISTRIBUTOR')
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        territory = request.POST.get('territory', '').strip()
        tax_or_drug_license = request.POST.get('tax_or_drug_license', '').strip()
        source = request.POST.get('source', '').strip()
        stage = request.POST.get('stage', lead.stage)
        owner_id = request.POST.get('owner')
        next_follow_up_date = request.POST.get('next_follow_up_date') or None
        notes = request.POST.get('notes', '').strip()
        lost_reason = request.POST.get('lost_reason', '').strip()

        if not org or not contact or not city or not state:
            messages.error(request, "Organization Name, Contact Person, City, and State are required fields.")
            return redirect('/dashboard/crm/?tab=leads')

        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) < 10:
                messages.error(request, "Contact phone number must have at least 10 digits.")
                return redirect('/dashboard/crm/?tab=leads')

        if stage == 'LOST' and not lost_reason:
            messages.error(request, "A detailed lost reason is mandatory when marking a lead as LOST.")
            return redirect('/dashboard/crm/?tab=leads')

        owner = None
        if owner_id:
            try:
                owner = User.objects.get(id=owner_id)
            except User.DoesNotExist:
                pass

        try:
            lead.organization_name = org
            lead.contact_person = contact
            lead.lead_type = lead_type
            lead.phone = phone
            lead.email = email
            lead.city = city
            lead.state = state
            lead.territory = territory
            lead.tax_or_drug_license = tax_or_drug_license
            lead.source = source
            lead.stage = stage
            lead.owner = owner
            lead.next_follow_up_date = next_follow_up_date
            lead.notes = notes
            if stage == 'LOST':
                lead.lost_reason = lost_reason
            lead.updated_by = request.user
            lead.save()

            audit_log_event(
                user=request.user,
                action='UPDATE',
                entity_name='Lead',
                entity_id=lead.id,
                document_no=lead.lead_id,
                reason=f"Updated CRM Lead: {lead.organization_name}",
                request=request
            )
            messages.success(request, f"Lead [{lead.lead_id}] '{lead.organization_name}' updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating lead: {str(e)}")

    return redirect('/dashboard/crm/?tab=leads')


@staff_required
def dashboard_lead_stage_update(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == "POST":
        new_stage = request.POST.get('stage')
        lost_reason = request.POST.get('lost_reason', '').strip()
        auto_convert = request.POST.get('convert_customer') == '1'

        if new_stage == 'LOST' and not lost_reason:
            messages.error(request, "A detailed lost reason is mandatory when setting stage to LOST.")
            return redirect('/dashboard/crm/?tab=pipeline')

        if new_stage == 'CONVERTED' and auto_convert:
            return dashboard_lead_convert(request, lead_id)

        old_stage = lead.stage
        lead.stage = new_stage
        if new_stage == 'LOST':
            lead.lost_reason = lost_reason
        lead.updated_by = request.user
        lead.save()

        audit_log_event(
            user=request.user,
            action='UPDATE',
            entity_name='Lead',
            entity_id=lead.id,
            document_no=lead.lead_id,
            reason=f"Changed Lead stage from {old_stage} to {new_stage}",
            request=request
        )
        messages.success(request, f"Lead [{lead.lead_id}] stage updated to '{lead.get_stage_display()}'.")
    return redirect('/dashboard/crm/?tab=pipeline')


@staff_required
def dashboard_lead_convert(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == "POST":
        try:
            cust_code = DocumentSequence.get_next_number('CUST')
            cust_type = lead.lead_type if lead.lead_type in dict(CustomerMaster.CUSTOMER_TYPE_CHOICES) else 'DISTRIBUTOR'

            customer = CustomerMaster.objects.filter(name__iexact=lead.organization_name).first()
            if not customer:
                customer = CustomerMaster.objects.create(
                    customer_code=cust_code,
                    name=lead.organization_name,
                    customer_type=cust_type,
                    billing_address=f"{lead.city}, {lead.state}" if lead.city else "Registered Office",
                    shipping_address=f"{lead.city}, {lead.state}" if lead.city else "",
                    city=lead.city or "Unknown",
                    state=lead.state or "Unknown",
                    gstin=lead.tax_or_drug_license if 'GST' in lead.tax_or_drug_license.upper() else '',
                    drug_license_20b=lead.tax_or_drug_license,
                    contact_person=lead.contact_person,
                    email=lead.email,
                    phone=lead.phone,
                    credit_limit=Decimal('500000.00'),
                    payment_terms_days=30,
                    created_by=request.user
                )

            lead.stage = 'CONVERTED'
            lead.updated_by = request.user
            lead.save()

            audit_log_event(
                user=request.user,
                action='UPDATE',
                entity_name='Lead',
                entity_id=lead.id,
                document_no=lead.lead_id,
                reason=f"Converted Lead into Customer Master [{customer.customer_code}] {customer.name}",
                request=request
            )
            messages.success(request, f"Lead converted to Customer Master [{customer.customer_code}] '{customer.name}'!")
        except Exception as e:
            messages.error(request, f"Conversion error: {str(e)}")
    return redirect('/dashboard/crm/?tab=leads')


@staff_required
def dashboard_lead_delete(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if request.method == "POST":
        org_name = lead.organization_name
        doc_no = lead.lead_id
        lead_pk = lead.id
        lead.delete()

        audit_log_event(
            user=request.user,
            action='DELETE',
            entity_name='Lead',
            entity_id=lead_pk,
            document_no=doc_no,
            reason=f"Deleted Lead record: {org_name}",
            request=request
        )
        messages.success(request, f"Lead '{org_name}' deleted successfully!")
    return redirect('/dashboard/crm/?tab=leads')


@staff_required
def dashboard_task_create(request):
    if request.method == "POST":
        lead_id = request.POST.get('lead_id')
        activity_type = request.POST.get('activity_type', 'CALL')
        purpose = request.POST.get('purpose', '').strip()
        due_date = request.POST.get('due_date')
        assigned_to_id = request.POST.get('assigned_to')
        priority = request.POST.get('priority', 'MEDIUM')

        if not lead_id or not purpose or not due_date:
            messages.error(request, "Lead, Purpose, and Due Date are mandatory to schedule a task.")
            return redirect('/dashboard/crm/?tab=tasks')

        lead = get_object_or_404(Lead, id=lead_id)
        assigned_user = request.user
        if assigned_to_id:
            try:
                assigned_user = User.objects.get(id=assigned_to_id)
            except User.DoesNotExist:
                pass

        task = FollowUpTask.objects.create(
            lead=lead,
            activity_type=activity_type,
            purpose=purpose,
            due_date=due_date,
            assigned_to=assigned_user,
            priority=priority,
            created_by=request.user
        )

        # Update lead next follow-up date
        lead.next_follow_up_date = due_date
        lead.save(update_fields=['next_follow_up_date'])

        audit_log_event(
            user=request.user,
            action='CREATE',
            entity_name='FollowUpTask',
            entity_id=task.id,
            document_no=lead.lead_id,
            reason=f"Scheduled {activity_type} follow-up task for {lead.organization_name}",
            request=request
        )
        messages.success(request, f"Follow-up task scheduled for '{lead.organization_name}' on {due_date}!")
    return redirect('/dashboard/crm/?tab=tasks')


@staff_required
def dashboard_task_update_status(request, task_id):
    task = get_object_or_404(FollowUpTask, id=task_id)
    if request.method == "POST":
        new_status = request.POST.get('status')
        outcome_notes = request.POST.get('outcome_notes', '').strip()

        task.status = new_status
        if outcome_notes:
            task.outcome_notes = outcome_notes
        if new_status in ['COMPLETED', 'CANCELLED']:
            task.completed_at = timezone.now()
        task.updated_by = request.user
        task.save()

        audit_log_event(
            user=request.user,
            action='UPDATE',
            entity_name='FollowUpTask',
            entity_id=task.id,
            document_no=task.lead.lead_id,
            reason=f"Updated CRM task status to {new_status} with outcome notes",
            request=request
        )
        messages.success(request, f"Task status updated to '{task.get_status_display()}'.")
    return redirect('/dashboard/crm/?tab=tasks')


@staff_required
def dashboard_task_delete(request, task_id):
    task = get_object_or_404(FollowUpTask, id=task_id)
    if request.method == "POST":
        task_pk = task.id
        lead_name = task.lead.organization_name
        task.delete()

        audit_log_event(
            user=request.user,
            action='DELETE',
            entity_name='FollowUpTask',
            entity_id=task_pk,
            reason=f"Deleted follow-up task for {lead_name}",
            request=request
        )
        messages.success(request, f"Follow-up task for '{lead_name}' deleted successfully!")
    return redirect('/dashboard/crm/?tab=tasks')


@staff_required
def dashboard_crm_bulk_import(request):
    if request.method == "POST":
        csv_file = request.FILES.get('csv_file')
        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid CSV file (.csv format only).")
            return redirect('/dashboard/crm/?tab=batches')

        try:
            decoded_file = csv_file.read().decode('utf-8-sig', errors='ignore')
            reader = csv.DictReader(io.StringIO(decoded_file))
            rows_data = [row for row in reader]

            if not rows_data:
                messages.error(request, "Uploaded CSV file contains no data rows.")
                return redirect('/dashboard/crm/?tab=batches')

            result = process_lead_import_rows(rows_data, csv_file.name, request.user, commit=True)
            messages.success(
                request,
                f"Batch {result['batch_no']} completed! Valid leads imported: {result['valid_count']}, "
                f"Duplicates skipped: {result['duplicate_count']}, Errors: {result['error_count']}."
            )
        except Exception as e:
            messages.error(request, f"Import error: {str(e)}")

    return redirect('/dashboard/crm/?tab=batches')


@staff_required
def dashboard_crm_sample_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="celldus_crm_leads_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'organization_name', 'contact_person', 'lead_type', 'phone', 'email',
        'city', 'state', 'territory', 'source', 'notes'
    ])
    writer.writerow([
        'Apex Healthcare Distributors', 'Rajesh Sharma', 'DISTRIBUTOR', '9811122233', 'sales@apexpharma.com',
        'Mumbai', 'Maharashtra', 'West Region', 'Medical Expo 2026', 'Interested in Injectables & Oncology formulations'
    ])
    writer.writerow([
        'City Care Super Specialty Hospital', 'Dr. Sunita Rao', 'HOSPITAL', '9822233344', 'purchase@citycare.org',
        'Bengaluru', 'Karnataka', 'South Region', 'Field Inquiry', 'Requires bulk IV fluids and antibiotics supply'
    ])
    return response


# ==========================================
# 7. 21 CFR PART 11 AUDIT TRAIL INSPECTOR
# ==========================================
@staff_required
def dashboard_audit_trail(request):
    action_filter = request.GET.get('action', '')
    entity_filter = request.GET.get('entity', '')
    search = request.GET.get('q', '').strip()

    qs = AuditLog.objects.select_related('user', 'branch').order_by('-timestamp')

    if action_filter:
        qs = qs.filter(action=action_filter)
    if entity_filter:
        qs = qs.filter(entity_name__icontains=entity_filter)
    if search:
        qs = qs.filter(
            Q(document_no__icontains=search) |
            Q(reason__icontains=search) |
            Q(user__username__icontains=search) |
            Q(entity_name__icontains=search)
        )

    context = {
        'audit_logs': qs[:150],
        'total_logs': AuditLog.objects.count(),
        'action_filter': action_filter,
        'entity_filter': entity_filter,
        'search_query': search,
    }
    return render(request, 'dashboard/erp_audit_trail.html', context)


# ==========================================
# 8. MASTER DATA HUB
# ==========================================
@staff_required
def dashboard_masters(request):
    items = ItemMaster.objects.select_related('base_uom').order_by('item_code')
    suppliers = SupplierMaster.objects.order_by('supplier_code')
    customers = CustomerMaster.objects.order_by('-created_at')
    boms = BOMHeader.objects.select_related('product', 'batch_uom').order_by('bom_code')
    specs = QualitySpecification.objects.select_related('item').order_by('spec_code')
    warehouses = Warehouse.objects.select_related('branch').prefetch_related('bins').order_by('code')
    bins = StorageBin.objects.select_related('warehouse').order_by('-created_at')
    uoms = UnitOfMeasure.objects.all().order_by('code')
    branches = Branch.objects.filter(is_active=True).order_by('name')
    products = ItemMaster.objects.filter(item_type__in=['WIP', 'FINISHED_GOOD'])

    context = {
        'items': items,
        'suppliers': suppliers,
        'customers': customers,
        'boms': boms,
        'specs': specs,
        'warehouses': warehouses,
        'bins': bins,
        'uoms': uoms,
        'branches': branches,
        'products': products,
        'item_type_choices': ItemMaster.ITEM_TYPE_CHOICES,
        'storage_conditions': ItemMaster.STORAGE_CONDITIONS,
        'supplier_status_choices': SupplierMaster.STATUS_CHOICES,
        'customer_type_choices': CustomerMaster.CUSTOMER_TYPE_CHOICES,
        'warehouse_type_choices': Warehouse.WAREHOUSE_TYPE_CHOICES,
    }
    return render(request, 'dashboard/erp_masters.html', context)


@staff_required
def dashboard_item_create(request):
    if request.method == "POST":
        code = request.POST.get('item_code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        generic = request.POST.get('generic_name', '').strip()
        item_type = request.POST.get('item_type', 'FINISHED_GOOD')
        base_uom_id = request.POST.get('base_uom')
        storage = request.POST.get('storage_condition', 'ROOM_TEMP')
        shelf_life = int(request.POST.get('shelf_life_days', 730) or 730)
        tax_rate = Decimal(request.POST.get('tax_rate', '12.00') or '12.00')
        cost = Decimal(request.POST.get('standard_cost', '0.00') or '0.00')
        mrp = Decimal(request.POST.get('mrp', '0.00') or '0.00')

        if not code or not name or not base_uom_id:
            messages.error(request, "Item Code, Name, and Base UOM are required.")
            return redirect('dashboard_masters')

        if ItemMaster.objects.filter(item_code=code).exists():
            messages.warning(request, f"Item with code '{code}' already exists.")
            return redirect('dashboard_masters')

        uom = get_object_or_404(UnitOfMeasure, id=base_uom_id)

        try:
            item = ItemMaster.objects.create(
                item_code=code,
                name=name,
                generic_name=generic,
                item_type=item_type,
                base_uom=uom,
                storage_condition=storage,
                shelf_life_days=shelf_life,
                tax_rate=tax_rate,
                standard_cost=cost,
                mrp=mrp,
                created_by=request.user
            )

            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='ItemMaster',
                entity_id=item.id,
                document_no=item.item_code,
                reason=f"Registered Master Item [{item.item_code}] {item.name}",
                request=request
            )
            messages.success(request, f"Master Item [{item.item_code}] '{item.name}' created successfully!")
        except Exception as e:
            messages.error(request, f"Error creating item: {str(e)}")

    return redirect('dashboard_masters')


@staff_required
def dashboard_supplier_create(request):
    if request.method == "POST":
        code = request.POST.get('supplier_code', '').strip().upper()
        name = request.POST.get('legal_name', '').strip()
        gstin = request.POST.get('gstin', '').strip().upper()[:15]
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        contact = request.POST.get('contact_person', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        gmp_cert = request.POST.get('gmp_certificate_no', '').strip()
        status = request.POST.get('status', 'QUALIFIED')

        if not code or not name:
            messages.error(request, "Supplier Code and Legal Name are required.")
            return redirect('/dashboard/masters/?tab=suppliers')

        if SupplierMaster.objects.filter(supplier_code=code).exists():
            messages.warning(request, f"Supplier code '{code}' already exists.")
            return redirect('/dashboard/masters/?tab=suppliers')

        try:
            supplier = SupplierMaster.objects.create(
                supplier_code=code,
                legal_name=name,
                gstin=gstin,
                city=city,
                state=state,
                contact_person=contact,
                phone=phone,
                email=email,
                gmp_certificate_no=gmp_cert,
                status=status,
                created_by=request.user
            )

            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='SupplierMaster',
                entity_id=supplier.id,
                document_no=supplier.supplier_code,
                reason=f"Registered Qualified Supplier [{supplier.supplier_code}] {supplier.legal_name}",
                request=request
            )
            messages.success(request, f"Supplier [{supplier.supplier_code}] '{supplier.legal_name}' registered successfully!")
        except Exception as e:
            messages.error(request, f"Error registering supplier: {str(e)}")

    return redirect('/dashboard/masters/?tab=suppliers')


@staff_required
def dashboard_customer_create(request):
    if request.method == "POST":
        code = request.POST.get('customer_code', '').strip().upper()
        if not code:
            code = DocumentSequence.get_next_number('CUST')
        name = request.POST.get('name', '').strip()
        cust_type = request.POST.get('customer_type', 'DISTRIBUTOR')
        address = request.POST.get('billing_address', '').strip() or 'Registered Office'
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        gstin = request.POST.get('gstin', '').strip().upper()[:15]
        drug_license = request.POST.get('drug_license_20b', '').strip()
        contact = request.POST.get('contact_person', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        credit_limit = Decimal(request.POST.get('credit_limit', '500000.00') or '500000.00')

        if not name:
            messages.error(request, "Customer Name is required.")
            return redirect('dashboard_masters')

        if CustomerMaster.objects.filter(customer_code=code).exists():
            messages.warning(request, f"Customer code '{code}' already exists.")
            return redirect('dashboard_masters')

        try:
            customer = CustomerMaster.objects.create(
                customer_code=code,
                name=name,
                customer_type=cust_type,
                billing_address=address,
                city=city,
                state=state,
                gstin=gstin,
                drug_license_20b=drug_license,
                contact_person=contact,
                phone=phone,
                email=email,
                credit_limit=credit_limit,
                created_by=request.user
            )

            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='CustomerMaster',
                entity_id=customer.id,
                document_no=customer.customer_code,
                reason=f"Registered Licensed Customer [{customer.customer_code}] {customer.name}",
                request=request
            )
            messages.success(request, f"Customer [{customer.customer_code}] '{customer.name}' registered successfully!")
        except Exception as e:
            messages.error(request, f"Error registering customer: {str(e)}")

    return redirect('/dashboard/masters/?tab=customers')


@staff_required
def dashboard_customer_edit(request, customer_id):
    customer = get_object_or_404(CustomerMaster, id=customer_id)
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        cust_type = request.POST.get('customer_type', customer.customer_type)
        address = request.POST.get('billing_address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        gstin = request.POST.get('gstin', '').strip().upper()[:15]
        drug_license = request.POST.get('drug_license_20b', '').strip()
        contact = request.POST.get('contact_person', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        try:
            credit_limit = Decimal(request.POST.get('credit_limit', customer.credit_limit) or '0.00')
        except Exception:
            credit_limit = customer.credit_limit

        if not name:
            messages.error(request, "Customer Name is required.")
            return redirect('/dashboard/masters/?tab=customers')

        try:
            customer.name = name
            customer.customer_type = cust_type
            customer.billing_address = address
            customer.city = city
            customer.state = state
            customer.gstin = gstin
            customer.drug_license_20b = drug_license
            customer.contact_person = contact
            customer.phone = phone
            customer.email = email
            customer.credit_limit = credit_limit
            customer.updated_by = request.user
            customer.save()

            audit_log_event(
                user=request.user,
                action='UPDATE',
                entity_name='CustomerMaster',
                entity_id=customer.id,
                document_no=customer.customer_code,
                reason=f"Updated Licensed Customer [{customer.customer_code}] {customer.name}",
                request=request
            )
            messages.success(request, f"Customer [{customer.customer_code}] updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating customer: {str(e)}")

    return redirect('/dashboard/masters/?tab=customers')


@staff_required
def dashboard_customer_toggle_status(request, customer_id):
    customer = get_object_or_404(CustomerMaster, id=customer_id)
    if request.method == "POST":
        new_status = not customer.is_active
        customer.is_active = new_status
        customer.updated_by = request.user
        customer.save(update_fields=['is_active', 'updated_by', 'updated_at'])

        action_verb = "Reactivated" if new_status else "Deactivated"

        audit_log_event(
            user=request.user,
            action='UPDATE',
            entity_name='CustomerMaster',
            entity_id=customer.id,
            document_no=customer.customer_code,
            reason=f"{action_verb} Licensed Customer [{customer.customer_code}] {customer.name}",
            request=request
        )
        messages.success(request, f"Customer [{customer.customer_code}] '{customer.name}' {action_verb.lower()} successfully!")

    return redirect('/dashboard/masters/?tab=customers')


@staff_required
def dashboard_warehouse_create(request):
    if request.method == "POST":
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        wh_type = request.POST.get('warehouse_type', 'GENERAL')
        branch_id = request.POST.get('branch')

        if not code or not name:
            messages.error(request, "Warehouse Code and Name are required.")
            return redirect('/dashboard/masters/?tab=warehouses')

        branch = Branch.objects.filter(id=branch_id).first() or Branch.objects.first()

        if wh_type == 'COLD_CHAIN':
            t_min, t_max = Decimal('2.00'), Decimal('8.00')
        else:
            t_min, t_max = Decimal('15.00'), Decimal('25.00')

        try:
            wh = Warehouse.objects.create(
                code=code,
                name=name,
                warehouse_type=wh_type,
                temperature_min=t_min,
                temperature_max=t_max,
                humidity_max=Decimal('65.00'),
                branch=branch,
                created_by=request.user
            )
            messages.success(request, f"Warehouse [{wh.code}] '{wh.name}' created successfully!")
        except Exception as e:
            messages.error(request, f"Error creating warehouse: {str(e)}")

    return redirect('/dashboard/masters/?tab=warehouses')


@staff_required
def dashboard_storage_bin_create(request):
    if request.method == "POST":
        warehouse_id = request.POST.get('warehouse_id')
        zone = request.POST.get('zone', '').strip() or 'General Zone'
        bin_code = request.POST.get('bin_code', '').strip().upper()
        capacity = request.POST.get('capacity_kg')

        if not warehouse_id or not bin_code:
            messages.error(request, "Warehouse and Bin Code are required.")
            return redirect('/dashboard/masters/?tab=warehouses')

        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        if StorageBin.objects.filter(warehouse=warehouse, bin_code=bin_code).exists():
            messages.warning(request, f"Bin '{bin_code}' already exists in {warehouse.code}.")
            return redirect('/dashboard/masters/?tab=warehouses')

        try:
            cap_val = Decimal(str(capacity)) if capacity else None
            bin_obj = StorageBin.objects.create(
                warehouse=warehouse,
                zone=zone,
                bin_code=bin_code,
                capacity_kg=cap_val,
                created_by=request.user
            )
            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='StorageBin',
                entity_id=bin_obj.id,
                document_no=bin_obj.bin_code,
                reason=f"Created storage bin {bin_obj.bin_code} in {warehouse.code}",
                request=request
            )
            messages.success(request, f"Storage Bin [{bin_obj.bin_code}] added to warehouse '{warehouse.name}'.")
        except Exception as e:
            messages.error(request, f"Error creating storage bin: {str(e)}")

    return redirect('/dashboard/masters/?tab=warehouses')


@staff_required
def dashboard_bom_create(request):
    if request.method == "POST":
        bom_code = request.POST.get('bom_code', '').strip().upper()
        product_id = request.POST.get('product_id')
        batch_size = request.POST.get('batch_size')
        batch_uom_id = request.POST.get('batch_uom_id')
        effective_from = request.POST.get('effective_from') or timezone.now().date()

        if not bom_code or not product_id or not batch_size or not batch_uom_id:
            messages.error(request, "BOM Code, Product Formulation, Batch Size, and Batch UOM are required.")
            return redirect('/dashboard/masters/?tab=boms')

        if BOMHeader.objects.filter(bom_code=bom_code).exists():
            messages.warning(request, f"BOM Code '{bom_code}' already exists.")
            return redirect('/dashboard/masters/?tab=boms')

        product = get_object_or_404(ItemMaster, id=product_id)
        uom = get_object_or_404(UnitOfMeasure, id=batch_uom_id)

        latest_bom = BOMHeader.objects.filter(product=product).order_by('-version').first()
        next_version = (latest_bom.version + 1) if latest_bom else 1

        try:
            bom = BOMHeader.objects.create(
                bom_code=bom_code,
                product=product,
                version=next_version,
                batch_size=Decimal(str(batch_size)),
                batch_uom=uom,
                effective_from=effective_from,
                status='APPROVED',
                approved_by=request.user,
                approved_at=timezone.now(),
                created_by=request.user
            )
            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='BOMHeader',
                entity_id=bom.id,
                document_no=bom.bom_code,
                reason=f"Registered Master BOM [{bom.bom_code}] for {product.name}",
                request=request
            )
            messages.success(request, f"Master BOM [{bom.bom_code}] registered and approved for '{product.name}'!")
        except Exception as e:
            messages.error(request, f"Error creating BOM: {str(e)}")

    return redirect('/dashboard/masters/?tab=boms')


# ==========================================
# 9. PURCHASE ORDER PRINTABLE DOCUMENT
# ==========================================
@staff_required
def dashboard_po_view(request, po_id):
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'branch', 'created_by', 'approved_by').prefetch_related('lines__item', 'lines__uom'),
        id=po_id
    )
    context = {
        'po': po,
        'supplier': po.supplier,
        'branch': po.branch,
        'lines': po.lines.all(),
        'today': timezone.now().date(),
    }
    return render(request, 'dashboard/purchase_order.html', context)


# ==========================================
# 10. TAX INVOICES & BILLING SYSTEM
# ==========================================
@staff_required
def dashboard_invoices(request):
    search = request.GET.get('q', '').strip()
    eway_filter = request.GET.get('eway', '').strip()
    invoices_qs = SalesDispatchInvoice.objects.select_related('order', 'customer', 'branch', 'created_by').order_by('-invoice_date')

    if eway_filter == '1':
        invoices_qs = invoices_qs.exclude(eway_bill_no__isnull=True).exclude(eway_bill_no='')

    if search:
        invoices_qs = invoices_qs.filter(
            Q(document_no__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(order__document_no__icontains=search) |
            Q(transporter_name__icontains=search) |
            Q(eway_bill_no__icontains=search)
        )

    all_invoices = SalesDispatchInvoice.objects.all()
    total_invoiced_value = sum((inv.total_amount for inv in all_invoices), Decimal('0.00'))
    total_invoices_count = all_invoices.count()
    active_eway_count = all_invoices.exclude(eway_bill_no__isnull=True).exclude(eway_bill_no='').count()

    context = {
        'invoices': invoices_qs[:100],
        'search_query': search,
        'eway_filter': eway_filter,
        'total_invoiced_value': total_invoiced_value,
        'total_invoices_count': total_invoices_count,
        'active_eway_count': active_eway_count,
        'today': timezone.now().date(),
    }
    return render(request, 'dashboard/erp_invoices.html', context)


# ==========================================
# 11. EMPLOYEE CRM & WORKFORCE OPERATIONS
# ==========================================
@staff_required
def dashboard_employee(request):
    tab = request.GET.get('tab', 'directory')
    dept_filter = request.GET.get('dept', '')
    search = request.GET.get('q', '').strip()

    employees_qs = Employee.objects.select_related('branch', 'user').all().order_by('employee_code')

    if dept_filter:
        employees_qs = employees_qs.filter(department=dept_filter)
    if search:
        employees_qs = employees_qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(employee_code__icontains=search) |
            Q(designation__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )

    all_employees = Employee.objects.all()
    total_employees = all_employees.count()
    active_employees = all_employees.filter(is_active=True).count()
    tech_staff_count = all_employees.filter(department__in=['QA', 'QC', 'PRODUCTION']).count()
    sales_staff_count = all_employees.filter(department='SALES').count()
    total_payroll = sum((e.base_salary for e in all_employees if e.is_active), Decimal('0.00'))

    today = timezone.now().date()
    attendance_records = AttendanceRecord.objects.select_related('employee').filter(date=today)
    present_today_count = attendance_records.filter(status='PRESENT').count()

    leaves = LeaveApplication.objects.select_related('employee', 'branch').order_by('-created_at')[:50]
    pending_leaves_count = LeaveApplication.objects.filter(status='SUBMITTED').count()

    # Field Force (Sales & Marketing / Medical Representatives)
    field_force = Employee.objects.select_related('branch', 'user').filter(department='SALES')

    branches = Branch.objects.all()
    departments = Employee.DEPARTMENT_CHOICES

    context = {
        'employees': employees_qs,
        'all_employees': all_employees,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'tech_staff_count': tech_staff_count,
        'sales_staff_count': sales_staff_count,
        'total_payroll': total_payroll,
        'today': today,
        'attendance_records': attendance_records,
        'present_today_count': present_today_count,
        'leaves': leaves,
        'pending_leaves_count': pending_leaves_count,
        'field_force': field_force,
        'branches': branches,
        'departments': departments,
        'active_tab': tab,
        'dept_filter': dept_filter,
        'search_query': search,
    }
    return render(request, 'dashboard/erp_employee.html', context)


@staff_required
def dashboard_employee_create(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        department = request.POST.get('department', 'SALES')
        designation = request.POST.get('designation', '').strip()
        branch_id = request.POST.get('branch')
        joining_date = request.POST.get('joining_date')
        base_salary = request.POST.get('base_salary', '0.00')
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        bank_account = request.POST.get('bank_account_no', '').strip()
        bank_ifsc = request.POST.get('bank_ifsc', '').strip()
        employee_code = request.POST.get('employee_code', '').strip()

        if not first_name or not last_name or not designation or not branch_id or not joining_date:
            messages.error(request, "First Name, Last Name, Designation, Branch, and Joining Date are required.")
            return redirect('/dashboard/employee/?tab=directory')

        branch = get_object_or_404(Branch, id=branch_id)

        if not employee_code:
            dept_prefix = department[:3].upper()
            count = Employee.objects.filter(department=department).count() + 1
            employee_code = f"EMP-{dept_prefix}-{count:03d}"
            while Employee.objects.filter(employee_code=employee_code).exists():
                count += 1
                employee_code = f"EMP-{dept_prefix}-{count:03d}"

        try:
            emp = Employee.objects.create(
                employee_code=employee_code,
                first_name=first_name,
                last_name=last_name,
                department=department,
                designation=designation,
                branch=branch,
                joining_date=joining_date,
                base_salary=Decimal(base_salary or '0.00'),
                phone=phone,
                email=email,
                bank_account_no=bank_account,
                bank_ifsc=bank_ifsc,
                created_by=request.user
            )
            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='Employee',
                entity_id=str(emp.id),
                reason=f"Onboarded employee [{emp.employee_code}] {emp.first_name} {emp.last_name} in {emp.department}",
                request=request
            )
            messages.success(request, f"Employee [{emp.employee_code}] '{emp.first_name} {emp.last_name}' onboarded successfully!")
        except Exception as e:
            messages.error(request, f"Error onboarding employee: {str(e)}")

    return redirect('/dashboard/employee/?tab=directory')


@staff_required
def dashboard_employee_edit(request, employee_id):
    emp = get_object_or_404(Employee, id=employee_id)
    if request.method == "POST":
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        department = request.POST.get('department', emp.department)
        designation = request.POST.get('designation', '').strip()
        branch_id = request.POST.get('branch')
        base_salary = request.POST.get('base_salary', str(emp.base_salary))
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        bank_account = request.POST.get('bank_account_no', '').strip()
        bank_ifsc = request.POST.get('bank_ifsc', '').strip()

        if not first_name or not last_name or not designation:
            messages.error(request, "First Name, Last Name, and Designation are required.")
            return redirect('/dashboard/employee/?tab=directory')

        if branch_id:
            try:
                emp.branch = Branch.objects.get(id=branch_id)
            except Branch.DoesNotExist:
                pass

        try:
            emp.first_name = first_name
            emp.last_name = last_name
            emp.department = department
            emp.designation = designation
            emp.base_salary = Decimal(base_salary or '0.00')
            emp.phone = phone
            emp.email = email
            emp.bank_account_no = bank_account
            emp.bank_ifsc = bank_ifsc
            emp.updated_by = request.user
            emp.save()

            audit_log_event(
                user=request.user,
                action='UPDATE',
                entity_name='Employee',
                entity_id=str(emp.id),
                reason=f"Updated details for employee [{emp.employee_code}] {emp.first_name} {emp.last_name}",
                request=request
            )
            messages.success(request, f"Employee [{emp.employee_code}] updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating employee: {str(e)}")

    return redirect('/dashboard/employee/?tab=directory')


@staff_required
def dashboard_employee_toggle_status(request, employee_id):
    emp = get_object_or_404(Employee, id=employee_id)
    emp.is_active = not emp.is_active
    emp.updated_by = request.user
    emp.save()

    status_str = "Activated" if emp.is_active else "Deactivated"
    audit_log_event(
        user=request.user,
        action='UPDATE',
        entity_name='Employee',
        entity_id=str(emp.id),
        reason=f"{status_str} employee [{emp.employee_code}] {emp.first_name} {emp.last_name}",
        request=request
    )
    messages.success(request, f"Employee [{emp.employee_code}] has been {status_str.lower()}.")
    return redirect('/dashboard/employee/?tab=directory')


@staff_required
def dashboard_attendance_mark(request):
    if request.method == "POST":
        employee_id = request.POST.get('employee')
        date_str = request.POST.get('date') or str(timezone.now().date())
        status = request.POST.get('status', 'PRESENT')
        in_time = request.POST.get('in_time') or None
        out_time = request.POST.get('out_time') or None
        overtime = request.POST.get('overtime_hours', '0.00')

        emp = get_object_or_404(Employee, id=employee_id)
        try:
            record, created = AttendanceRecord.objects.get_or_create(
                employee=emp,
                date=date_str,
                defaults={
                    'status': status,
                    'in_time': in_time,
                    'out_time': out_time,
                    'overtime_hours': Decimal(overtime or '0.00'),
                    'created_by': request.user,
                    'updated_by': request.user,
                }
            )
            if not created:
                record.status = status
                record.in_time = in_time
                record.out_time = out_time
                record.overtime_hours = Decimal(overtime or '0.00')
                record.updated_by = request.user
                record.save()

            audit_log_event(
                user=request.user,
                action='CREATE' if created else 'UPDATE',
                entity_name='AttendanceRecord',
                entity_id=str(record.id),
                reason=f"Attendance logged for [{emp.employee_code}] on {date_str} as {status}",
                request=request
            )
            messages.success(request, f"Attendance marked for {emp.first_name} {emp.last_name} ({status})!")
        except Exception as e:
            messages.error(request, f"Error logging attendance: {str(e)}")

    return redirect('/dashboard/employee/?tab=attendance')


@staff_required
def dashboard_leave_create(request):
    if request.method == "POST":
        employee_id = request.POST.get('employee')
        leave_type = request.POST.get('leave_type', 'CASUAL')
        from_date = request.POST.get('from_date')
        to_date = request.POST.get('to_date')
        days_count = request.POST.get('days_count', '1.0')
        reason = request.POST.get('reason', '').strip()

        if not employee_id or not from_date or not to_date or not reason:
            messages.error(request, "Employee, dates, and reason are required.")
            return redirect('/dashboard/employee/?tab=leaves')

        emp = get_object_or_404(Employee, id=employee_id)
        try:
            leave = LeaveApplication.objects.create(
                employee=emp,
                branch=emp.branch,
                leave_type=leave_type,
                from_date=from_date,
                to_date=to_date,
                days_count=Decimal(days_count or '1.0'),
                reason=reason,
                status='SUBMITTED',
                created_by=request.user
            )
            audit_log_event(
                user=request.user,
                action='CREATE',
                entity_name='LeaveApplication',
                entity_id=str(leave.id),
                reason=f"Leave application [{leave.document_no}] submitted for {emp.first_name} ({leave_type})",
                request=request
            )
            messages.success(request, f"Leave application [{leave.document_no}] submitted successfully!")
        except Exception as e:
            messages.error(request, f"Error submitting leave: {str(e)}")

    return redirect('/dashboard/employee/?tab=leaves')


@staff_required
def dashboard_leave_action(request, leave_id, action):
    leave = get_object_or_404(LeaveApplication, id=leave_id)
    if action == 'approve':
        leave.status = 'APPROVED'
        leave.approved_by = request.user
        messages.success(request, f"Leave [{leave.document_no}] approved.")
    elif action == 'reject':
        leave.status = 'REJECTED'
        messages.warning(request, f"Leave [{leave.document_no}] rejected.")
    leave.updated_by = request.user
    leave.save()

    audit_log_event(
        user=request.user,
        action='UPDATE',
        entity_name='LeaveApplication',
        entity_id=str(leave.id),
        reason=f"Leave [{leave.document_no}] {leave.status} by {request.user.username}",
        request=request
    )
    return redirect('/dashboard/employee/?tab=leaves')


# ==========================================
# 12. FIELD FORCE SFA & EMPLOYEE TRACKING
# ==========================================

@login_required(login_url='dashboard_login')
def dashboard_field_portal(request):
    """
    Mobile-first Field Force SFA Portal for Medical Representatives.
    Includes GPS Attendance, Daily Beat Plan, Geofenced Detailing, and Offline Sync.
    """
    try:
        employee = get_authenticated_employee(request.user)
    except Exception:
        employee = None

    if not employee:
        if request.user.is_staff or request.user.is_superuser:
            b = Branch.objects.first()
            employee, _ = Employee.objects.get_or_create(
                user=request.user,
                defaults={
                    'employee_code': f"EMP-ADM-{request.user.id:03d}",
                    'first_name': request.user.first_name or request.user.username.capitalize(),
                    'last_name': request.user.last_name or 'Director',
                    'email': request.user.email or f"{request.user.username}@cellduspharma.com",
                    'department': 'SALES',
                    'designation': 'National Sales Director',
                    'sales_tier': 'NSM',
                    'joining_date': timezone.now().date(),
                    'is_active': True,
                    'branch': b,
                }
            )
        else:
            messages.error(request, "No active Employee profile linked to your user account. Please contact HR.")
            return redirect('dashboard_index')

    today = timezone.now().date()
    items = ItemMaster.objects.filter(is_active=True).order_by('name')
    customers = CustomerMaster.objects.filter(is_active=True).order_by('name')
    is_mgr = is_sales_manager(request.user) or is_system_or_hr_admin(request.user)

    context = {
        'employee': employee,
        'today': today,
        'items': items,
        'customers': customers,
        'is_manager_or_admin': is_mgr,
    }
    return render(request, 'dashboard/field_portal.html', context)


@login_required(login_url='dashboard_login')
def dashboard_field_tracking(request):
    """
    Manager Tracking Cockpit & Live Operations Center.
    Displays real-time geographic map, team status, and daily timeline stepper.
    """
    today = timezone.now().date()
    field_force = Employee.objects.select_related('territory', 'branch').filter(department='SALES').order_by('employee_code')
    attendances_today = AttendanceRecord.objects.filter(date=today)
    att_map = {a.employee_id: a for a in attendances_today}

    visits_today = FieldVisit.objects.select_related('customer', 'employee').filter(visit_date=today).order_by('-start_time')
    beat_plans_today = DailyBeatPlan.objects.filter(date=today)

    total_field_force = field_force.count()
    present_count = attendances_today.filter(check_in_time__isnull=False).count()
    in_progress_visits = visits_today.filter(visit_status='IN_PROGRESS').count()
    completed_visits = visits_today.filter(visit_status='COMPLETED').count()
    planned_visits = beat_plans_today.count()

    pob_agg = VisitOrderBooking.objects.filter(visit__visit_date=today).aggregate(models.Sum('booked_amount'))
    total_pob_amount = pob_agg['booked_amount__sum'] or Decimal('0.00')

    flagged_visits_count = visits_today.filter(is_flagged=True).count()
    flagged_att_count = attendances_today.filter(Q(check_in_status='REQUIRES_REVIEW') | Q(flag_reason__gt='')).count()
    exception_count = flagged_visits_count + flagged_att_count

    team_data = []
    for emp in field_force:
        att = att_map.get(emp.id)
        emp_visits = [v for v in visits_today if v.employee_id == emp.id]
        emp_planned = [b for b in beat_plans_today if b.employee_id == emp.id]
        is_active_visit = any(v.visit_status == 'IN_PROGRESS' for v in emp_visits)
        completed_v = sum(1 for v in emp_visits if v.visit_status == 'COMPLETED')
        pob_emp = sum((o.booked_amount for v in emp_visits for o in v.orders_booked.all()), Decimal('0.00'))

        att_status = 'NOT_CHECKED_IN'
        if att:
            att_status = att.check_in_status or ('PRESENT' if att.check_in_time else 'ABSENT')

        team_data.append({
            'employee': emp,
            'attendance': att,
            'attendance_status': att_status,
            'is_active_in_visit': is_active_visit,
            'planned_visits': len(emp_planned),
            'completed_visits': completed_v,
            'pob_booked_amount': pob_emp,
        })

    activity_feed = []
    for v in visits_today[:15]:
        activity_feed.append({
            'type': 'VISIT',
            'icon': 'fa-check' if v.visit_status == 'COMPLETED' else 'fa-stethoscope',
            'icon_bg': 'rgba(16, 185, 129, 0.15)' if not v.is_flagged else 'rgba(245, 158, 11, 0.15)',
            'icon_color': '#10b981' if not v.is_flagged else '#f59e0b',
            'employee_id': str(v.employee_id),
            'employee_name': f"{v.employee.first_name} {v.employee.last_name}",
            'title': f"{v.employee.first_name} {v.employee.last_name} @ {v.customer.name}",
            'subtitle': f"{v.customer.customer_type} | {v.customer.city or 'Field'}",
            'time': v.start_time.strftime('%H:%M') if v.start_time else '--:--',
            'status': v.visit_status,
            'is_flagged': v.is_flagged,
            'flag_reason': v.flag_reason,
            'timestamp': v.start_time or timezone.now()
        })

    for a in attendances_today.filter(check_in_time__isnull=False).select_related('employee')[:15]:
        activity_feed.append({
            'type': 'ATTENDANCE',
            'icon': 'fa-fingerprint',
            'icon_bg': 'rgba(79, 70, 229, 0.15)' if a.check_in_status == 'VALID' else 'rgba(244, 63, 94, 0.15)',
            'icon_color': '#6366f1' if a.check_in_status == 'VALID' else '#f43f5e',
            'employee_id': str(a.employee_id),
            'employee_name': f"{a.employee.first_name} {a.employee.last_name}",
            'title': f"{a.employee.first_name} {a.employee.last_name} Punched In",
            'subtitle': f"Mode: {a.work_mode} | {a.employee.territory.name if a.employee.territory else 'HQ'}",
            'time': timezone.localtime(a.check_in_time).strftime('%H:%M') if a.check_in_time else (str(a.in_time)[:5] if a.in_time else '--:--'),
            'status': a.check_in_status or 'PRESENT',
            'is_flagged': bool(a.flag_reason),
            'flag_reason': a.flag_reason,
            'timestamp': a.check_in_time or timezone.now()
        })
    activity_feed.sort(key=lambda x: x['timestamp'], reverse=True)

    territories = Territory.objects.all().order_by('name')

    stats = {
        'total_field_force': total_field_force,
        'present_count': present_count,
        'in_progress_visits': in_progress_visits,
        'completed_visits': completed_visits,
        'planned_visits': planned_visits,
        'total_pob_amount': total_pob_amount,
        'exception_count': exception_count,
    }

    context = {
        'stats': stats,
        'team_data': team_data,
        'recent_visits': visits_today[:15],
        'activity_feed': activity_feed,
        'territories': territories,
        'today': today,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', 'AIzaSyB51aYJiic2l5j0grNJsbd-WIoH2M-D0L0'),
    }
    return render(request, 'dashboard/field_tracking.html', context)


@login_required(login_url='dashboard_login')
def dashboard_field_reports(request):
    """
    Field Force SFA Performance, Coverage & Exception Reports.
    Includes CSV export capability.
    """
    tab = request.GET.get('tab', 'visits')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    territory_filter = request.GET.get('territory', '')

    today = timezone.now().date()
    start_date = today - timezone.timedelta(days=7)
    end_date = today

    if start_date_str:
        try:
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except Exception:
            pass
    if end_date_str:
        try:
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    visits_qs = FieldVisit.objects.select_related('customer', 'employee').prefetch_related('orders_booked').filter(
        visit_date__gte=start_date,
        visit_date__lte=end_date
    ).order_by('-visit_date', '-start_time')

    if territory_filter:
        visits_qs = visits_qs.filter(customer__territory_id=territory_filter)

    att_qs = AttendanceRecord.objects.select_related('employee').filter(
        date__gte=start_date,
        date__lte=end_date
    ).order_by('-date', '-check_in_time')

    exceptions = []
    for v in visits_qs.filter(is_flagged=True):
        exceptions.append({
            'date': v.visit_date,
            'type': 'VISIT_GEOFENCE_DEVIATION',
            'employee_name': f"{v.employee.first_name} {v.employee.last_name}",
            'employee_code': v.employee.employee_code,
            'target': v.customer.name,
            'distance': v.distance_to_target_meters,
            'reason': v.flag_reason or v.geofence_deviation_reason or 'Geofence exceeded',
        })

    for a in att_qs.filter(Q(check_in_status='REQUIRES_REVIEW') | Q(flag_reason__gt='')):
        exceptions.append({
            'date': a.date,
            'type': 'ATTENDANCE_FLAG',
            'employee_name': f"{a.employee.first_name} {a.employee.last_name}",
            'employee_code': a.employee.employee_code,
            'target': 'Check-In Punch',
            'distance': None,
            'reason': a.flag_reason or 'Suspicious location or mock GPS',
        })

    territories = Territory.objects.all().order_by('name')

    context = {
        'active_tab': tab,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'selected_territory': territory_filter,
        'territories': territories,
        'visits': visits_qs[:100],
        'attendance_list': att_qs[:100],
        'exceptions': exceptions,
        'exception_count': len(exceptions),
    }
    return render(request, 'dashboard/field_reports.html', context)


