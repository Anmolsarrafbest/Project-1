"""FastAPI application for receiving and processing task requests."""
import logging
import json
import time
from contextlib import asynccontextmanager
from typing import Dict, Set
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
from services.validator import ValidationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Request tracking for duplicate detection
# Track: {(task, round, nonce): {"status": "processing"|"completed", "timestamp": float, "result": dict}}
request_tracker: Dict[tuple, dict] = {}
TRACKER_CLEANUP_INTERVAL = 900  # 15 minutes in seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app."""
    logger.info("Starting up application...")
    logger.info(f"Student email: {settings.student_email}")
    logger.info(f"GitHub username: {settings.github_username}")
    yield
    logger.info("Shutting down application...")


def cleanup_old_requests():
    """Remove old entries from request tracker to prevent memory bloat."""
    current_time = time.time()
    keys_to_remove = [
        key for key, data in request_tracker.items()
        if current_time - data["timestamp"] > TRACKER_CLEANUP_INTERVAL
    ]
    for key in keys_to_remove:
        del request_tracker[key]
        logger.debug(f"Cleaned up old request: {key}")
    
    if keys_to_remove:
        logger.info(f"Cleaned up {len(keys_to_remove)} old request(s) from tracker")


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


@app.get("/api/build")
async def build_get_handler():
    """Handle GET requests to /api/build - inform users to use POST."""
    return {
        "error": "Method Not Allowed",
        "message": "Please send a POST request to this endpoint, not GET",
        "endpoint": "/api/build",
        "method": "POST",
        "content_type": "application/json",
        "example": {
            "email": "your-email@example.com",
            "task": "your-task-id",
            "round": 1,
            "nonce": "unique-nonce",
            "secret": "your-secret",
            "evaluation_url": "https://evaluation-server.com/callback",
            "brief": "Create a calculator app",
            "checks": ["Repo has MIT license", "README.md is professional"],
            "attachments": []
        }
    }


