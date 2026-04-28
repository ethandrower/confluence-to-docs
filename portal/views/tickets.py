import json

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


CATEGORY_LABELS = {
    'question': 'Question',
    'bug': 'Bug Report',
    'feature': 'Feature Request',
    'docs': 'Documentation Issue',
    'other': 'Other',
}


@csrf_exempt
@require_POST
def submit_ticket(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    category = data.get('category', 'other')
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    errors = {}
    if not name:
        errors['name'] = 'Name is required'
    if not email:
        errors['email'] = 'Email is required'
    if not subject:
        errors['subject'] = 'Subject is required'
    if not message:
        errors['message'] = 'Message is required'
    if errors:
        return JsonResponse({'errors': errors}, status=400)

    category_label = CATEGORY_LABELS.get(category, category)

    email_subject = f'[{category_label}] {subject}'
    email_body = (
        f'Name: {name}\n'
        f'Email: {email}\n'
        f'Category: {category_label}\n'
        f'\n'
        f'{message}'
    )

    try:
        msg = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SUPPORT_EMAIL],
            reply_to=[email],
        )
        msg.send()
    except Exception:
        return JsonResponse({'error': 'Failed to send message. Please try again.'}, status=500)

    return JsonResponse({'ok': True, 'message': 'Your request has been submitted.'})
