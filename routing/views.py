import time

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import DOMAIN_ERRORS, domain_error_response
from .serializers import RouteRequestSerializer
from .services import get_cached_plan, plan_route


class RouteView(APIView):
    """Plan a truck route with the cheapest fuel stops. Accepts GET query params or a JSON POST body."""

    def get(self, request):
        return self._handle(request, request.query_params)

    def post(self, request):
        return self._handle(request, request.data)

    def _handle(self, request, data):
        started = time.perf_counter()
        serializer = RouteRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            payload, cached = plan_route(**serializer.validated_data)
        except DOMAIN_ERRORS as exc:
            return domain_error_response(exc)
        body = dict(payload)
        body["map_url"] = request.build_absolute_uri(reverse("route-map", args=[payload["route_id"]]))
        body["meta"] = {"cached": cached, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
        return Response(body)


def route_map(request, route_id):
    plan = get_cached_plan(route_id)
    if plan is None:
        raise Http404("Route not found or expired. Call /api/route/ again.")
    return render(request, "routing/map.html", {"plan": plan})
