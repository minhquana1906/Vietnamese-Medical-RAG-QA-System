import asyncio
import time

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException
from loguru import logger

from .config import get_backend_settings
from .models import init_db, insert_document
from .schema import CompleteRequest
from .tasks import chunk_and_index_document, message_handler_task
from .vectorize import create_collection

settings = get_backend_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.on_event("startup")
def on_startup():
    try:
        init_db()
        create_collection()
        logger.info("Application startup complete.")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise


@app.get("/")
def read_root():
    return {"message": f"Welcome to the {settings.app_name} API!"}


@app.get("/ready")
async def readiness_check():
    try:
        return {"status": "ready", "timestamp": time.time()}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


# Task endpoints
@app.post("/chat/complete")
async def chat_complete(request: CompleteRequest):
    bot_id = request.bot_id
    user_id = request.user_id
    user_message = request.user_message
    is_sync_request = request.is_sync_request

    if not bot_id or not user_id or not user_message:
        raise HTTPException(status_code=400, detail="Missing required fields")

    logger.info(f"Chat request from user {user_id} to bot {bot_id}: {user_message}")

    try:
        if is_sync_request:
            response = message_handler_task(bot_id, user_id, user_message)
            return {"status": "completed", "response": response}
        else:
            response = message_handler_task.delay(bot_id, user_id, user_message)
            return {"status": "processing", "task_id": response.id}
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/chat/complete/{task_id}")
async def get_chat_response(task_id: str):
    start = time.time()
    try:
        while True:
            task_result = AsyncResult(task_id)
            task_status = task_result.status
            if task_status == "PENDING" or task_status == "STARTED":
                if time.time() - start > 60:
                    return {
                        "task_id": task_id,
                        "status": task_result.status,
                        "task_result": task_result.result,
                        "error_message": "408 Request Timeout: The task is still pending after 60 seconds.",
                    }
                else:
                    # Wait 0.5s before checking again
                    await asyncio.sleep(0.5)
            else:
                return {
                    "task_id": task_id,
                    "status": task_result.status,
                    "task_result": task_result.result,
                }
    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


# Qdrant endpoints
@app.post("/collections/create")
def create_collection_endpoint(
    collection_name: str = settings.default_collection_name,
    vector_size: int = settings.vector_dimension,
):
    try:
        status = create_collection(collection_name, vector_size)
        return {"status": status}
    except Exception as e:
        logger.error(f"Error creating collection via endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.post("/documents/create")
def insert_document_endpoint(title: str, content: str):
    try:
        new_docs = insert_document(title, content)
        doc_id = str(new_docs.id)
        chunk_and_index_document.delay(doc_id, title, content)
        return {
            "status": "Document received and indexing started.",
            "document_id": doc_id,
        }
    except Exception as e:
        logger.error(f"Error inserting document via endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")
