"""External API client service."""
import httpx
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
from ..config import settings


class ExternalAPIClient:
    """Client for external API requests."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.external_api_base
        self.timeout = settings.api_timeout
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the external API."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    data=data,
                    timeout=self.timeout
                )
                
                # Handle 401 Unauthorized
                if response.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="认证失败"
                    )
                
                # Handle other errors
                if response.status_code != 200:
                    error_data = {}
                    if response.headers.get("content-type", "").startswith("application/json"):
                        try:
                            error_data = response.json()
                        except Exception:
                            pass
                    
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=error_data.get("detail", "请求失败")
                    )
                
                return response.json()
                
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"无法连接到外部API: {str(e)}"
            )
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Proxy login request to external API."""
        return await self._request(
            method="POST",
            endpoint="/api/v1/auth/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "accept": "application/json"
            },
            data={
                "username": username,
                "password": password
            }
        )
    
    async def get_scan_records(
        self,
        authorization: str,
        show_cancelled: str = "false",
        page: int = 1,
        page_size: int = 10,
        sort: Optional[str] = None,
        order: Optional[str] = None,
        warehouse: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get scan records from external API."""
        params = {
            "show_cancelled": show_cancelled,
            "page": page,
            "page_size": page_size,
        }
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        if warehouse:
            params["warehouse"] = warehouse
        
        return await self._request(
            method="GET",
            endpoint="/api/v1/scan-records/weekly",
            headers={
                "Authorization": authorization,
                "accept": "application/json"
            },
            params=params
        )
    
    async def get_warehouse_data(
        self,
        authorization: str,
        warehouse: str,
        show_cancelled: str = "false",
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Get warehouse data from external API for a single warehouse.
        
        Args:
            authorization: Authorization token
            warehouse: Warehouse code
            show_cancelled: Whether to show cancelled records
            page_size: Page size for pagination
            
        Returns:
            Dictionary with 'success', 'warehouse', 'items', 'total_items', 'error' keys
        """
        try:
            all_items = []
            
            # Get first page to determine total pages
            first_response = await self.get_scan_records(
                authorization=authorization,
                show_cancelled=show_cancelled,
                page=1,
                page_size=page_size,
                sort="nonupdated_start_timestamp",
                order="desc",
                warehouse=warehouse
            )
            
            # Extract items from response
            items_data = first_response.get("data") or first_response.get("items") or []
            if isinstance(items_data, list):
                all_items.extend(items_data)
            
            # Get pagination info
            pagination = first_response.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)
            
            # Fetch remaining pages
            for page in range(2, total_pages + 1):
                try:
                    response = await self.get_scan_records(
                        authorization=authorization,
                        show_cancelled=show_cancelled,
                        page=page,
                        page_size=page_size,
                        sort="nonupdated_start_timestamp",
                        order="desc",
                        warehouse=warehouse
                    )
                    
                    page_items = response.get("data") or response.get("items") or []
                    if isinstance(page_items, list):
                        all_items.extend(page_items)
                except Exception as e:
                    print(f"Error fetching page {page} for warehouse {warehouse}: {e}")
                    # Continue with other pages even if one fails
                    continue
            
            return {
                "success": True,
                "warehouse": warehouse,
                "items": all_items,
                "total_items": len(all_items),
                "error": None
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error fetching data for warehouse {warehouse}: {error_msg}")
            return {
                "success": False,
                "warehouse": warehouse,
                "items": [],
                "total_items": 0,
                "error": error_msg
            }
    
    async def get_all_warehouse_data(
        self,
        authorization: str,
        warehouses: List[str],
        show_cancelled: str = "false",
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Get all warehouse data from external API for multiple warehouses.
        
        Args:
            authorization: Authorization token
            warehouses: List of warehouse codes
            show_cancelled: Whether to show cancelled records
            page_size: Page size for pagination
            
        Returns:
            Dictionary with 'results' (list of warehouse results), 'total_items', 'successful_count', 'failed_count'
        """
        results = []
        all_items = []
        successful_count = 0
        failed_count = 0
        
        for warehouse in warehouses:
            result = await self.get_warehouse_data(
                authorization=authorization,
                warehouse=warehouse,
                show_cancelled=show_cancelled,
                page_size=page_size
            )
            
            results.append(result)
            
            if result["success"]:
                successful_count += 1
                all_items.extend(result["items"])
            else:
                failed_count += 1
        
        return {
            "results": results,
            "all_items": all_items,
            "total_items": len(all_items),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "total_warehouses": len(warehouses)
        }


# Global client instance
external_api_client = ExternalAPIClient()

