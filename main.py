"""FastAPI application for receiving and processing task requests."""
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn

from config import get_settings
from models import (
    TaskRequest,
    TaskResponse,
    EvaluationNotification,
    HealthResponse
)
from services.llm_generator import LLMGenerator
from services.github_service import GitHubService
from services.notifier import NotificationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app."""
    logger.info("Starting up application...")
    logger.info(f"Student email: {settings.student_email}")
    logger.info(f"GitHub username: {settings.github_username}")
    yield
    logger.info("Shutting down application...")


# Create FastAPI app
app = FastAPI(
    title="LLM Code Deployment - Student API",
    description="Receives task briefs, generates apps, and deploys to GitHub Pages",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests for debugging."""
    # Log request details
    logger.info(f"Request: {request.method} {request.url.path} from {request.client.host}")
    
    # Log headers
    content_type = request.headers.get("content-type", "")
    logger.info(f"Content-Type: {content_type}")
    
    response = await call_next(request)
    return response


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint."""
    return HealthResponse(status="healthy")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@app.post("/api/build", response_model=TaskResponse)
async def build_and_deploy(
    request: TaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Receive task request and trigger build/deploy process.
    
    This endpoint:
    1. Validates the secret
    2. Returns immediate 200 response
    3. Processes task in background
    """
    logger.info(f"Received task request: {request.task} (round {request.round})")
    logger.debug(f"Request details: {request.model_dump()}")
    
    # Validate email
    if request.email != settings.student_email:
        logger.warning(f"Email mismatch: {request.email} != {settings.student_email}")
        raise HTTPException(
            status_code=403,
            detail="Email does not match configured student email"
        )
    
    # Validate secret
    if request.secret != settings.student_secret:
        logger.warning("Invalid secret provided")
        raise HTTPException(
            status_code=403,
            detail="Invalid secret"
        )
    
    # Add background task
    background_tasks.add_task(
        process_task,
        request
    )
    
    # Return immediate response
    return TaskResponse(
        status="accepted",
        message=f"Task {request.task} received and processing started"
    )


async def process_task(request: TaskRequest):
    try:
        logger.info(f"Processing task: {request.task}")
        
        # Initialize services
        generator = LLMGenerator(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url
        )
        
        github_service = GitHubService(
            token=settings.github_token,
            username=settings.github_username,
            pages_timeout=settings.pages_timeout
        )
        
        notifier = NotificationService(
            max_retries=settings.max_retries,
            retry_delays=settings.retry_delays
        )
        
        # Determine repository name
        repo_name = request.task.replace(".", "-").replace("_", "-")
        
        # For Round 2+, fetch existing code first
        existing_files = None
        if request.round > 1:
            logger.info(f"Round {request.round}: Fetching existing code from {repo_name}...")
            existing_files = github_service.get_repository_files(repo_name)
            
            if not existing_files:
                logger.warning(f"No existing repo found for {repo_name}, treating as Round 1")
                request.round = 1  # Fallback to creating new repo
        
        # Step 1: Generate or update application
        logger.info(f"Step 1: {'Updating' if request.round > 1 else 'Generating'} application with LLM...")
        files = generator.generate_app(
            brief=request.brief,
            checks=request.checks,
            attachments=request.attachments or [],
            task_id=request.task,
            round_num=request.round,
            existing_files=existing_files
        )
        
        # Step 2: Create/update repository
        if request.round == 1:
            logger.info("Step 2: Creating new GitHub repository...")
            deployment = github_service.create_and_deploy(
                repo_name=repo_name,
                files=files,
                task_id=request.task
            )
        else:
            logger.info("Step 2: Updating existing repository...")
            deployment = github_service.update_repository(
                repo_name=repo_name,
                files=files
            )
        
        # Step 3: Notify evaluation server
        logger.info("Step 3: Notifying evaluation server...")
        notification = EvaluationNotification(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=deployment["repo_url"],
            commit_sha=deployment["commit_sha"],
            pages_url=deployment["pages_url"]
        )
        
        success = await notifier.notify_evaluation_server(
            evaluation_url=request.evaluation_url,
            notification=notification
        )
        
        if success:
            logger.info(f"✓ Task {request.task} completed successfully!")
        else:
            logger.error(f"✗ Task {request.task} completed but notification failed")
        
    except Exception as e:
        logger.error(f"Error processing task {request.task}: {e}", exc_info=True)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with request body."""
    try:
        body = await request.body()
        body_str = body.decode()
        logger.error(f"Validation error - Content-Type: {request.headers.get('content-type')}")
        logger.error(f"Raw body (first 500 chars): {body_str[:500]}")
        logger.error(f"Validation errors: {exc.errors()}")
        
        # Try to help diagnose the issue
        if body_str.startswith('"') or body_str.startswith("'"):
            logger.error("⚠️  Body appears to be a JSON STRING instead of JSON object!")
            logger.error("Make sure Content-Type is 'application/json' and body is raw JSON, not a string")
    except Exception as e:
        logger.error(f"Could not read request body: {e}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "hint": "Ensure Content-Type is 'application/json' and body is valid JSON (not a string)"
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


def main():
    """Run the application."""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
