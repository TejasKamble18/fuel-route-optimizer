from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    return exception_handler(exc, context)
