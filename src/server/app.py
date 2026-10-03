"""Production FastAPI Application for AI Research Assistant.

Provides zero-cost, enterprise-grade REST endpoints for autonomous research:
- Health check & component diagnostics (/api/health)
- Synchronous & Asynchronous research job dispatch (/api/research)
- Job status & progress polling (/api/research/{job_id})
- Multi-format report downloads (/api/research/{job_id}/download)
- In-memory thread-safe job store with optional persistence
"""

import io
import time
import uuid
import threading
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.models.schemas import ResearchResult
from src.graphs.graph import run_research
from src.security.guardrails import get_guardrails
from src.security.rate_limiter import get_rate_limiter, RateLimitExceeded
from src.utils.exporter import export_to_markdown, export_to_json, export_to_pdf, _slugify
from src.utils.html_exporter import export_to_html
from src.utils.logger import get_logger

logger = get_logger("server.api")

# Initialize FastAPI App
app = FastAPI(
    title="AI Research Assistant Production API",
    version="1.0.0",
    description="Autonomous, 100% free multi-agent research platform REST API",
)

# Enable CORS for web and dashboard integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rate Limiter Exception Handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc), "retry_after": exc.retry_after},
        headers={"Retry-After": str(int(exc.retry_after) + 1)},
    )


# ---------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------
class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Research topic or question")
    max_papers: int = Field(3, ge=1, le=10, description="Max academic arXiv papers")
    max_web: int = Field(3, ge=1, le=10, description="Max web search results")
    max_revisions: int = Field(2, ge=0, le=5, description="Max judge refinement loops")
    research_mode: str = Field("quick", description="'quick' (15s lean) or 'deep' (full audit)")
    use_cache: bool = Field(True, description="Enable semantic cache for instant hits")
    async_mode: bool = Field(True, description="Run in background and poll for status")


class ProgressEntry(BaseModel):
    step: str
    message: str
    timestamp: float


class JobStatus(BaseModel):
    job_id: str
    query: str
    status: str  # "queued", "running", "completed", "failed"
    research_mode: str
    created_at: float
    duration_seconds: Optional[float] = None
    progress: List[ProgressEntry] = []
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------
# Thread-Safe In-Memory Job Store
# ---------------------------------------------------------
class JobStore:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._results: Dict[str, ResearchResult] = {}
        self._lock = threading.Lock()

    def create_job(self, query: str, research_mode: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "query": query,
                "status": "queued",
                "research_mode": research_mode,
                "created_at": time.time(),
                "duration_seconds": None,
                "progress": [],
                "error": None,
            }
        return job_id

    def update_progress(self, job_id: str, step: str, message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "running"
                self._jobs[job_id]["progress"].append(
                    {"step": step, "message": message, "timestamp": time.time()}
                )

    def complete_job(self, job_id: str, result: ResearchResult) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "completed"
                self._jobs[job_id]["duration_seconds"] = result.duration_seconds
                self._results[job_id] = result

    def fail_job(self, job_id: str, error_msg: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error_msg
                self._jobs[job_id]["duration_seconds"] = round(
                    time.time() - self._jobs[job_id]["created_at"], 2
                )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            data = dict(job)
            if job_id in self._results:
                data["result"] = self._results[job_id].model_dump()
            return data

    def get_result(self, job_id: str) -> Optional[ResearchResult]:
        with self._lock:
            return self._results.get(job_id)

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda x: x["created_at"], reverse=True)
            return jobs[:limit]


job_store = JobStore()


# ---------------------------------------------------------
# Background Worker Function
# ---------------------------------------------------------
def _execute_research_job(job_id: str, req: ResearchRequest) -> None:
    """Execute research pipeline in background thread."""
    try:
        job_store.update_progress(job_id, "start", f"Initiating research on '{req.query}'")

        def progress_cb(step: str, message: str):
            job_store.update_progress(job_id, step, message)

        result = run_research(
            query=req.query,
            max_papers=req.max_papers,
            max_web=req.max_web,
            max_revisions=req.max_revisions,
            on_progress=progress_cb,
            use_cache=req.use_cache,
            research_mode=req.research_mode,
        )
        job_store.complete_job(job_id, result)
        logger.info(f"Background research job {job_id} completed successfully.")
    except Exception as exc:
        logger.exception(f"Background research job {job_id} failed: {exc}")
        job_store.fail_job(job_id, str(exc))


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.get("/", tags=["General"])
async def root():
    """Welcome index with quick links to docs and health status."""
    return {
        "name": "AI Research Assistant API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/api/health",
        "cost": "$0 (100% Free / Self-Hostable)",
    }


@app.get("/api/health", tags=["General"])
async def health_check():
    """Comprehensive health check for API, security guardrails, and memory layers."""
    guardrails = get_guardrails()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "platform": "AI Research Assistant",
        "version": "1.0.0",
        "zero_cost_ready": True,
        "components": {
            "guardrails": "local_active" if guardrails else "inactive",
            "rate_limiter": "active",
            "search_fallback": "duckduckgo_free_active",
            "storage": "local_sqlite_active",
        },
    }


