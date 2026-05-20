from django.db import models
import os

class Configuration(models.Model):
    nvidia_api_key = models.CharField(max_length=255, blank=True, help_text="Your Nvidia API Key from build.nvidia.com")
    model_name = models.CharField(max_length=100, default='meta/llama-3.3-70b-instruct', help_text="The Nvidia NIM model to use")
    workspace_path = models.CharField(max_length=500, blank=True, help_text="Path to the workspace where agent edits files")

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"

    def __str__(self):
        return f"Config (Model: {self.model_name})"

    @classmethod
    def get_sole_config(cls):
        config, created = cls.objects.get_or_create(id=1)
        if not config.workspace_path:
            # Set default workspace path to env-defined path or sibling directory named 'workspace'
            default_ws = os.environ.get('DEFAULT_WORKSPACE_PATH')
            if not default_ws:
                default_ws = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace'))
            config.workspace_path = default_ws
            config.save()
        return config


class Session(models.Model):
    STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    title = models.CharField(max_length=200)
    skill_name = models.CharField(max_length=100, help_text="The name of the skill applied to this session")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idle')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    system_prompt = models.TextField(blank=True, help_text="System prompt sent to the LLM")
    workspace_dir = models.CharField(max_length=500, blank=True, help_text="Session-specific workspace subfolder")

    def __str__(self):
        return f"{self.title} ({self.skill_name})"

    def get_actual_workspace(self):
        config = Configuration.get_sole_config()
        base_workspace = config.workspace_path or os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace'))
        if self.workspace_dir:
            return os.path.join(base_workspace, self.workspace_dir)
        # Create session-specific folder inside base workspace to keep runs isolated
        session_folder = f"session_{self.id}"
        return os.path.join(base_workspace, session_folder)


class Message(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20)  # system, user, assistant, tool
    content = models.TextField(blank=True, default='')
    tool_calls = models.JSONField(blank=True, null=True, help_text="List of tool calls made by the assistant")
    tool_call_id = models.CharField(max_length=100, blank=True, null=True, help_text="ID of the tool call this message answers")
    name = models.CharField(max_length=100, blank=True, null=True, help_text="The name of the tool called")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.role.capitalize()}: {self.content[:50]}..."
