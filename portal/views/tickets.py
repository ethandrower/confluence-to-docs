from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def tickets(request):
    return JsonResponse({'error': 'Ticket submission not yet available'}, status=501)


@require_http_methods(['GET'])
def ticket_detail(request, ticket_id):
    return JsonResponse({'error': 'Ticket submission not yet available'}, status=501)


@require_http_methods(['GET'])
def request_types(request):
    return JsonResponse({'results': []})
