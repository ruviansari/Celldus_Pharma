from .models import Blog

def footer_blogs(request):
    return {"footer_blogs": Blog.objects.all().order_by('-created_at')[:2]}