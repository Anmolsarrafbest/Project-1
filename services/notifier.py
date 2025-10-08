"""Notification service to send results to evaluation server."""
import logging
import time
from typing import List
import httpx
from models import EvaluationNotification

logger = logging.getLogger(__name__)


class NotificationService:
    """Handle notifications to evaluation server with retry logic."""
    
    def __init__(self, max_retries: int = 5, retry_delays: List[int] = None):
        """Initialize with retry configuration."""
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [1, 2, 4, 8, 16]
    
    async def notify_evaluation_server(
        self,
        evaluation_url: str,
        notification: EvaluationNotification
    ) -> bool:
        """
        Send notification to evaluation server with exponential backoff.
        
        Args:
            evaluation_url: URL to POST notification to
            notification: Evaluation notification data
        
        Returns:
            True if successful, False otherwise
        """
        payload = notification.model_dump()
        
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Notifying evaluation server (attempt {attempt + 1}/{self.max_retries})..."
                )
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        evaluation_url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        logger.info("✓ Evaluation server notified successfully")
                        return True
                    else:
                        logger.warning(
                            f"Evaluation server returned {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        
            except Exception as e:
                logger.error(f"Error notifying evaluation server: {e}")
            
            # Retry with exponential backoff
            if attempt < self.max_retries - 1:
                delay = self.retry_delays[attempt]
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
        
        logger.error(
            f"Failed to notify evaluation server after {self.max_retries} attempts"
        )
        return False
