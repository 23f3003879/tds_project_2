from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import tempfile
import shutil
import os
from werkzeug.utils import secure_filename
from agent_task import (
    extract_metadata,
    plan_tasks,
    execute_task_code,
    fix_or_verify_code,
    answer_questions,
    infer_expected_format,
    extract_expected_keys,
    build_safe_defaults,
    normalize_images_in_object,
    force_object_schema,
    normalize_output_keys,
)
import re
import json

app = FastAPI()
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB


@app.post("/api/")
async def handle_request(request: Request):
    if request.headers.get("content-length") and int(request.headers["content-length"]) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=413, detail="Request too large (max 16MB)")

    temp_dir = tempfile.mkdtemp()
    files_map = {}
    questions = ""

    try:
        form = await request.form()
        files_uploaded = form.getlist("files")

        print("FILES RECEIVED:", [f.filename for f in files_uploaded])

        # ✅ Save any uploaded files (any type)
        for file in files_uploaded:
            filename = secure_filename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            contents = await file.read()
            with open(file_path, "wb") as f:
                f.write(contents)

            files_map[filename] = file_path
            print(f"Saved file {filename} ({len(contents)} bytes)")

            if filename.lower() in ("questions.txt", "question.txt"):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    questions = f.read()

        # ✅ If no questions file, maybe questions came as plain text field
        if not questions and "questions" in form:
            questions = str(form["questions"])

        if not questions:
            raise HTTPException(status_code=400, detail="Questions are required (file or text)")

        # ✅ Extract links inside questions and download them
        links = re.findall(r"https?://\S+", questions)
        if links:
            print(f"Found {len(links)} links in questions, attempting download...")
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for i, link in enumerate(links):
                    try:
                        async with session.get(link) as resp:
                            if resp.status == 200:
                                guessed_name = os.path.basename(link.split("?")[0]) or f"link_{i}.dat"
                                filename = secure_filename(guessed_name)
                                file_path = os.path.join(temp_dir, filename)
                                with open(file_path, "wb") as f:
                                    f.write(await resp.read())
                                files_map[filename] = file_path
                                print(f"✅ Downloaded {link} → {filename}")
                            else:
                                print(f"⚠️ Failed to fetch {link}, status={resp.status}")
                    except Exception as e:
                        print(f"❌ Error downloading {link}: {e}")

        if not files_map:
            print("⚠️ Proceeding without files, only questions available")

        # --- Main processing starts ---
        print("🔄 Starting metadata extraction...")
        metadata = extract_metadata(files_map, questions)
        print("✅ Metadata extraction completed")

        try:
            print("🔄 Starting task planning...")
            plan = plan_tasks(questions, files_map, metadata)
            print("✅ Task planning completed")
        except Exception as plan_error:
            print(f"⚠️ Task planning failed: {plan_error}")
            plan = {"steps": []}

        all_code = "\n".join(step.get("code", "") for step in plan.get("steps", []) if step.get("code"))

        required_imports = [
            'import networkx as nx',
            'import pandas as pd',
            'import matplotlib.pyplot as plt',
            'import io',
            'import base64',
            'import json',
        ]
        prepend_imports = []
        for imp in required_imports:
            if imp not in all_code:
                prepend_imports.append(imp)
        all_code = "\n".join(prepend_imports) + "\n" + all_code

        # Remove stray print statements (but keep json.dumps ones)
        code_lines = all_code.splitlines()
        cleaned = []
        for line in code_lines:
            if (("print(result)" in line or "print(results)" in line) and "json.dumps" not in line):
                continue
            if "print(" in line and "json.dumps" not in line and not ("print(result)" in line or "print(results)" in line):
                continue
            cleaned.append(line)
        all_code = "\n".join(cleaned)

        # Force consistent output variable name -> "results"
        if "result =" in all_code and "results =" not in all_code:
            all_code = all_code.replace("result =", "results =")
        all_code = all_code.replace("print(json.dumps(result))", "print(json.dumps(results))")

        # Ensure the final results are printed as JSON
        if "results = {" in all_code and "print(json.dumps(results))" not in all_code:
            all_code += "\nprint(json.dumps(results))"
        
        # Also handle if it's just "result = {" pattern
        if "result = {" in all_code and "print(json.dumps(" not in all_code:
            all_code += "\nprint(json.dumps(result))"

        print("=== FINAL CODE TO EXECUTE ===")
        print(all_code)
        print("=== END CODE ===")

        print("🔄 Starting code execution...")
        result, stderr = execute_task_code(all_code, files_map, timeout=180)
        print("✅ Code execution completed")

        # Debug output
        print("=== SCRIPT RAW STDOUT BEGIN ===")
        lines = [l for l in result.strip().splitlines()]
        for i, line in enumerate(lines):
            print(f"{i}: {repr(line)}")
        print("=== SCRIPT RAW STDOUT END ===")
        print("SCRIPT STDERR:")
        print(stderr)

        # Extract JSON - HANDLE QUOTED STRINGS
        print("🔄 Starting JSON extraction...")
        final_output = None
        lines = [l for l in result.strip().splitlines()]

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
                
            print(f"🔍 Trying to parse line: {line[:100]}...")
            
            try:
                maybe = json.loads(line)  # direct parse
                print(f"✅ Direct JSON parse successful: {type(maybe)}")
            except json.JSONDecodeError:
                if line.startswith("'") and line.endswith("'"):
                    unquoted = line[1:-1]
                    print(f"🔧 Removing quotes, trying: {unquoted[:100]}...")
                    try:
                        maybe = json.loads(unquoted)
                        print(f"✅ Unquoted JSON parse successful: {type(maybe)}")
                    except json.JSONDecodeError as e:
                        print(f"❌ Unquoted parse failed: {e}")
                        continue
                else:
                    print(f"❌ Direct parse failed and no quotes to remove")
                    continue
            except Exception as e:
                print(f"❌ Other error: {e}")
                continue
            
            if isinstance(maybe, str):
                try:
                    maybe = json.loads(maybe)
                    print(f"✅ Double-parsed string: {type(maybe)}")
                except Exception:
                    pass
                    
            if isinstance(maybe, dict):
                final_output = maybe
                print(f"🎉 Found valid dict with keys: {list(maybe.keys())}")
                break

        if final_output is None:
            print("💥 No valid JSON found after trying all methods")
            if result.strip():
                raise Exception(f"Could not parse JSON from output: {result[:200]}...")
        else:
            print(f"✅ Successfully extracted JSON with {len(final_output)} keys")

        print("🔄 Starting post-processing...")
        expected_keys = extract_expected_keys(questions)
        
        if not isinstance(final_output, dict):
            print("⚠️ final_output is not a dict, building safe defaults")
            final_output = build_safe_defaults(questions, expected_keys)
        
        print("🔄 Normalizing images...")
        final_output = normalize_images_in_object(final_output)
        
        print("🔄 Forcing object schema...")
        final_output = force_object_schema(questions, final_output, expected_keys)
        
        print("🔄 Normalizing output keys...")
        final_output = normalize_output_keys(final_output)
        
        print("✅ All post-processing completed")
        print(f"🚀 Returning final output with keys: {list(final_output.keys())}")
        
        return JSONResponse(content=final_output)

    except HTTPException:
        print("❌ HTTPException occurred, re-raising")
        raise
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {type(e).__name__}: {str(e)}")
        print("📍 Error occurred, returning safe defaults")
        try:
            expected_keys = extract_expected_keys(questions if 'questions' in locals() else "")
            safe = build_safe_defaults(questions if 'questions' in locals() else "", expected_keys)
            safe["error"] = str(e)
            print(f"🔧 Returning safe defaults with keys: {list(safe.keys())}")
            return JSONResponse(status_code=200, content=safe)
        except Exception as fallback_error:
            print(f"❌ Even fallback failed: {fallback_error}")
            return JSONResponse(status_code=500, content={"error": "Complete system failure"})
    finally:
        print("🧹 Cleaning up temp directory...")
        shutil.rmtree(temp_dir, ignore_errors=True)