@app.post("/api/build", response_model=TaskResponse)
async def build_and_deploy(
    request: TaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Receive task request and trigger build/deploy process.
    
    This endpoint:
    1. Validates the secret
    2. Checks for duplicate requests (same task/round/nonce)
    3. Returns immediate 200 response
    4. Processes task in background
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
    
    # Check for duplicate request
    request_key = (request.task, request.round, request.nonce)
    
    if request_key in request_tracker:
        existing = request_tracker[request_key]
        status = existing["status"]
        
        if status == "processing":
            logger.warning(f"Duplicate request detected - already processing: {request_key}")
            return TaskResponse(
                status="processing",
                message=f"Task {request.task} (round {request.round}) is already being processed"
            )
        elif status == "completed":
            logger.warning(f"Duplicate request detected - already completed: {request_key}")
            return TaskResponse(
                status="already_completed",
                message=f"Task {request.task} (round {request.round}) was already completed"
            )
    
    # Mark request as processing
    request_tracker[request_key] = {
        "status": "processing",
        "timestamp": time.time(),
        "result": None
    }
    
    logger.info(f"Request accepted and marked as processing: {request_key}")
    
    # Clean up old requests periodically
    if len(request_tracker) % 10 == 0:  # Every 10th request
        cleanup_old_requests()
    
    # Add background task
    background_tasks.add_task(
        process_task,
        request,
        request_key
    )
    
    # Return immediate response
    return TaskResponse(
        status="accepted",
        message=f"Task {request.task} received and processing started"
    )


async def process_task(request: TaskRequest, request_key: tuple):
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
        
        validator = ValidationService()
        
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
        
        # Step 1.5: VALIDATE generated files
        logger.info("=" * 60)
        logger.info("VALIDATION: Static file validation")
        logger.info("=" * 60)
        
        static_validation = validator.validate_static_files(files, request.checks)
        
        if static_validation["errors"]:
            logger.error("❌ Static validation ERRORS:")
            for error in static_validation["errors"]:
                logger.error(f"  • {error}")
        
        if static_validation["warnings"]:
            logger.warning("⚠️  Static validation WARNINGS:")
            for warning in static_validation["warnings"]:
                logger.warning(f"  • {warning}")
        
        if static_validation["passed"]:
            logger.info("✓ Static validation PASSED")
        else:
            logger.error("✗ Static validation FAILED")
        
        logger.info("=" * 60)
        logger.info("VALIDATION: Checking against requirements")
        logger.info("=" * 60)
        
        checks_validation = validator.validate_against_checks(files, request.checks)
        
        logger.info(f"Checks validation summary: {checks_validation['passed_count']}/{checks_validation['total_checks']} passed")
        
        if checks_validation["failed_count"] > 0:
            logger.error(f"❌ {checks_validation['failed_count']} checks FAILED")
        
        if checks_validation["unknown_count"] > 0:
            logger.warning(f"⚠️  {checks_validation['unknown_count']} checks could not be validated")
        
        # Log detailed results
        for result in checks_validation["results"]:
            if result["passed"] == True:
                logger.info(f"  ✓ {result['check']}")
            elif result["passed"] == False:
                logger.error(f"  ✗ {result['check']}: {result['message']}")
            else:
                logger.warning(f"  ⚠ {result['check']}: {result['message']}")
        
        logger.info("=" * 60)
        
        # Step 1.6: TARGETED FIXES for failed checks (if any)
        if checks_validation["failed_count"] > 0:
            logger.info("=" * 60)
            logger.info("ATTEMPTING TARGETED FIXES")
            logger.info("=" * 60)
            
            failed_checks = [r for r in checks_validation["results"] if r["passed"] == False]
            
            try:
                # Only fix specific failed checks (fast!)
                fixed_files = generator.fix_validation_failures(
                    files,
                    failed_checks,
                    request.task
                )
                
                # Re-validate ONLY if files were actually changed
                if fixed_files != files:
                    logger.info("Re-validating after fixes...")
                    files = fixed_files
                    
                    # Quick re-validation
                    recheck_validation = validator.validate_against_checks(files, request.checks)
                    
                    improvement = recheck_validation["passed_count"] - checks_validation["passed_count"]
                    
                    if improvement > 0:
                        logger.info(f"✓ Fixes successful: {improvement} more checks passed!")
                        logger.info(f"New score: {recheck_validation['passed_count']}/{recheck_validation['total_checks']}")
                    else:
                        logger.warning("Fixes did not improve validation results")
                    
                    # Log what changed
                    for result in recheck_validation["results"]:
                        old_result = next((r for r in checks_validation["results"] if r["check"] == result["check"]), None)
                        if old_result and old_result["passed"] == False and result["passed"] == True:
                            logger.info(f"  ✓ FIXED: {result['check']}")
                else:
                    logger.info("No files were changed during fix attempt")
                    
            except Exception as e:
                logger.error(f"Fix attempt failed (non-fatal): {e}")
                logger.info("Continuing with original files...")
            
            logger.info("=" * 60)
        
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
        
        # Step 2.5: VALIDATE deployed page
        logger.info("=" * 60)
        logger.info("VALIDATION: Live deployed page")
        logger.info("=" * 60)
        
        try:
            live_validation = validator.validate_deployed_page(
                deployment["pages_url"],
                request.checks,
                timeout=20
            )
            
            if live_validation["info"]:
                logger.info(f"Page info: {live_validation['info']}")
            
            if live_validation["errors"]:
                logger.error("❌ Live page validation ERRORS:")
                for error in live_validation["errors"]:
                    logger.error(f"  • {error}")
            
            if live_validation["warnings"]:
                logger.warning("⚠️  Live page validation WARNINGS:")
                for warning in live_validation["warnings"]:
                    logger.warning(f"  • {warning}")
            
            if live_validation["passed"]:
                logger.info("✓ Live page validation PASSED")
            else:
                logger.error("✗ Live page validation FAILED")
        
        except Exception as e:
            logger.error(f"Live validation error (non-fatal): {e}")
        
        logger.info("=" * 60)
        logger.info("VALIDATION COMPLETE")
        logger.info("=" * 60)
        
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
            # Mark as completed in tracker
            request_tracker[request_key] = {
                "status": "completed",
                "timestamp": time.time(),
                "result": deployment
            }
        else:
            logger.error(f"✗ Task {request.task} completed but notification failed")
            # Still mark as completed (work is done, just notification failed)
            request_tracker[request_key] = {
                "status": "completed",
                "timestamp": time.time(),
                "result": deployment
            }
        
    except Exception as e:
        logger.error(f"Error processing task {request.task}: {e}", exc_info=True)
        # Mark as failed but keep in tracker to prevent retries of failed tasks
        request_tracker[request_key] = {
            "status": "failed",
            "timestamp": time.time(),
            "result": None,
            "error": str(e)
        }


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
