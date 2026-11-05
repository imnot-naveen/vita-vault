"""Local source-returning API; retrieval candidates remain unassessed."""

from contextlib import asynccontextmanager
from threading import Lock
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from retrieval.search import InvalidInput, Retriever


INPUT_MESSAGE = 'Provide question (1-8000 non-whitespace characters) and limit (integer 1-20).'
SERVICE_MESSAGE = 'Retrieval is unavailable. Check the local model cache and Qdrant service.'


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator('question', mode='before')
    @classmethod
    def trim_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class SourceCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    point_id: int | str
    score: float
    matching_query_identifiers: list[str]
    payload: dict[str, Any]


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    status: Literal['candidates_require_review', 'no_candidates']
    question: str
    collection: str
    embedding_model: str
    query_prefix: str
    ranking: str
    query_identifiers: list[str]
    min_score: float | None
    evidence_assessment: Literal['not_assessed']
    notice: str
    sources: list[SourceCandidate]
    fetched_points: int
    skipped: dict[str, int]


class ErrorResponse(BaseModel):
    status: Literal['invalid_input', 'service_error']
    message: str


def create_app(*, retriever_factory=Retriever):
    @asynccontextmanager
    async def lifespan(application):
        application.state.retriever = retriever_factory()
        application.state.search_lock = Lock()
        try:
            yield
        finally:
            application.state.retriever.close()

    application = FastAPI(
        title='Vita Vault Source API', version='0.1.0', lifespan=lifespan,
        description='Read-only retrieval of source passages. Candidates are not assessed answers or confirmed fixes.',
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exception):
        return JSONResponse(status_code=422, content={'status': 'invalid_input', 'message': INPUT_MESSAGE})

    @application.get('/health', summary='Check process liveness')
    def health():
        return {'status': 'ok', 'service': 'vita-vault', 'check': 'process_liveness'}

    @application.post('/search', response_model=SearchResponse,
                      summary='Retrieve source-bearing candidates',
                      responses={400: {'model': ErrorResponse, 'description': 'Search options rejected'},
                                 422: {'model': ErrorResponse, 'description': 'Invalid request body'},
                                 503: {'model': ErrorResponse, 'description': 'Retrieval unavailable'}})
    def search(body: SearchRequest, request: Request):
        try:
            # One shared, lazily loaded encoder/client. Serialize access so the
            # first model load and in-memory client operations cannot overlap.
            with request.app.state.search_lock:
                result = request.app.state.retriever.search(body.question, limit=body.limit)
                return SearchResponse.model_validate(result)
        except InvalidInput:
            return JSONResponse(status_code=400, content={'status': 'invalid_input', 'message': INPUT_MESSAGE})
        except Exception:
            # Backend exception strings may contain credentials or local paths.
            return JSONResponse(status_code=503, content={'status': 'service_error', 'message': SERVICE_MESSAGE})

    # Register last so API routes retain their existing behavior. Serve only
    # the dedicated public directory, never repository files or credentials.
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    if (frontend / 'index.html').is_file():
        application.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')

    return application


app = create_app()
