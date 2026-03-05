from core.routes.auth_routes import router as auth_router
from core.routes.billing_routes import router as billing_router
from core.routes.market_routes import router as market_router
from core.routes.memory_routes import router as memory_router
from core.routes.system_routes import router as system_router
from core.routes.trading_routes import router as trading_router

all_routers = [
    auth_router,
    billing_router,
    market_router,
    memory_router,
    trading_router,
    system_router,
]
