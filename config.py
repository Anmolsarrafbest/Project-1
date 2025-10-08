"""Configuration management using Pydantic settings."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Student credentials
    student_email: str
    student_secret: str
    
    # GitHub configuration
    github_token: str
    github_username: str
    
    # AI Pipe configuration (IITM's AI service)
    openai_api_key: str  # Your AI Pipe token
    openai_base_url: str = "https://aipipe.org/openai/v1/chat/completions"  # AI Pipe endpoint
    openai_model: str = "gpt-4o-mini"  # Model available on AI Pipe
    
    # Server configuration
    port: int = 8000
    
    # Retry configuration
    max_retries: int = 5
    retry_delays: list[int] = [1, 2, 4, 8, 16]
    
    # GitHub Pages wait timeout (seconds)
    pages_timeout: int = 300
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
