from django.http import JsonResponse
from django.conf import settings

def api_key_required(view_func):
    def wrapper(request, *args, **kwargs):
        api_key = request.headers.get("X-API-KEY")
        if api_key != getattr(settings, "INTERNAL_API_KEY", None):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper