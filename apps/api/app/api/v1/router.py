from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    ai_analyst,
    analysis,
    api_keys,
    auth,
    billing,
    dashboards,
    datasets,
    health,
    industry,
    organizations,
    reports,
    saved_scenarios,
    scheduled_reports,
    sso,
    users,
    webhooks,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)
api_router.include_router(workspaces.router)
api_router.include_router(datasets.router)
api_router.include_router(analysis.router)
api_router.include_router(reports.router)
api_router.include_router(ai_analyst.router)
api_router.include_router(billing.router)
api_router.include_router(industry.router)
api_router.include_router(dashboards.router)
api_router.include_router(scheduled_reports.router)
api_router.include_router(api_keys.router)
api_router.include_router(admin.router)
api_router.include_router(webhooks.router)
api_router.include_router(sso.router)
api_router.include_router(saved_scenarios.router)
