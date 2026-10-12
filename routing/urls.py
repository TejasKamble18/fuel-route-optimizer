from django.urls import path

from .views import RouteView, route_map

urlpatterns = [
    path("route/", RouteView.as_view(), name="route"),
    path("route/<str:route_id>/map/", route_map, name="route-map"),
]
