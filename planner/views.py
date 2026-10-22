import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .routing import RouteError, plan_trip


def home(request):
    return render(request, "planner/index.html")


@require_GET
def health(request):
    return JsonResponse({"ok": True, "service": "fuel-route-planner", "maxRangeMiles": 500, "mpg": 10})


@require_POST
@csrf_exempt
def route(request):
    if len(request.body) > 12000:
        return JsonResponse({"ok": False, "error": "Request body is too large."}, status=413)
    try:
        payload = json.loads(request.body or b"{}")
        if not isinstance(payload, dict):
            raise RouteError("Send a JSON object with start and finish locations.", 400)
        result = plan_trip(payload.get("start", ""), payload.get("finish", ""))
        return JsonResponse({"ok": True, **result})
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Send valid JSON."}, status=400)
    except RouteError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=exc.status)
    except Exception:
        return JsonResponse({"ok": False, "error": "The route service encountered an unexpected error."}, status=500)
