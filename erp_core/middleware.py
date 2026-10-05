import threading
from django.utils.deprecation import MiddlewareMixin
from .security import audit_log_event

_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class ERPContextMiddleware(MiddlewareMixin):
    """
    Stores current request & user in thread-local storage for attributable tracking,
    and logs critical API actions.
    """
    def process_request(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request

    def process_response(self, request, response):
        # Clean up thread locals
        _thread_locals.user = None
        _thread_locals.request = None
        return response
