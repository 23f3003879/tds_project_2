from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List
import tempfile, shutil, os
from werkzeug.utils import secure_filename
from agent_task import (
    extract_metadata,
    plan_tasks,
    execute_task_code,
    fix_or_verify_code,
    answer_questions
)

app = FastAPI()
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

@app.post("/api/")
async def handle_request(request: Request, files: List[UploadFile] | None = File(None)):
    # Request size check
    if request.headers.get("content-length") and int(request.headers["content-length"]) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=413, detail="Request too large (max 16MB)")

    temp_dir = tempfile.mkdtemp()
    files_map = {}
    try:
        form = await request.form()
        questions_file = None

        # Save files from multipart form
        for key, value in form.multi_items():
            if hasattr(value, "filename") and value.filename:
                filename = secure_filename(value.filename)
                file_path = os.path.join(temp_dir, filename)
                content = await value.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                files_map[filename] = file_path
                if filename.lower() in ("questions.txt", "question.txt"):
                    questions_file = file_path

        # Save files passed via 'files' field (alternative method)
        if files:
            for upload in files:
                if upload and upload.filename:
                    filename = secure_filename(upload.filename)
                    file_path = os.path.join(temp_dir, filename)
                    content = await upload.read()
                    with open(file_path, "wb") as f:
                        f.write(content)
                    files_map[filename] = file_path
                    if filename.lower() in ("questions.txt", "question.txt"):
                        questions_file = file_path

        if not questions_file:
            raise HTTPException(status_code=400, detail="questions.txt is required")

        # Read questions
        with open(questions_file, "r") as f:
            questions = f.read()

        # ---------------------------
        # 1. Extract Metadata (fast, universal)
        # ---------------------------
        metadata = extract_metadata(files_map, questions)

        # ---------------------------
        # 2. Plan Tasks
        # ---------------------------
        plan = plan_tasks(questions, files_map, metadata)

        # ---------------------------
        # 3. Execute & Fix/Verify Steps
        # ---------------------------
        for step in plan.get("steps", []):
            if step.get("action") in ["scrape_url", "run_code", "load_file"]:
                code_str = step.get("code") or ""
                if not code_str:
                    step["result"] = ""
                    continue
                result, stderr = execute_task_code(code_str, files_map, timeout=90)
                if stderr or not result:
                    fixed_code = fix_or_verify_code(code_str, result, stderr)
                    if fixed_code:
                        result, stderr = execute_task_code(fixed_code, files_map, timeout=60)
                step["result"] = result

        # ---------------------------
        # 4. Answer Questions
        # ---------------------------
        final_output = answer_questions(questions, plan)
        return JSONResponse(content=final_output)

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
