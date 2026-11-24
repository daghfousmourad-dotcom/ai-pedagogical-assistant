import os
import shutil
import json
from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import JSONResponse
from celery_worker import index_pdf_task, index_pdf_advanced_task, celery_app
from api.dependencies import get_cleanup
import api.dependencies_state as ds

router = APIRouter(prefix="/api/ai", tags=["Indexing"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload-pdf")
async def upload_to_qdrant(request: Request):
    content_type = request.headers.get("content-type", "")
    pdf_path = None
    mongo_id = None
    try:
        raw_body = await request.body()
        if "application/json" in content_type:
            if raw_body:
                data = json.loads(raw_body)
                pdf_path = data.get("pdf_path")
                mongo_id = data.get("mongo_id")
        elif "multipart/form-data" in content_type:
            form = await request.form()
            file = form.get("file")
            pdf_path_form = form.get("pdf_path")
            mongo_id = form.get("mongo_id")
            if file and isinstance(file, UploadFile):
                temp_path = os.path.join(UPLOAD_DIR, file.filename)
                with open(temp_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                pdf_path = temp_path
            elif pdf_path_form:
                pdf_path = pdf_path_form
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Parsing error: {str(e)}"})

    if not pdf_path:
        return JSONResponse(status_code=400, content={"status": "error", "message": "No file or path provided"})
    pdf_path = os.path.abspath(pdf_path.strip('"').strip("'"))
    if not os.path.exists(pdf_path):
        return JSONResponse(status_code=404, content={"status": "error", "message": f"File not found: {pdf_path}"})

    try:
        task = index_pdf_task.delay(pdf_path, mongo_id)
        # Stocker le mapping mongo_id -> task_id dans Redis (TTL: 2h)
        if mongo_id and ds.redis_client:
            await ds.redis_client.set(f"task_for_doc:{mongo_id}", task.id, ex=7200)
        return {"status": "success", "task_id": task.id, "message": f"Indexing started for: {os.path.basename(pdf_path)}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/upload-pdf-advanced")
async def upload_to_qdrant_advanced(request: Request):
    content_type = request.headers.get("content-type", "")
    pdf_path = None
    mongo_id = None
    raw_body = await request.body()
    try:
        if "application/json" in content_type:
            if not raw_body:
                return JSONResponse(status_code=400, content={"status": "error", "message": "Empty body"})
            data = json.loads(raw_body)
            pdf_path = data.get("pdf_path")
            mongo_id = data.get("mongo_id")
        elif "multipart/form-data" in content_type:
            form = await request.form()
            file = form.get("file")
            pdf_path_form = form.get("pdf_path")
            mongo_id = form.get("mongo_id")
            if file and isinstance(file, UploadFile):
                temp_path = os.path.join(UPLOAD_DIR, file.filename)
                with open(temp_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                pdf_path = temp_path
            elif pdf_path_form:
                pdf_path = pdf_path_form
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Parsing error: {str(e)}"})

    if not pdf_path:
        return JSONResponse(status_code=400, content={"status": "error", "message": "No file or path provided"})
    pdf_path = os.path.abspath(pdf_path.strip('"').strip("'"))
    if not os.path.exists(pdf_path):
        return JSONResponse(status_code=404, content={"status": "error", "message": f"File not found: {pdf_path}"})

    try:
        task = index_pdf_advanced_task.delay(pdf_path, mongo_id)
        # Stocker le mapping mongo_id -> task_id dans Redis (TTL: 2h)
        if mongo_id and ds.redis_client:
            await ds.redis_client.set(f"task_for_doc:{mongo_id}", task.id, ex=7200)
        return {"status": "success", "task_id": task.id, "message": f"Advanced indexing started for: {os.path.basename(pdf_path)}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """Lit l'état d'une tâche Celery depuis Redis (par task_id direct)."""
    task = celery_app.AsyncResult(task_id)
    return _build_status_response(task)

@router.get("/doc-progress/{mongo_id}")
async def get_doc_progress(mongo_id: str):
    """Retrouve le task_id via le mongo_id et retourne la progression (sans modification Java)."""
    if not ds.redis_client:
        return {"state": "PENDING", "percent": 0}
    task_id = await ds.redis_client.get(f"task_for_doc:{mongo_id}")
    if not task_id:
        return {"state": "PENDING", "percent": 0}
    task = celery_app.AsyncResult(task_id)
    return _build_status_response(task)

def _build_status_response(task):
    if task.state == 'PROGRESS':
        info = task.info or {}
        return {
            "state": "PROGRESS",
            "percent": info.get('percent', 0),
            "current": info.get('current', 0),
            "total": info.get('total', 0)
        }
    elif task.state == 'SUCCESS':
        return {"state": "SUCCESS", "percent": 100}
    elif task.state == 'FAILURE':
        return {"state": "FAILURE", "percent": 0, "error": str(task.info)}
    else:
        return {"state": task.state, "percent": 0}

@router.get("/documents/ids")
async def get_all_document_ids():
    try:
        cleaner = get_cleanup()
        ids = cleaner.get_all_mongo_ids()
        return {"status": "success", "ids": ids}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.delete("/documents/{mongo_id}")
async def delete_document_vectors(mongo_id: str):
    try:
        cleaner = get_cleanup()
        cleaner.delete_by_mongo_id(mongo_id)
        return {"status": "success", "message": f"Successfully deleted vectors for: {mongo_id}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.delete("/cleanup")
async def delete_by_source(source: str):
    try:
        cleaner = get_cleanup()
        cleaner.delete_by_source_path(source)
        return {"status": "success", "message": f"Successfully deleted vectors for source: {source}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
