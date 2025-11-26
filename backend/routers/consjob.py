"""Warehouse and items routes."""
from fastapi import APIRouter, HTTPException, Query, Depends, status, Header
from typing import Optional, List
from ..database import db
from ..auth import get_current_user, get_external_api_authorization
from ..models import ItemsResponse
from ..services.external_api import external_api_client

router = APIRouter(prefix="/api/consjob", tags=["ConsJob"])

# 固定的仓库列表
WAREHOUSES = ['JFK', 'EWR', 'PHL', 'DCA', 'BOS', 'RDU', 'CLT', 'BUF', 'RIC', 'PIT', 'MDT', 'ALB', 'SYR', 'PWM']

@router.get("/")
async def get_consjob(
    current_user: str = Depends(get_current_user),
    sync: bool = Query(False, description="是否从外部API同步数据到数据库"),
    warehouse: Optional[str] = Query(None, description="指定要同步的仓库，不指定则同步所有仓库"),
    authorization: str = Header(None)
):
    """Get consjob list. If sync=true, fetch warehouse data from external API and save to database."""
    if sync:
        # 获取外部API token（仅在sync时需要）
        try:
            external_auth = await get_external_api_authorization(authorization)
        except HTTPException as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要外部API token来同步数据，请重新登录"
            )
        # 确定要处理的仓库列表
        warehouses_to_sync = [warehouse] if warehouse and warehouse in WAREHOUSES else WAREHOUSES
        
        if warehouse and warehouse not in WAREHOUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的仓库代码: {warehouse}"
            )
        
        try:
            # 逐个处理仓库，提高健壮性
            warehouse_results = []
            total_saved = 0
            total_items = 0
            successful_warehouses = 0
            failed_warehouses = 0
            
            for wh in warehouses_to_sync:
                try:
                    # 获取单个仓库的数据（使用自动获取的外部API token）
                    warehouse_result = await external_api_client.get_warehouse_data(
                        authorization=external_auth,
                        warehouse=wh,
                        show_cancelled="false",
                        page_size=100
                    )
                    
                    if warehouse_result["success"]:
                        # 保存该仓库的数据到数据库
                        items = warehouse_result["items"]
                        saved_count = await db.save_consjob_data(items)
                        
                        warehouse_results.append({
                            "warehouse": wh,
                            "success": True,
                            "items_fetched": warehouse_result["total_items"],
                            "items_saved": saved_count,
                            "error": None
                        })
                        
                        total_items += warehouse_result["total_items"]
                        total_saved += saved_count
                        successful_warehouses += 1
                    else:
                        warehouse_results.append({
                            "warehouse": wh,
                            "success": False,
                            "items_fetched": 0,
                            "items_saved": 0,
                            "error": warehouse_result["error"]
                        })
                        failed_warehouses += 1
                        
                except Exception as e:
                    # 单个仓库失败不影响其他仓库
                    error_msg = str(e)
                    print(f"Error processing warehouse {wh}: {error_msg}")
                    warehouse_results.append({
                        "warehouse": wh,
                        "success": False,
                        "items_fetched": 0,
                        "items_saved": 0,
                        "error": error_msg
                    })
                    failed_warehouses += 1
                    continue
            
            return {
                "success": True,
                "message": f"同步完成: {successful_warehouses} 个仓库成功, {failed_warehouses} 个仓库失败",
                "total_warehouses": len(warehouses_to_sync),
                "successful_warehouses": successful_warehouses,
                "failed_warehouses": failed_warehouses,
                "total_items_fetched": total_items,
                "total_items_saved": total_saved,
                "warehouse_results": warehouse_results
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"同步数据失败: {str(e)}"
            )
    else:
        # 返回数据库中的 consjob 列表
        return await db.get_consjob_list()


@router.post("/sync/{warehouse}")
async def sync_warehouse(
    warehouse: str,
    current_user: str = Depends(get_current_user),
    authorization: str = Header(None)
):
    """Sync data for a specific warehouse from external API to database."""
    if warehouse not in WAREHOUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的仓库代码: {warehouse}. 有效的仓库: {', '.join(WAREHOUSES)}"
        )
    
    # 获取外部API token
    try:
        external_auth = await get_external_api_authorization(authorization)
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要外部API token来同步数据，请重新登录"
        )
    
    try:
        # 获取单个仓库的数据（使用自动获取的外部API token）
        warehouse_result = await external_api_client.get_warehouse_data(
            authorization=external_auth,
            warehouse=warehouse,
            show_cancelled="false",
            page_size=100
        )
        
        if warehouse_result["success"]:
            # 保存数据到数据库
            items = warehouse_result["items"]
            saved_count = await db.save_consjob_data(items)
            
            return {
                "success": True,
                "warehouse": warehouse,
                "items_fetched": warehouse_result["total_items"],
                "items_saved": saved_count,
                "message": f"成功同步 {saved_count} 条 {warehouse} 仓库数据到数据库"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取 {warehouse} 仓库数据失败: {warehouse_result['error']}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步 {warehouse} 仓库数据失败: {str(e)}"
        )


@router.get("/{consjob_id}")
async def get_consjob_by_id(
    consjob_id: int,
    current_user: str = Depends(get_current_user)
):