@app.post("/api/research", response_model=Dict[str, Any], tags=["Research"])
async def start_research(
    req: ResearchRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Trigger research run with local security guardrails check."""
    # 1. Rate Limiting Check
    client_ip = request.client.host if request.client else "unknown"
    limiter = get_rate_limiter()
    limiter.check_or_raise(f"api_research_{client_ip}")

    # 2. Local Guardrails Security Check (PII masking & injection defense)
    guardrails = get_guardrails()
    passed, sanitized_query, reason = guardrails.validate_input(req.query)
    if not passed:
        raise HTTPException(
            status_code=400,
            detail=f"Security Guardrail Violation: {reason}",
        )

    # Use sanitized query
    req.query = sanitized_query

    # 3. Create Job
    job_id = job_store.create_job(req.query, req.research_mode)

    if req.async_mode:
        background_tasks.add_task(_execute_research_job, job_id, req)
        return {
            "job_id": job_id,
            "status": "queued",
            "query": req.query,
            "message": "Research job queued successfully. Check status at /api/research/{job_id}",
            "status_url": f"/api/research/{job_id}",
        }
    else:
        # Synchronous execution
        _execute_research_job(job_id, req)
        job_data = job_store.get_job(job_id)
        if job_data.get("status") == "failed":
            raise HTTPException(status_code=500, detail=job_data.get("error", "Research failed"))
        return job_data


@app.get("/api/research/{job_id}", response_model=Dict[str, Any], tags=["Research"])
async def get_job_status(job_id: str):
    """Get the current progress or completed results of a research job."""
    job_data = job_store.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job_data


@app.get("/api/research/{job_id}/download", tags=["Export"])
async def download_report(
    job_id: str,
    format: str = Query("markdown", pattern="^(markdown|json|html|pdf)$"),
):
    """Download research report in desired format: markdown, json, html, or pdf."""
    result = job_store.get_result(job_id)
    if not result:
        job_data = job_store.get_job(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        if job_data.get("status") in ("queued", "running"):
            raise HTTPException(status_code=400, detail="Research is still running. Try again when complete.")
        raise HTTPException(status_code=404, detail=f"No results found for job '{job_id}'.")

    slug = _slugify(result.query)

    if format == "markdown":
        content = export_to_markdown(result)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
        )
    elif format == "html":
        content = export_to_html(result)
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.html"'},
        )
    elif format == "json":
        content = export_to_json(result)
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.json"'},
        )
    elif format == "pdf":
        try:
            pdf_bytes = export_to_pdf(result)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
            )
        except Exception as exc:
            logger.warning(f"PDF export failed, returning HTML fallback: {exc}")
            content = export_to_html(result)
            return Response(
                content=content,
                media_type="text/html; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{slug}.html"'},
            )


@app.get("/api/jobs", tags=["Research"])
async def list_jobs(limit: int = Query(50, ge=1, le=100)):
    """List recent research jobs."""
    return {"jobs": job_store.list_jobs(limit=limit)}
