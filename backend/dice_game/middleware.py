from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
import logging
import re

logger = logging.getLogger('django')

class NormalizePathMiddleware(MiddlewareMixin):
    """Middleware to normalize double slashes in paths to single slashes."""
    def process_request(self, request):
        if '//' in request.path:
            old_path = request.path
            new_path = re.sub(r'/+', '/', request.path)
            request.path = new_path
            
            if hasattr(request, 'path_info'):
                request.path_info = re.sub(r'/+', '/', request.path_info)
            
            logger.info(f"Normalized path from {old_path} to {new_path}")
        return None

class DisableCSRFMiddleware(MiddlewareMixin):
    """Middleware to disable CSRF for specific API endpoints."""
    def process_request(self, request):
        # Always normalize for the check
        normalized_path = re.sub(r'/+', '/', request.path)
        
        # Log all POST requests to see what's being blocked
        if request.method in ['POST', 'DELETE', 'PUT', 'PATCH']:
            logger.info(f"CSRF Check for: {normalized_path} (Method: {request.method})")
        
        # List of paths to exempt from CSRF (using regex for flexibility)
        exempt_patterns = [
            r'^/ws/.*',
            r'^/api/auth/login/.*',
            r'^/api/auth/register/.*',
            r'^/api/auth/otp/.*',
            r'^/api/game/bet/last/.*',
            r'^/api/game/bet/.*',
            r'^/game/bet/.*',
            r'^/api/game/prediction/.*',
            r'^/api/game/round/.*predictions/.*',
            r'^/game-admin/login/.*',
            r'^/game-admin/.*',
        ]
        
        is_exempt = False
        for pattern in exempt_patterns:
            if re.match(pattern, normalized_path):
                is_exempt = True
                break
        
        if is_exempt:
            # This flag tells Django's CSRF middleware to skip the check
            setattr(request, '_dont_enforce_csrf_checks', True)
            logger.info(f"CSRF exempt: {normalized_path}")
        
        return None
