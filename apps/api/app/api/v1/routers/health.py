from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "_debug_client_host": request.client.host if request.client else "none",
        "_debug_xff": request.headers.get("x-forwarded-for", ""),
        "_debug_x_real_ip": request.headers.get("x-real-ip", ""),
    }
