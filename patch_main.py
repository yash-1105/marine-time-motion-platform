with open("apps/api/main.py", "r") as f:
    text = f.read()

text = text.replace("from apps.api.routers.ingestion import router as ingestion_router", "from apps.api.routers.ingestion import router as ingestion_router\nfrom apps.api.routers.quality import router as quality_router")
text = text.replace("v1_router.include_router(ingestion_router)", "v1_router.include_router(ingestion_router)\nv1_router.include_router(quality_router)")

with open("apps/api/main.py", "w") as f:
    f.write(text)
