from django.conf import settings
from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)
    start_fuel_gallons = serializers.FloatField(
        required=False, default=0.0, min_value=0.0,
        max_value=settings.VEHICLE_RANGE_MILES / settings.VEHICLE_MPG,
    )
