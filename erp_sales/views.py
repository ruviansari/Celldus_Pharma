from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import SalesOrder, SalesOrderLine, SalesOrderLotAllocation, SalesDispatchInvoice
from .serializers import SalesOrderSerializer, SalesOrderLineSerializer, SalesDispatchInvoiceSerializer
from .services import approve_sales_order_and_reserve_fefo, dispatch_sales_order
from erp_core.security import audit_log_event, check_prevent_self_approval


class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related('customer').prefetch_related('lines__product', 'lines__lot_allocations__lot').all()
    serializer_class = SalesOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'SalesOrder', order.id, order.document_no, request=self.request)

    @action(detail=True, methods=['post'])
    def approve_and_reserve(self, request, pk=None):
        """
        Validates credit limits, checks batch availability, and executes FEFO reservation.
        """
        order = approve_sales_order_and_reserve_fefo(pk, request.user)
        return Response({'status': 'Approved & FEFO Reserved', 'document_no': order.document_no})

    @action(detail=True, methods=['post'])
    def dispatch(self, request, pk=None):
        """
        Executes physical dispatch and generates tax invoice.
        Body: {"transporter": "...", "docket_no": "...", "eway_bill_no": "...", "vehicle_no": "..."}
        """
        transporter = request.data.get('transporter', 'Local Fleet')
        docket_no = request.data.get('docket_no', '')
        eway_bill_no = request.data.get('eway_bill_no', '')
        vehicle_no = request.data.get('vehicle_no', '')

        invoice = dispatch_sales_order(pk, transporter, docket_no, eway_bill_no, vehicle_no, request.user)
        return Response({
            'status': 'Dispatched',
            'invoice_no': invoice.document_no,
            'total_amount': str(invoice.total_amount)
        })


class SalesDispatchInvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SalesDispatchInvoice.objects.select_related('order', 'customer').all()
    serializer_class = SalesDispatchInvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
