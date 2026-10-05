from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from .models import Contact, Subscriber, Category, Product, Blog
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import user_passes_test
from django.core.files.storage import FileSystemStorage
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail




# =======================
# CONTEXT PROCESSOR
# =======================
def footer_blogs(request):
    return {"footer_blogs": Blog.objects.all().order_by("-created_at")[:2]}

# =======================
# PAGES
# =======================

def splashscreen(request):
    return render(request, 'splashscreen.html')


def home(request):
    products = Product.objects.all().select_related('category')
    return render(request, 'home_page.html', {
        "blogs": Blog.objects.all().order_by("-created_at")[:3],
        "products": products,
        "categories": Category.objects.all().order_by('name'),
        "total_products_count": products.count(),
        "total_categories_count": Category.objects.count(),
    })


def about(request):
    return render(request, 'about_us.html')


def product(request):
    categories = Category.objects.all().order_by('name')
    products = Product.objects.all().select_related('category')
    
    category_id = request.GET.get('category')
    selected_category = None
    if category_id:
        try:
            category_id = int(category_id)
            products = products.filter(category_id=category_id)
            selected_category = categories.filter(id=category_id).first()
        except (ValueError, TypeError):
            category_id = None

    search_q = request.GET.get('q', '').strip()
    if search_q:
        products = products.filter(Q(name__icontains=search_q) | Q(description__icontains=search_q))

    return render(request, 'product.html', {
        "products": products,
        "categories": categories,
        "selected_category_id": category_id,
        "selected_category": selected_category,
        "search_q": search_q,
    })


def our_blog(request):
    return render(request, 'our_blog.html', {
        "blogs": Blog.objects.all().order_by("-created_at")
    })


def faq(request):
    return render(request, 'faq.html')


def product_detail(request, id):
    product = get_object_or_404(Product, id=id)
    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
    return render(request, 'product_details.html', {
        "product": product,
        "related_products": related_products,
    })


def blog_details(request, id):
    blog = get_object_or_404(Blog, id=id)
    recent_blogs = Blog.objects.exclude(id=id).order_by("-created_at")[:4]
    categories = Category.objects.all().order_by('name')
    return render(request, 'blog_details.html', {
        "blog": blog,
        "recent_blogs": recent_blogs,
        "categories": categories,
    })


# =======================
# CONTACT PAGE 
# =======================


