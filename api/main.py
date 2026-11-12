"""Local source search and an explicit, experimental evidence-review endpoint."""

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
from retrieval.assessor import OpenRouterClient, assess_evidence
from retrieval.evidence import decide_evidence


INPUT_MESSAGE = 'Provide question (1-8000 non-whitespace characters) and limit (integer 1-20).'
SERVICE_MESSAGE = 'Retrieval is unavailable. Check the local model cache and Qdrant service.'
ASSESSMENT_MESSAGE = 'Evidence review is unavailable. The retrieved passages are still available to read.'


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


class RelatedSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    point_id: int | str
    url: str
    title: str
    relevance: Literal['direct', 'related']
    applicability: Literal['matching', 'mismatch', 'unknown']
    support: Literal['explanation', 'documented_guidance', 'documented_release', 'reported_success',
                     'suggestion_without_outcome', 'symptoms_only', 'none']
    reason: str
    limitations: list[str]


class PermittedClaim(RelatedSource):
    claim: str
    evidence_quote: str
    qualification: str


class EvidenceDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['supported_answer', 'related_reports_insufficient_support',
                    'no_relevant_evidence_retrieved', 'review_required', 'service_error']
    message: str
    notice: str
    permitted_claims: list[PermittedClaim]
    related_sources: list[RelatedSource]
    basis: str | None = None
    conflicting_evidence: bool = False


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['assessed', 'no_relevant_evidence_retrieved', 'review_required', 'service_error']
    retrieval: SearchResponse
    decision: EvidenceDecision
    model_called: bool


def configured_assessor():
    import config
    return OpenRouterClient(config.OPENROUTER_API_KEY, config.LLM_MODEL)


def create_app(*, retriever_factory=Retriever, assessor_factory=configured_assessor):
    @asynccontextmanager
    async def lifespan(application):
        application.state.retriever = retriever_factory()
        application.state.search_lock = Lock()
        application.state.assessment_lock = Lock()
        try:
            yield
        finally:
            application.state.retriever.close()

    application = FastAPI(
        title='Vita Vault API', version='0.2.0', lifespan=lifespan,
        description='Local source search plus optional model-assisted evidence review. No verified repairs or hardware diagnoses.',
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

    @application.post('/assess', response_model=AssessmentResponse,
                      summary='Retrieve and review source evidence with the configured free model',
                      responses={400: {'model': ErrorResponse}, 422: {'model': ErrorResponse},
                                 503: {'description': 'Retrieval, review service, or review capacity unavailable'}})
    def assess(body: SearchRequest, request: Request):
        # Do not queue unlimited model requests. Source-only searches stay usable.
        lock = request.app.state.assessment_lock
        if not lock.acquire(blocking=False):
            return JSONResponse(status_code=503, content={'status': 'service_error',
                'message': 'Another evidence review is running. Try again shortly, or search sources.'})
        try:
            retrieved = search(body, request)
            if isinstance(retrieved, JSONResponse):
                return retrieved
            retrieval = retrieved.model_dump()
            called = False
            try:
                if retrieval['status'] == 'no_candidates':
                    decision = decide_evidence(retrieval, None)
                    state = decision['status']
                else:
                    client = assessor_factory()
                    called = True
                    result = assess_evidence(retrieval, client)
                    called = result['model_called']
                    state = result['status']
                    # Rebind accepted reviews to the server's own retrieval.
                    if state == 'assessed':
                        decision = decide_evidence(retrieval, result['review'])
                        if decision['status'] == 'review_required':
                            state = 'review_required'
                    else:
                        decision = None
                if state in ('review_required', 'service_error'):
                    decision = {'status': state, 'message': ASSESSMENT_MESSAGE if state == 'service_error' else
                        'The evidence review could not be validated. Read the original passages or try again.',
                        'notice': 'No supported answer was established.', 'permitted_claims': [], 'related_sources': []}
                response = AssessmentResponse(status=state, retrieval=retrieved,
                    decision=decision, model_called=called)
            except Exception:
                # Never expose provider bodies, credentials, raw reviews or configuration errors.
                response = AssessmentResponse(status='service_error', retrieval=retrieved,
                    decision={'status': 'service_error', 'message': ASSESSMENT_MESSAGE,
                              'notice': 'No supported answer was established.',
                              'permitted_claims': [], 'related_sources': []}, model_called=called)
            if response.status == 'service_error':
                return JSONResponse(status_code=503, content=response.model_dump())
            return response
        finally:
            lock.release()

    # Register last so API routes retain their existing behavior. Serve only
    # the dedicated public directory, never repository files or credentials.
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    if (frontend / 'index.html').is_file():
        application.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')

    return application


app = create_app()
