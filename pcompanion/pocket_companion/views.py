from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from .chat import generate_with_model
import json

# Create your views here.
def landing(request):
    return render(request, 'pocket_companion/landing.html')

def chat_page(request):
    return render(request, 'pocket_companion/chat.html')

@csrf_protect
def process_message(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        data = json.loads(request.body)
        message = data.get('message')
        
        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)
            
        response = generate_with_model(
            model='mistral', 
            prompt=message,
            user=request.user if request.user.is_authenticated else None,
            session=request.session.session_key
        )
        
        return JsonResponse({'response': response})
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)