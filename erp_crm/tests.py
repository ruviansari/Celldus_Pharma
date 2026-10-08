"""
Comprehensive Production-Grade Backend Test Suite for Celldus Pharma
Employee Tracking, Attendance, Geofencing, Beat Plans, Field Visits, and Anti-IDOR Security.
"""
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from erp_core.models import Branch, ERPUserRole
from erp_masters.models import UnitOfMeasure, ItemMaster, CustomerMaster, Territory
from erp_hr.models import Employee, AttendanceRecord
from .models import (
    DailyBeatPlan, FieldVisit, VisitProductDiscussed,
    VisitSampleGiven, VisitOrderBooking, EmployeeLocationEvent
)
from .geofence_service import calculate_haversine_distance, validate_geofence
from .tracking_service import TrackingService


class GeofenceEngineTests(TestCase):
    """Unit tests for the Haversine distance engine and geofence boundary validation."""

    def test_haversine_exact_match(self):
        # Same coordinates should return 0.0 meters
        dist = calculate_haversine_distance(28.6139, 77.2090, 28.6139, 77.2090)
        self.assertEqual(dist, 0.0)

    def test_haversine_known_distance(self):
        # Known points in Noida Sector 62: ~450 meters apart
        # Point A: 28.6280, 77.3649 (Electronic City Metro)
        # Point B: 28.6245, 77.3622
        dist = calculate_haversine_distance(28.6280, 77.3649, 28.6245, 77.3622)
        self.assertGreater(dist, 350.0)
        self.assertLess(dist, 550.0)

    def test_validate_geofence_inside_radius(self):
        # Target at 28.6280, 77.3649, User nearby (~25 meters)
        res = validate_geofence(
            user_lat=28.6281,
            user_lng=28.6249,
            user_accuracy=10.0,
            target_lat=28.6281,
            target_lng=28.6250,
            allowed_radius=150.0
        )
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['validation_status'], 'VALID')
        self.assertFalse(res['is_flagged'])
        self.assertLessEqual(res['distance_meters'], 150.0)

    def test_validate_geofence_outside_radius(self):
        # User 1.5 km away
        res = validate_geofence(
            user_lat=28.6139,
            user_lng=28.6200,
            user_accuracy=15.0,
            target_lat=28.6280,
            target_lng=28.6350,
            allowed_radius=150.0
        )
        self.assertFalse(res['is_valid'])
        self.assertEqual(res['validation_status'], 'OUTSIDE_GEOFENCE')
        self.assertTrue(res['is_flagged'])
        self.assertEqual(res['error_code'], 'OUTSIDE_GEOFENCE')

    def test_validate_geofence_poor_gps_accuracy(self):
        # User within distance but GPS accuracy is terrible (> 80m threshold)
        res = validate_geofence(
            user_lat=28.6280,
            user_lng=28.6250,
            user_accuracy=120.0,
            target_lat=28.6280,
            target_lng=28.6250,
            allowed_radius=150.0
        )
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['validation_status'], 'REQUIRES_REVIEW')
        self.assertTrue(res['is_flagged'])
        self.assertIn("Poor GPS accuracy", res['flag_reason'])

    def test_validate_geofence_target_has_no_coordinates(self):
        res = validate_geofence(
            user_lat=28.6280,
            user_lng=28.6250,
            user_accuracy=10.0,
            target_lat=None,
            target_lng=None,
            allowed_radius=150.0
        )
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['validation_status'], 'NO_COORDINATES')
        self.assertTrue(res['is_flagged'])


