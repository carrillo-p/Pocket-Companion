import json
import os
import requests
import time
import re
import PyPDF2

from datetime import datetime
from dotenv import load_dotenv
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import Dict, Union, Optional, List, Tuple
from urllib.parse import quote

from .models import ConversationTracker

load_dotenv()

class ScryfallAPI:
    def __init__(self):
        self.base_url = "https://api.scryfall.com"

    def get_card_info(self, card_name: str) -> Dict:
        """Fetch card information from Scryfall"""
        escaped_name = quote(card_name.strip())
        url = f"{self.base_url}/cards/named?fuzzy={escaped_name}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None

    def get_card_rulings(self, card_name: str) -> List[Dict]:
        """Fetch card rulings from Scryfall"""
        card_info = self.get_card_info(card_name)
        if not card_info:
            return []
        rulings_url = card_info.get('rulings_uri')
        if rulings_url:
            response = requests.get(rulings_url)
            if response.status_code == 200:
                return response.json().get('data', [])
        return []

    def get_card_image(self, card_name: str) -> str:
        """Get card image URL"""
        card_info = self.get_card_info(card_name)
        if card_info:
            return card_info.get('image_uris', {}).get('normal')
        return None
    
def parse_card_references(text: str) -> Tuple[List[str], List[str]]:
    """Extract card names from [[Card Name]] and [[!Card Name]] patterns"""
    text_refs = re.findall(r'\[\[([^\]!][^\]]*)\]\]', text)
    image_refs = re.findall(r'\[\[!([^\]]*)\]\]', text)
    return text_refs, image_refs

def load_rules_context(rules_context_path: str = None) -> str:
    """Load rules from both PDF and JSON files"""
    # Debug current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Current directory: {current_dir}")

    if rules_context_path is None:
        rules_context_path = os.path.join(current_dir, "rules_context")
    
    # Debug rules context path
    print(f"Looking for rules in: {rules_context_path}")
    print(f"Directory exists: {os.path.exists(rules_context_path)}")
    
    rules_text = ""
    
    # Load PDF rules with full path logging
    pdf_path = os.path.join(rules_context_path, "mtgrules.pdf")
    print(f"Attempting to load PDF from: {pdf_path}")
    print(f"PDF file exists: {os.path.exists(pdf_path)}")
    
    try:
        with open(pdf_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                rules_text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Warning: Could not load PDF rules from {pdf_path}: {e}")

    # Load JSON rules with full path logging
    json_path = os.path.join(rules_context_path, "reddit_top_posts.json")
    print(f"Attempting to load JSON from: {json_path}")
    print(f"JSON file exists: {os.path.exists(json_path)}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as json_file:
            rules_json = json.load(json_file)
            rules_text += json.dumps(rules_json, indent=2)
    except Exception as e:
        print(f"Warning: Could not load JSON rules from {json_path}: {e}")

    return rules_text.strip()

class ContentValidator:
    def __init__(self):
        self.MIN_WORDS = 10  # Shorter minimum for concise rule answers
        self.MAX_WORDS = 500  # Shorter maximum for clear responses
        self.MTG_REQUIRED_TERMS = {
            "rules": ["rule", "section", "comprehensive rules"],
            "gameplay": ["cast", "resolve", "trigger", "ability", "stack"],
            "timing": ["phase", "step", "turn", "priority"]
        }
        self.INVALID_PATTERNS = [
            "As an AI", "I am an AI", "I apologize",
            "I cannot", "I don't have", "I'm unable",
            "real world", "other games"
        ]

    def validate_mtg_response(self, content: str) -> Tuple[bool, str]:
        # Check for minimum MTG terminology
        has_rules = any(term in content.lower() for term in self.MTG_REQUIRED_TERMS["rules"])
        has_gameplay = any(term in content.lower() for term in self.MTG_REQUIRED_TERMS["gameplay"])
        
        word_count = len(content.split())
        if word_count < self.MIN_WORDS or word_count > self.MAX_WORDS:
            return False, "Response length invalid"
            
        if any(pattern in content for pattern in self.INVALID_PATTERNS):
            return False, "Response contains invalid patterns"
            
        return True, "Content validation passed"

def generate_with_model(model: str, prompt: str, history: list = None, rules_context_path: str = "rules_context", profile_data=None, user=None, session=None) -> str:
    validator = ContentValidator()
    tracker = ChatModelTracker()
    ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    scryfall = ScryfallAPI()

    # Load rules context using new function
    rules_context = load_rules_context(rules_context_path)

    # Extract card references from the prompt
    text_refs, image_refs = parse_card_references(prompt)
    
    # Get all card references, including those not marked for images
    all_cards = set(text_refs + image_refs)
    
    # Always get images for all referenced cards
    image_urls = []
    for card_name in all_cards:
        image_url = scryfall.get_card_image(card_name)
        if image_url:
            image_urls.append(image_url)

    # Build comprehensive card context from Scryfall API
    card_context = "Using only official Scryfall API data:\n"
    
    for card_name in text_refs:
        card_info = scryfall.get_card_info(card_name)
        if card_info:
            # Extract relevant gameplay fields
            gameplay_fields = {
                "name": card_info.get("name", ""),
                "mana_cost": card_info.get("mana_cost", ""),
                "type_line": card_info.get("type_line", ""),
                "oracle_text": card_info.get("oracle_text", ""),
                "power": card_info.get("power", ""),
                "toughness": card_info.get("toughness", ""),
                "loyalty": card_info.get("loyalty", ""),
                "colors": card_info.get("colors", []),
                "keywords": card_info.get("keywords", []),
                "legalities": card_info.get("legalities", {}),
                "set_name": card_info.get("set_name", "")
            }
            
            card_context += f"\nCard Details for {card_name}:\n"
            for field, value in gameplay_fields.items():
                if value:
                    card_context += f"{field}: {value}\n"

            # Include official rulings
            rulings = scryfall.get_card_rulings(card_name)
            if rulings:
                card_context += f"\nOfficial Rulings for {card_name}:\n"
                for ruling in rulings:
                    card_context += f"- {ruling.get('comment')}\n"

    # Updated system prompt to prioritize rules
    mtg_system_prompt = """You are a Level 1 Magic: The Gathering judge.
    Follow this priority order when answering:
    1. ALWAYS check and apply the comprehensive rules provided in the rules context first
    2. Use the specific card information from Scryfall API to supplement the rules
    3. Combine both sources to provide accurate rulings
    If information is not found in either source, state that explicitly."""

    # Build knowledge base combining rules and card info
    full_context = f"""COMPREHENSIVE RULES CONTEXT:
{rules_context}

CARD SPECIFIC INFORMATION:
{card_context}"""

    # Format conversation history
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in (history or [])])
    
    # Build final prompt combining all elements
    full_prompt = f"{mtg_system_prompt}\n\n{full_context}\n\n{history_text}\nUser: {prompt}\nJudge:"

    try:
        response = requests.post(f"{ollama_host}/api/generate", 
            json={"model": model, "prompt": full_prompt, "stream": False}
        ).json()

        generated_text = response.get("response", "")

        if image_urls:
            generated_text += "\n\nRequested card images:\n" + "\n".join(image_urls)
        
        # Validate response
        is_valid, validation_message = validator.validate_mtg_response(generated_text)
        if not is_valid:
            return "I need to provide a more accurate rules-based response. Please rephrase your question."

        # Track conversation if user and session provided
        if user and session:
            tracker.track_conversation(
                user=user,
                session=session,
                prompt=prompt,
                response=generated_text,
                model=model,
                platform="mtg_judge"
            )

        return generated_text

    except Exception as e:
        return f"Error generating response: {str(e)}"


