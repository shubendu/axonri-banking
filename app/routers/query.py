"""
Query router — the main user-facing endpoint.

GET /api/query/stream  — SSE streaming query (primary)
POST /api/query        — non-streaming query (for testing / admin)
"""

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from axonri_core.models import QueryRequest, QueryResult

router = APIRouter()


def get_current_user(request: Request) -> dict:
    """
    Basic session check. Replace with proper JWT in production.
    For Phase 1, simple session token in cookie or header.
    """
    token = (
        request.headers.get("X-Session-Token")
        or request.cookies.get("session_token")
    )
    # Allow eval runner and testing
    if token in ("test", "eval-runner", "axonri-eval"):
        return {"user_id": "eval", "username": "eval.runner"}
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": "staff_user", "username": "branch.staff"}


@router.get("/api/query/stream")
async def query_stream(
    q: str,
    request: Request,
    input_method: str = "text",
    # user: dict = Depends(get_current_user),
):
    """
    SSE streaming query endpoint.

    Query params:
        q: the question text (URL-encoded)
        input_method: 'text' or 'voice'

    Returns:
        Server-Sent Events stream with events: token, sources, done, error

    Example:
        curl -N 'http://localhost:8000/api/query/stream?q=NPA+kab+banta+hai'
    """
    user = {"user_id": "staff_user", "username": "staff"}  # hardcode for testing
    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=422, detail="Query too short (min 3 chars)")
    if len(q) > 2000:
        raise HTTPException(status_code=422, detail="Query too long (max 2000 chars)")

    engine = request.app.state.engine

    async def event_generator():
        try:
            async for sse_event in engine.query_stream(
                query=q.strip(),
                user_id=user["user_id"],
                input_method=input_method,
            ):
                yield sse_event
        except Exception as e:
            import json
            yield f'event: error\ndata: {json.dumps({"message": "Unexpected error. Please try again."})}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.post("/api/query", response_model=dict)
async def query_sync(
    body: QueryRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Non-streaming query for testing. Collects full SSE stream and returns JSON.
    Not recommended for production UI — use /api/query/stream instead.
    """
    engine = request.app.state.engine
    tokens = []
    sources = []
    query_id = None

    import json
    async for sse in engine.query_stream(
        query=body.query,
        user_id=user["user_id"],
        input_method=body.input_method,
    ):
        lines = sse.strip().split("\n")
        if len(lines) < 2:
            continue
        event_type = lines[0].replace("event: ", "")
        try:
            data = json.loads(lines[1].replace("data: ", ""))
        except json.JSONDecodeError:
            continue

        if event_type == "token":
            tokens.append(data.get("text", ""))
        elif event_type == "sources":
            sources = data.get("sources", [])
        elif event_type == "done":
            query_id = data.get("query_id")
            response_timings = data.get("timings", {})
        elif event_type == "error":
            raise HTTPException(status_code=503, detail=data.get("message"))

    return {
    "query_id": query_id,
    "answer":   "".join(tokens),
    "sources":  sources,
    "timings":  response_timings,
    }
