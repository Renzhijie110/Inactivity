"""Proxy routes for external API."""
from fastapi import APIRouter, HTTPException, Query, Header, status
from typing import Optional
from ..services.external_api import external_api_client

router = APIRouter(prefix="/api/v1", tags=["Proxy"])


@router.get("/scan-records/weekly")
async def proxy_scan_records(
    show_cancelled: str = Query("false"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    order: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    authorization: str = Header(None)
):
    """Proxy scan records request to external API."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token"
        )
    
    return await external_api_client.get_scan_records(
        authorization=authorization,
        show_cancelled=show_cancelled,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        warehouse=warehouse
    )

