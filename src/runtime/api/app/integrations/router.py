"""Admin-only configuration status and synthetic delivery endpoints."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEvent, User
from ..security import require_role
from .contracts import (
    DeliveryState,
    IntegrationStatusResponse,
    SyntheticSendRequest,
    SyntheticSendResponse,
    normalise_idempotency_key,
)
from .service import (
    IdempotencyCapacityError,
    IdempotencyConflict,
    IntegrationService,
)


router = APIRouter()
_integration_service = IntegrationService.from_environment()


def get_integration_service() -> IntegrationService:
    return _integration_service


def _record_admin_audit(
    db: Session,
    *,
    user: User,
    event_type: str,
    target_ref: str,
    action: str,
    result: str,
    detail: dict[str, object],
) -> bool:
    try:
        db.add(
            AuditEvent(
                event_type=event_type,
                actor_user_id=user.id,
                actor_role=user.role,
                company_id=user.company_id,
                target_type="outbound_integrations",
                target_ref=target_ref,
                purpose="synthetic_integration_administration",
                action=action,
                result=result,
                detail=detail,
            )
        )
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        return False
    return True


@router.get(
    "/api/v1/admin/integrations/status",
    response_model=IntegrationStatusResponse,
)
def admin_integration_status(
    http_response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
    service: IntegrationService = Depends(get_integration_service),
) -> IntegrationStatusResponse:
    snapshot = service.status()
    http_response.headers["Cache-Control"] = "no-store"
    _record_admin_audit(
        db,
        user=user,
        event_type="integration_status_viewed",
        target_ref="current_configuration",
        action="read",
        result="success",
        detail={
            "global_enabled": snapshot.global_enabled,
            "provider_states": {
                item.provider.value: item.configuration_state.value
                for item in snapshot.providers
            },
            "network_probe_performed": False,
        },
    )
    return snapshot


@router.post(
    "/api/v1/admin/integrations/synthetic-send",
    response_model=SyntheticSendResponse,
)
async def admin_synthetic_integration_send(
    request: SyntheticSendRequest,
    http_response: Response,
    idempotency_key_header: str | None = Header(
        default=None, alias="Idempotency-Key", max_length=128
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
    service: IntegrationService = Depends(get_integration_service),
) -> SyntheticSendResponse:
    try:
        header_key = (
            normalise_idempotency_key(idempotency_key_header)
            if idempotency_key_header is not None
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_idempotency_key") from exc
    if request.idempotency_key is not None and header_key is not None:
        if not hmac.compare_digest(request.idempotency_key, header_key):
            raise HTTPException(status_code=409, detail="idempotency_key_mismatch")
    key = request.idempotency_key or header_key
    if key is None:
        raise HTTPException(status_code=422, detail="idempotency_key_required")
    try:
        response = await service.synthetic_send(
            providers=request.providers,
            idempotency_key=key,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="idempotency_key_conflict") from exc
    except IdempotencyCapacityError as exc:
        raise HTTPException(
            status_code=503, detail="idempotency_capacity_unavailable"
        ) from exc

    http_response.headers["Cache-Control"] = "no-store"
    states = {
        receipt.provider.value: receipt.state.value for receipt in response.receipts
    }
    if any(receipt.state == DeliveryState.FAILED for receipt in response.receipts):
        audit_result = (
            "partial" if response.overall_state == "PARTIAL_DELIVERY" else "failed"
        )
    elif all(receipt.state == DeliveryState.DISABLED for receipt in response.receipts):
        audit_result = "disabled"
    else:
        audit_result = "success"
    _record_admin_audit(
        db,
        user=user,
        event_type="synthetic_integration_send",
        target_ref=response.event.event_id,
        action="dispatch",
        result=audit_result,
        detail={
            "providers": [provider.value for provider in request.providers],
            "states": states,
            "replayed_count": sum(
                1 for receipt in response.receipts if receipt.replayed
            ),
            "data_classification": response.event.data_classification,
        },
    )
    return response