def contact_page(request):
    if request.method == "POST":
        Contact.objects.create(
            name=request.POST.get('name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            subject=request.POST.get('subject'),
            message=request.POST.get('message'),
        )
        return JsonResponse({"status": "success", "message": "Message sent successfully!"})

    return render(request, 'contact_us.html')
    if request.method == "POST":
        Contact.objects.create(
            name=request.POST.get('name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            subject=request.POST.get('subject'),
            message=request.POST.get('message'),
        )

        messages.success(request, "Message sent successfully!")
        return redirect('contact')

    return render(request, 'contact_us.html')
def subscribe(request):
    if request.method == "POST":
        email = request.POST.get('email')

        if not email:
            return JsonResponse({
                "status": "error",
                "message": "Email is required!"
            })

        if Subscriber.objects.filter(email=email).exists():
            return JsonResponse({
                "status": "error",
                "message": "Email already subscribed!"
            })

        Subscriber.objects.create(email=email)

        return JsonResponse({
            "status": "success",
            "message": "Subscribed successfully!"
        })

    return JsonResponse({"status": "error", "message": "Invalid request"})


# =======================
# DASHBOARD CUSTOM ADMIN PANEL VIEWS
# =======================

# Staff access check decorator
def staff_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff, login_url='dashboard_login')(view_func)

def dashboard_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('dashboard_index')
        
    if request.method == "POST":
        username_or_email = request.POST.get('username')
        password = request.POST.get('password')
        
        username = username_or_email
        # If user logs in with email, find their username first
        if "@" in username_or_email:
            try:
                user_obj = User.objects.get(email=username_or_email)
                username = user_obj.username
            except User.DoesNotExist:
                pass
                
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('dashboard_index')
            else:
                messages.error(request, "Access Denied: Staff accounts only.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'login.html')

def dashboard_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have successfully logged out.")
    return redirect('dashboard_login')

@staff_required
def dashboard_index(request):
    from erp_masters.models import ItemMaster, SupplierMaster, CustomerMaster
    from erp_inventory.models import InventoryLot
    from erp_procurement.models import PurchaseOrder
    from erp_manufacturing.models import ProductionOrder
    from erp_quality.models import QCInspectionRequest, QualityDeviation
    from erp_core.models import AuditLog
    from erp_crm.models import Lead

    context = {
        # Core Website & Product Stats
        "total_products": Product.objects.count(),
        "total_categories": Category.objects.count(),
        "total_inquiries": Contact.objects.count(),
        "total_subscribers": Subscriber.objects.count(),
        "recent_inquiries": Contact.objects.all().order_by('-created_at')[:5],

        # Enterprise Pharma ERP Metrics
        "total_items": ItemMaster.objects.count(),
        "quarantine_lots_count": InventoryLot.objects.filter(status='QUARANTINE').count(),
        "available_lots_count": InventoryLot.objects.filter(status='AVAILABLE').count(),
        "active_pos_count": PurchaseOrder.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count(),
        "active_batches_count": ProductionOrder.objects.filter(status__in=['RELEASED', 'IN_PROGRESS']).count(),
        "pending_qc_count": QCInspectionRequest.objects.exclude(status='DISPOSITIONED').count(),
        "open_deviations_count": QualityDeviation.objects.filter(status='OPEN').count(),
        "total_leads_count": Lead.objects.count(),

        # Recent 21 CFR Part 11 Audit Trail Logs
        "recent_audits": AuditLog.objects.select_related('user').order_by('-timestamp')[:8],
    }
    return render(request, 'dashboard/index.html', context)

@staff_required
def dashboard_categories(request):
    categories = Category.objects.all().order_by('-created_at')
    return render(request, 'dashboard/categories.html', {"categories": categories})

@staff_required
def dashboard_category_add(request):
    if request.method == "POST":
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        if Category.objects.filter(name__iexact=name).exists():
            messages.warning(request, "Category already exists!")
        else:
            Category.objects.create(name=name, description=description)
            messages.success(request, "Category created successfully!")
    return redirect('dashboard_categories')

@staff_required
def dashboard_category_edit(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == "POST":
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        if Category.objects.filter(name__iexact=name).exclude(id=id).exists():
            messages.warning(request, "Another category with this name already exists!")
        else:
            category.name = name
            category.description = description
            category.save()
            messages.success(request, "Category updated successfully!")
    return redirect('dashboard_categories')

@staff_required
def dashboard_category_delete(request, id):
    if request.method == "POST":
        category = Category.objects.filter(id=id).first()
        if category:
            category.delete()
            messages.success(request, "Category deleted successfully!")
        else:
            messages.info(request, "Category has already been deleted or does not exist.")
    return redirect('dashboard_categories')

@staff_required
def dashboard_products(request):
    products = Product.objects.all().order_by('-created_at').select_related('category')
    categories = Category.objects.all()
    return render(request, 'dashboard/products.html', {
        "products": products,
        "categories": categories
    })

@staff_required
def dashboard_product_add(request):
    if request.method == "POST":
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        description = request.POST.get('description')
        image_file = request.FILES.get('image_file')
        
        # New fields
        price = request.POST.get('price') or 0.00
        selling_price = request.POST.get('selling_price') or 0.00
        size = request.POST.get('size', '')
        stock = request.POST.get('stock') or 0
        specification = request.POST.get('specification', '')
        
        category = get_object_or_404(Category, id=category_id)
        image_path = 'images/products/default.png'
        
        if image_file:
            from django.conf import settings
            import os
            
            static_products_dir = os.path.join(settings.BASE_DIR, 'static', 'images', 'products')
            os.makedirs(static_products_dir, exist_ok=True)
            
            fs = FileSystemStorage(location=static_products_dir)
            filename = fs.save(image_file.name, image_file)
            image_path = f'images/products/{filename}'
            
        Product.objects.create(
            name=name,
            category=category,
            description=description,
            image=image_path,
            price=price,
            selling_price=selling_price,
            size=size,
            stock=stock,
            specification=specification
        )
        messages.success(request, "Product added successfully!")
    return redirect('dashboard_products')

@staff_required
def dashboard_product_edit(request, id):
    product = get_object_or_404(Product, id=id)
    if request.method == "POST":
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        description = request.POST.get('description')
        image_file = request.FILES.get('image_file')
        
        # New fields
        price = request.POST.get('price') or 0.00
        selling_price = request.POST.get('selling_price') or 0.00
        size = request.POST.get('size', '')
        stock = request.POST.get('stock') or 0
        specification = request.POST.get('specification', '')
        
        category = get_object_or_404(Category, id=category_id)
        product.name = name
        product.category = category
        product.description = description
        product.price = price
        product.selling_price = selling_price
        product.size = size
        product.stock = stock
        product.specification = specification
        
        if image_file:
            from django.conf import settings
            import os
            
            static_products_dir = os.path.join(settings.BASE_DIR, 'static', 'images', 'products')
            os.makedirs(static_products_dir, exist_ok=True)
            
            fs = FileSystemStorage(location=static_products_dir)
            filename = fs.save(image_file.name, image_file)
            product.image = f'images/products/{filename}'
            
        product.save()
        messages.success(request, "Product updated successfully!")
    return redirect('dashboard_products')

@staff_required
def dashboard_product_delete(request, id):
    if request.method == "POST":
        product = Product.objects.filter(id=id).first()
        if product:
            product.delete()
            messages.success(request, "Product deleted successfully!")
        else:
            messages.info(request, "Product has already been deleted or does not exist.")
    return redirect('dashboard_products')

@staff_required
def dashboard_customers(request):
    search_query = request.GET.get('q', '').strip()
    inquiries_qs = Contact.objects.all().order_by('-created_at')
    subscribers_qs = Subscriber.objects.all().order_by('-created_at')

    total_inquiries = inquiries_qs.count()
    total_subscribers = subscribers_qs.count()

    if search_query:
        inquiries_qs = inquiries_qs.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(subject__icontains=search_query) |
            Q(message__icontains=search_query)
        )
        subscribers_qs = subscribers_qs.filter(email__icontains=search_query)

    return render(request, 'dashboard/customers.html', {
        "inquiries": inquiries_qs[:100],
        "subscribers": subscribers_qs[:100],
        "total_inquiries": total_inquiries,
        "total_subscribers": total_subscribers,
        "search_query": search_query,
    })

@staff_required
def dashboard_inquiry_delete(request, id):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'
    if request.method == "POST":
        inquiry = Contact.objects.filter(id=id).first()
        if inquiry:
            inquiry.delete()
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'Inquiry message deleted successfully!'})
            messages.success(request, "Inquiry message deleted successfully!")
        else:
            if is_ajax:
                return JsonResponse({'status': 'info', 'message': 'Inquiry has already been deleted or does not exist.'})
            messages.info(request, "Inquiry has already been deleted or does not exist.")
    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
    return redirect('dashboard_customers')

