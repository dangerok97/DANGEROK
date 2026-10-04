def test_vonage_router_imports_cleanly():
    from telephone.vonage_router import router

    paths = {getattr(route, "path", "") for route in router.routes}
    for needed in ("/vonage/answer", "/vonage/event", "/vonage/fallback", "/vonage/socket"):
        assert needed in paths
