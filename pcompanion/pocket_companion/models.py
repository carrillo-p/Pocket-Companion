from django.db import models
import json
from django.contrib.auth.models import User
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage

class ChatSession(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)  # Fecha y hora de creación automática
    model_choice = models.CharField(max_length=50)  # Modelo de lenguaje seleccionado
    conversation_history = models.TextField(default='[]')  # Almacena el historial como cadena JSON

    def add_message(self, role: str, content: str):
        """
        Agrega un nuevo mensaje al historial de conversación
        Args:
            role (str): Rol del mensaje (usuario o asistente)
            content (str): Contenido del mensaje
        """
        history = json.loads(self.conversation_history)
        history.append({"role": role, "content": content})
        self.conversation_history = json.dumps(history)
        self.save()

    def get_history(self):
        """
        Recupera el historial de conversación completo
        Returns:
            list: Lista de mensajes en formato JSON
        """
        return json.loads(self.conversation_history)
    
class ConversationTracker(models.Model):
    """
    Modelo para rastrear y almacenar las conversaciones individuales entre usuarios y el chatbot.
    Registra detalles específicos de cada interacción para análisis y seguimiento.
    """
    # Relación con el usuario que inició la conversación
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # Vinculación con la sesión de chat correspondiente
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE)
    # Marca temporal de cuando se registró la conversación
    timestamp = models.DateTimeField(auto_now_add=True)
    # Texto de entrada proporcionado por el usuario
    prompt = models.TextField()
    # Respuesta generada por el modelo
    response = models.TextField()
    # Identificador del modelo de IA utilizado
    model_used = models.CharField(max_length=50)
    # Plataforma desde donde se realizó la interacción
    platform = models.CharField(max_length=20)
    # Métricas adicionales de la conversación en formato JSON
    metrics = models.JSONField(default=dict)

    class Meta:
        # Ordenar las conversaciones por timestamp en orden descendente
        ordering = ['-timestamp']