@staff_required
def dashboard_subscriber_delete(request, id):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'
    if request.method == "POST":
        sub = Subscriber.objects.filter(id=id).first()
        if sub:
            sub.delete()
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'Subscriber removed successfully!'})
            messages.success(request, "Subscriber removed successfully!")
        else:
            if is_ajax:
                return JsonResponse({'status': 'info', 'message': 'Subscriber has already been deleted or does not exist.'})
            messages.info(request, "Subscriber has already been deleted or does not exist.")
    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
    return redirect('dashboard_customers')

@staff_required
def dashboard_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'dashboard/users.html', {"users": users})

@staff_required
def dashboard_user_add(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        is_superuser = request.POST.get('is_superuser') == 'on'
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('dashboard_users')
            
        if User.objects.filter(username=username).exists():
            messages.warning(request, "Username already exists!")
            return redirect('dashboard_users')
            
        if User.objects.filter(email=email).exists():
            messages.warning(request, "Email address already registered!")
            return redirect('dashboard_users')
            
        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = True
        if is_superuser:
            user.is_superuser = True
        user.save()
        messages.success(request, f"Staff user '{username}' created successfully!")
    return redirect('dashboard_users')

@staff_required
def dashboard_user_toggle(request, id):
    if request.method == "POST":
        target_user = get_object_or_404(User, id=id)
        if target_user == request.user:
            messages.error(request, "You cannot modify your own access!")
        else:
            target_user.is_staff = not target_user.is_staff
            target_user.save()
            messages.success(request, f"Access toggled for user '{target_user.username}'.")
    return redirect('dashboard_users')

@staff_required
def dashboard_user_delete(request, id):
    if request.method == "POST":
        target_user = get_object_or_404(User, id=id)
        if target_user == request.user:
            messages.error(request, "You cannot delete your own account!")
        else:
            target_user.delete()
            messages.success(request, f"User account '{target_user.username}' deleted successfully.")
    return redirect('dashboard_users')

@staff_required
def dashboard_user_change_password(request, id):
    target_user = get_object_or_404(User, id=id)
    if request.method == "POST":
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
        else:
            target_user.set_password(password)
            target_user.save()
            messages.success(request, f"Password updated successfully for {target_user.username}.")
    return redirect('dashboard_users')


# ============================================
# CUSTOM PASSWORD RESET VIEWS (With SMTP Debug)
# ============================================

def custom_forgot_password(request):
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        print("SUBMITTED EMAIL:", repr(email), flush=True)
        print("ALL DB EMAILS:", [u.email for u in User.objects.all()], flush=True)
        user = User.objects.filter(email__iexact=email).first()
        if user:
            # Generate tokens using standard Django library
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Formulate full absolute reset link
            protocol = 'https' if request.is_secure() else 'http'
            domain = request.get_host()
            reset_url = f"{protocol}://{domain}/password-reset-confirm/{uid}/{token}/"
            
            subject = "Password Reset Request - Celldus Pharma"
            message_body = (
                f"Hello {user.username},\n\n"
                f"You are receiving this email because a password reset request was submitted for your account at Celldus Pharma.\n\n"
                f"Please click the link below to reset your password:\n\n"
                f"{reset_url}\n\n"
                f"If you did not request a password reset, no further action is required.\n\n"
                f"Best regards,\n"
                f"The Celldus Pharma Team"
            )
            
            try:
                send_mail(
                    subject,
                    message_body,
                    'neelam@rakle.in',
                    [user.email],
                    fail_silently=False,
                )
                messages.success(request, f"Password reset email successfully sent to {email}!")
                return render(request, 'password_reset_done.html')
            except Exception as e:
                # Capture and log exact SMTP network/auth details to display on screen for easy verification
                print("SMTP EXCEPTION OCCURRED:", str(e), flush=True)
                messages.error(request, f"SMTP Error sending email: {str(e)}")
        else:
            messages.warning(request, "No account was found with that email address. Please make sure spelling is correct.")
            
    return render(request, 'password_reset.html')


def custom_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        validlink = True
        if request.method == "POST":
            new_password = request.POST.get('new_password1')
            confirm_password = request.POST.get('new_password2')
            
            if not new_password or new_password != confirm_password:
                messages.error(request, "Passwords do not match!")
            elif len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
            else:
                user.set_password(new_password)
                user.save()
                messages.success(request, "Your password has been successfully reset! You can now log in.")
                return render(request, 'password_reset_complete.html')
    else:
        validlink = False
        
    return render(request, 'password_reset_confirm.html', {
        'validlink': validlink,
        'uidb64': uidb64,
        'token': token
    })
