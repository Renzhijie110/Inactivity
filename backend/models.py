"""Pydantic models for request/response validation."""
from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    """User information model."""
    username: str


class WarehouseInfo(BaseModel):
    """Warehouse information model."""
    code: str
    count: int


class ItemInfo(BaseModel):
    """Item information model."""
    id: int
    tracking_number: Optional[str]
    order_id: Optional[str]
    warehouse: Optional[str]
    zone: Optional[str]
    driver_id: Optional[str]
    current_status: Optional[str]
    nonupdated_start_timestamp: Optional[str]


class PaginationInfo(BaseModel):
    """Pagination information model."""
    page: int
    page_size: int
    total: int
    total_pages: int


class ItemsResponse(BaseModel):
    """Items response model."""
    success: bool
    data: list[ItemInfo]
    pagination: PaginationInfo
    warehouse_stats: dict[str, int]

