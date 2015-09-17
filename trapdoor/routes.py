
from trapdoor import handlers,utils

HANDLERS = [
    (r"/", handlers.Index),
    (r"/resolve/?", handlers.Resolve),
    (r"/resolve_all/?", handlers.ResolveAll),

    #messageWall
    (r"/wall", handlers.Wall),

    #websocket
    (r"/socket", utils.ChatSocketHandler),

    # API
    (r"/api/varbinds/(?P<notification_id>\d+)", handlers.ApiVarBinds),
    (r"/api/activetraps/?", handlers.ApiActiveTraps),
    (r"/api/traps/?", handlers.ApiTraps),

    # Default
    (r"/.*", handlers.NotFound),
]