class ChatModelTracker:
    def __init__(self):
        # Historial de mensajes para mantener el contexto de la conversación
        self.message_history = ChatMessageHistory()
        # Variable para rastrear el tiempo de inicio de la generación de respuestas
        self.start_time = None
    
    def _track_metrics(self, **kwargs):
        # Calcula y retorna métricas importantes de la conversación:
        # - timestamp: momento exacto de la generación
        # - generation_time: tiempo total de generación
        # - prompt_tokens: cantidad aproximada de tokens en el prompt
        # - response_tokens: cantidad aproximada de tokens en la respuesta
        metrics = {
            'timestamp': time.time(),
            'generation_time': time.time() - self.start_time if self.start_time else 0,
            'prompt_tokens': len(kwargs.get('prompt', '').split()),
            'response_tokens': len(kwargs.get('response', '').split()),
        }
        return metrics

    def track_conversation(self, user, session, prompt, response, model, platform):
        # Inicia el cronómetro para medir el tiempo de generación
        self.start_time = time.time()
        # Obtiene las métricas de la conversación actual
        metrics = self._track_metrics(prompt=prompt, response=response)
        
        # Guarda la conversación en la base de datos incluyendo:
        # - Información del usuario y sesión
        # - Prompt y respuesta
        # - Modelo utilizado y plataforma
        # - Métricas calculadas
        ConversationTracker.objects.create(
            user=user,
            session=session,
            prompt=prompt,
            response=response,
            model_used=model,
            platform=platform,
            metrics=metrics
        )
        
        # Actualiza el historial de mensajes para mantener el contexto
        self.message_history.add_user_message(prompt)
        self.message_history.add_ai_message(response)
        
        return metrics