class EmployeeTrackingIntegrationTests(TestCase):
    """Integration tests for the complete Field Force API workflow."""

    def setUp(self):
        self.client = APIClient()

        # 1. Branch
        self.branch = Branch.objects.create(
            code="BR-DEL-01",
            name="Delhi Corporate Branch",
            address="Okhla Phase III",
            city="New Delhi",
            state="Delhi"
        )

        # 2. Users: Manager & Field Reps
        self.manager_user = User.objects.create_user(username="manager_asm", password="password123")
        self.rep1_user = User.objects.create_user(username="mr_rahul", password="password123")
        self.rep2_user = User.objects.create_user(username="mr_amit", password="password123")

        # 3. Territory
        self.territory = Territory.objects.create(
            code="TERR-NOIDA-01",
            name="Noida Central Pharma Zone",
            headquarters="Noida",
            state="Uttar Pradesh",
            branch=self.branch
        )

        # 4. Employees: Manager & Reps
        self.manager_emp = Employee.objects.create(
            employee_code="EMP-MGR-001",
            first_name="Vikram",
            last_name="Singh",
            user=self.manager_user,
            department="SALES",
            designation="Area Sales Manager",
            sales_tier="ASM",
            territory=self.territory,
            branch=self.branch,
            joining_date=timezone.now().date(),
            base_salary=Decimal('75000.00')
        )
        self.territory.manager = self.manager_emp
        self.territory.save()

        self.rep1_emp = Employee.objects.create(
            employee_code="EMP-MR-001",
            first_name="Rahul",
            last_name="Sharma",
            user=self.rep1_user,
            department="SALES",
            designation="Medical Representative",
            sales_tier="MR",
            manager=self.manager_emp,
            territory=self.territory,
            branch=self.branch,
            joining_date=timezone.now().date(),
            base_salary=Decimal('35000.00')
        )

        self.rep2_emp = Employee.objects.create(
            employee_code="EMP-MR-002",
            first_name="Amit",
            last_name="Verma",
            user=self.rep2_user,
            department="SALES",
            designation="Medical Representative",
            sales_tier="MR",
            manager=self.manager_emp,
            territory=self.territory,
            branch=self.branch,
            joining_date=timezone.now().date(),
            base_salary=Decimal('35000.00')
        )

        # 5. Customer (Doctor Clinic / Pharmacy) with known geofence
        # Location: Sector 63, Noida (28.6280, 77.3780)
        self.customer = CustomerMaster.objects.create(
            customer_code="CUST-NOIDA-001",
            name="Apollo Clinic & Pharmacy",
            customer_type="CLINIC",
            billing_address="Shop 4, H-Block, Sector 63",
            city="Noida",
            state="Uttar Pradesh",
            latitude=Decimal('28.628000'),
            longitude=Decimal('77.378000'),
            geofence_radius_meters=150,
            territory=self.territory
        )

        # 6. Product
        self.uom = UnitOfMeasure.objects.create(code="BOX", name="Box", symbol="bx")
        self.product = ItemMaster.objects.create(
            item_code="PROD-PAR-650",
            name="Celldus Paracetamol 650mg",
            item_type="FINISHED_GOOD",
            base_uom=self.uom,
            shelf_life_days=730,
            mrp=Decimal('45.00')
        )

    # --------------------------------------------------------------------------
    # ATTENDANCE TESTS
    # --------------------------------------------------------------------------

    def test_check_in_flow_success(self):
        self.client.force_authenticate(user=self.rep1_user)
        payload = {
            "lat": 28.628050,
            "lng": 77.378010,
            "accuracy": 12.5,
            "address": "Sector 63 Noida Metro Station",
            "work_mode": "FIELD",
            "battery": 85,
            "idempotency_key": "chk-001"
        }
        response = self.client.post('/api/v1/tracking/attendance/check-in/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['employee_code'], "EMP-MR-001")
        self.assertEqual(response.data['data']['status'], "PRESENT")

        # Verify database attendance
        att = AttendanceRecord.objects.get(employee=self.rep1_emp, date=timezone.now().date())
        self.assertIsNotNone(att.check_in_time)
        self.assertEqual(att.check_in_status, 'VALID')

        # Verify location event created
        event = EmployeeLocationEvent.objects.filter(employee=self.rep1_emp, event_type='CHECK_IN').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.idempotency_key, "chk-001")

    def test_duplicate_check_in_rejected(self):
        self.client.force_authenticate(user=self.rep1_user)
        payload = {"lat": 28.6280, "lng": 77.3780, "accuracy": 10.0}

        # First check-in
        res1 = self.client.post('/api/v1/tracking/attendance/check-in/', payload, format='json')
        self.assertEqual(res1.status_code, 200)

        # Second check-in on same day must be rejected
        res2 = self.client.post('/api/v1/tracking/attendance/check-in/', payload, format='json')
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.data['success'])
        self.assertEqual(res2.data['error_code'], "ALREADY_CHECKED_IN")

    def test_check_out_without_check_in_rejected(self):
        self.client.force_authenticate(user=self.rep1_user)
        payload = {"lat": 28.6280, "lng": 77.3780, "accuracy": 10.0}

        response = self.client.post('/api/v1/tracking/attendance/check-out/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error_code'], "CHECK_IN_REQUIRED")

    def test_check_out_flow_success(self):
        self.client.force_authenticate(user=self.rep1_user)

        # Check-in first
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})

        # Check-out
        res = self.client.post('/api/v1/tracking/attendance/check-out/', {
            "lat": 28.6285,
            "lng": 77.3785,
            "accuracy": 8.0,
            "address": "Noida HQ Office"
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['success'])

        att = AttendanceRecord.objects.get(employee=self.rep1_emp, date=timezone.now().date())
        self.assertIsNotNone(att.check_out_time)

    # --------------------------------------------------------------------------
    # BEAT PLAN & VISIT TESTS
    # --------------------------------------------------------------------------

    def test_visit_start_inside_geofence(self):
        self.client.force_authenticate(user=self.rep1_user)

        # 1. Must check in first
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})

        # 2. Start visit inside geofence (User is 15 meters away from Apollo Clinic)
        start_payload = {
            "customer_id": str(self.customer.id),
            "lat": 28.628100,
            "lng": 77.378100,
            "accuracy": 10.0,
            "idempotency_key": "v-start-001"
        }
        res = self.client.post('/api/v1/tracking/visits/start/', start_payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['data']['visit_status'], "IN_PROGRESS")
        self.assertEqual(res.data['data']['geofence_status'], "VALID")

        visit = FieldVisit.objects.get(id=res.data['data']['id'])
        self.assertEqual(visit.employee, self.rep1_emp)
        self.assertEqual(visit.customer, self.customer)

    def test_visit_start_outside_geofence_requires_deviation_reason(self):
        self.client.force_authenticate(user=self.rep1_user)
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})

        # User is 2 km away from Apollo Clinic (28.6400, 77.3900)
        outside_payload = {
            "customer_id": str(self.customer.id),
            "lat": 28.640000,
            "lng": 77.390000,
            "accuracy": 10.0,
            "deviation_reason": ""  # No deviation reason provided!
        }
        res = self.client.post('/api/v1/tracking/visits/start/', outside_payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data['success'])
        self.assertEqual(res.data['error_code'], "GEOFENCE_DEVIATION_REQUIRED")

        # Now supply deviation reason -> Should succeed and be flagged
        outside_payload['deviation_reason'] = "Doctor requested detailing at regional medical conference hall."
        res2 = self.client.post('/api/v1/tracking/visits/start/', outside_payload, format='json')
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.data['success'])
        self.assertEqual(res2.data['data']['geofence_status'], "OUTSIDE_GEOFENCE")
        self.assertTrue(res2.data['data']['is_flagged'])

    def test_concurrent_visit_prevention(self):
        self.client.force_authenticate(user=self.rep1_user)
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})

        # Start visit 1
        self.client.post('/api/v1/tracking/visits/start/', {
            "customer_id": str(self.customer.id),
            "lat": 28.6280,
            "lng": 77.3780
        })

        # Try to start another visit before finishing visit 1
        res = self.client.post('/api/v1/tracking/visits/start/', {
            "customer_id": str(self.customer.id),
            "lat": 28.6280,
            "lng": 77.3780
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['error_code'], "CONCURRENT_VISIT_PROHIBITED")

    def test_visit_end_flow_with_detailing_and_pob(self):
        self.client.force_authenticate(user=self.rep1_user)
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})

        start_res = self.client.post('/api/v1/tracking/visits/start/', {
            "customer_id": str(self.customer.id),
            "lat": 28.6280,
            "lng": 77.3780
        })
        visit_id = start_res.data['data']['id']

        # Complete visit
        end_payload = {
            "lat": 28.6280,
            "lng": 77.3780,
            "accuracy": 8.0,
            "doctor_response": "HIGHLY_INTERESTED",
            "remarks": "Dr. Sharma agreed to prescribe Paracetamol 650mg for viral fever cases.",
            "next_follow_up_date": str(timezone.now().date() + timedelta(days=14)),
            "products_discussed": [
                {"product_id": str(self.product.id), "is_core_focus": True, "feedback": "Positive"}
            ],
            "samples_given": [
                {"product_id": str(self.product.id), "quantity": 5, "batch_no": "LOT-2026-01"}
            ],
            "booked_amount": "4500.00"
        }
        end_res = self.client.post(f'/api/v1/tracking/visits/{visit_id}/end/', end_payload, format='json')
        self.assertEqual(end_res.status_code, 200)
        self.assertTrue(end_res.data['success'])
        self.assertEqual(end_res.data['data']['visit_status'], "COMPLETED")
        self.assertEqual(end_res.data['data']['doctor_response'], "HIGHLY_INTERESTED")

        # Verify relational tables
        self.assertEqual(VisitProductDiscussed.objects.filter(visit_id=visit_id).count(), 1)
        self.assertEqual(VisitSampleGiven.objects.filter(visit_id=visit_id).count(), 1)
        self.assertEqual(VisitOrderBooking.objects.filter(visit_id=visit_id).count(), 1)
        self.assertEqual(VisitOrderBooking.objects.get(visit_id=visit_id).booked_amount, Decimal('4500.00'))

    # --------------------------------------------------------------------------
    # ANTI-IDOR & AUTHORIZATION TESTS
    # --------------------------------------------------------------------------

    def test_anti_idor_rep_cannot_modify_other_rep_visit(self):
        # Rep 1 starts a visit
        self.client.force_authenticate(user=self.rep1_user)
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})
        start_res = self.client.post('/api/v1/tracking/visits/start/', {
            "customer_id": str(self.customer.id),
            "lat": 28.6280,
            "lng": 77.3780
        })
        visit_id = start_res.data['data']['id']

        # Rep 2 checks in and tries to END Rep 1's visit -> MUST BE 403 FORBIDDEN!
        self.client.force_authenticate(user=self.rep2_user)
        self.client.post('/api/v1/tracking/attendance/check-in/', {"lat": 28.6280, "lng": 77.3780})
        tamper_res = self.client.post(f'/api/v1/tracking/visits/{visit_id}/end/', {
            "lat": 28.6280,
            "lng": 77.3780,
            "remarks": "Tampered visit"
        })
        self.assertEqual(tamper_res.status_code, 403)

    def test_manager_authorization_for_team_tracking(self):
        # Field Rep attempts to call Live Team Tracking -> MUST BE FORBIDDEN
        self.client.force_authenticate(user=self.rep1_user)
        res_rep = self.client.get('/api/v1/tracking/employees/current/')
        self.assertEqual(res_rep.status_code, 403)

        # Sales Manager calls Live Team Tracking -> SUCCESS
        self.client.force_authenticate(user=self.manager_user)
        res_mgr = self.client.get('/api/v1/tracking/employees/current/')
        self.assertEqual(res_mgr.status_code, 200)
        self.assertTrue(res_mgr.data['success'])
        self.assertGreaterEqual(res_mgr.data['data']['total_subordinates'], 2)

    # --------------------------------------------------------------------------
    # OFFLINE BATCH SYNC & IDEMPOTENCY
    # --------------------------------------------------------------------------

    def test_offline_batch_sync_idempotency(self):
        self.client.force_authenticate(user=self.rep1_user)

        events_batch = {
            "events": [
                {
                    "idempotency_key": "off-001",
                    "event_type": "LOCATION_PING",
                    "lat": 28.6280,
                    "lng": 77.3780,
                    "accuracy": 15.0,
                    "battery": 78
                },
                {
                    "idempotency_key": "off-002",
                    "event_type": "LOCATION_PING",
                    "lat": 28.6290,
                    "lng": 77.3790,
                    "accuracy": 14.0,
                    "battery": 77
                }
            ]
        }

        # First sync
        res1 = self.client.post('/api/v1/tracking/events/sync/', events_batch, format='json')
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.data['data']['synced'], 2)
        self.assertEqual(res1.data['data']['skipped'], 0)

        # Second sync of the same batch -> Must skip duplicates
        res2 = self.client.post('/api/v1/tracking/events/sync/', events_batch, format='json')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.data['data']['synced'], 0)
        self.assertEqual(res2.data['data']['skipped'], 2)

    # --------------------------------------------------------------------------
    # FRONTEND DASHBOARD & END-TO-END WORKFLOW INTEGRATION TESTS
    # --------------------------------------------------------------------------

    def test_frontend_dashboard_views_authenticated(self):
        admin_user = User.objects.create_superuser(username="admin_tester", email="admin@celldus.com", password="password123")

        # 1. Field Portal View (Rep authenticated via session)
        self.client.force_login(self.rep1_user)
        res_portal = self.client.get('/dashboard/field/portal/')
        self.assertEqual(res_portal.status_code, 200)
        self.assertContains(res_portal, "Field Force SFA & Detailing Portal")

        # 2. Manager Cockpit View (Manager authenticated via session)
        self.client.force_login(self.manager_user)
        res_mgr = self.client.get('/dashboard/field/tracking/')
        self.assertEqual(res_mgr.status_code, 200)
        self.assertContains(res_mgr, "Real-time Geographic Field Deployment")

        # 3. SFA Reports View (Admin authenticated via session)
        self.client.force_login(admin_user)
        res_rep = self.client.get('/dashboard/field/reports/')
        self.assertEqual(res_rep.status_code, 200)
        self.assertContains(res_rep, "SFA Field Analytics & Compliance Reports")

    def test_frontend_dashboard_unauthenticated_redirect(self):
        self.client.logout()
        res = self.client.get('/dashboard/field/portal/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/dashboard/login/', res.url)

    def test_complete_end_to_end_sfa_lifecycle(self):
        """
        Tests complete real-world flow:
        Duty Check-in -> Beat Plan query -> Start Doctor Visit within geofence ->
        Product Detailing & POB Booking -> End Visit -> Check-out -> Verify reports
        """
        # Step 1: Rep 1 Checks In
        self.client.force_authenticate(user=self.rep1_user)
        check_in_res = self.client.post('/api/v1/tracking/attendance/check-in/', {
            "lat": 28.6280,
            "lng": 77.3780,
            "accuracy": 12.0,
            "work_mode": "FIELD"
        })
        self.assertEqual(check_in_res.status_code, 200)
        self.assertTrue(check_in_res.data['success'])

        # Step 2: Beat Plan query (create target for today first)
        beat_item = DailyBeatPlan.objects.create(
            employee=self.rep1_emp,
            date=timezone.now().date(),
            customer=self.customer,
            sequence=1,
            planned_time='10:00:00',
            priority='HIGH',
            status='PLANNED'
        )
        beat_res = self.client.get('/api/v1/tracking/beat-plan/today/')
        self.assertEqual(beat_res.status_code, 200)
        self.assertGreaterEqual(len(beat_res.data['data']['targets']), 1)

        # Step 3: Start Doctor Visit
        start_res = self.client.post('/api/v1/tracking/visits/start/', {
            "customer_id": str(self.customer.id),
            "beat_plan_id": str(beat_item.id),
            "lat": 28.6280,
            "lng": 77.3780,
            "accuracy": 10.0
        })
        self.assertEqual(start_res.status_code, 200)
        visit_id = start_res.data['data']['id']

        # Step 4: Detailing & End Visit with POB
        end_res = self.client.post(f'/api/v1/tracking/visits/{visit_id}/end/', {
            "lat": 28.6280,
            "lng": 77.3780,
            "accuracy": 10.0,
            "doctor_response": "HIGHLY_INTERESTED",
            "remarks": "Prescription assured for cardiology patients",
            "booked_amount": "8500.00",
            "products_discussed": [
                {"product_id": str(self.product.id), "is_core_focus": True, "feedback": "Very interested"}
            ],
            "samples_given": [
                {"product_id": str(self.product.id), "quantity": 3, "batch_no": "LOT-2026-01"}
            ]
        }, format='json')
        self.assertEqual(end_res.status_code, 200)
        self.assertEqual(end_res.data['data']['visit_status'], 'COMPLETED')

        # Step 5: Duty Check-out
        check_out_res = self.client.post('/api/v1/tracking/attendance/check-out/', {
            "lat": 28.6280,
            "lng": 77.3780,
            "accuracy": 12.0
        })
        self.assertEqual(check_out_res.status_code, 200)
        self.assertTrue(check_out_res.data['success'])

        # Step 6: Verify Manager Tracking Cockpit reflection
        self.client.force_authenticate(user=self.manager_user)
        cockpit_res = self.client.get('/api/v1/tracking/employees/current/')
        self.assertEqual(cockpit_res.status_code, 200)
        self.assertGreaterEqual(cockpit_res.data['data']['total_subordinates'], 1)

        # Step 7: Verify Reports reflection
        reports_res = self.client.get('/api/v1/tracking/reports/visits/')
        self.assertEqual(reports_res.status_code, 200)
        self.assertGreaterEqual(reports_res.data['data']['summary']['total_scheduled'], 1)

