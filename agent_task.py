import json, os, re, csv
import pandas as pd
import requests
from io import BytesIO, StringIO
from llm_client import call_llm
from sandbox import run_code_safely

MAX_BASE64_BYTES = 100_000
MAX_ROWS_PREVIEW = 20
MAX_BYTES_FETCH = 200_000  # ~200KB fetch cap for URLs

# ---------------------------
# Utility Functions
# ---------------------------
def parse_json_loosely(text: str):
    if not text or not text.strip():
        raise ValueError("Empty response from LLM")

    s = text.strip()

    # Remove markdown fenced code blocks ```json ... ```
    fence_pattern = r"^```(?:json)?\s*([\s\S]*?)\s*```"
    m = re.match(fence_pattern, s, flags=re.IGNORECASE)
    if m:
        s = m.group(1).strip()

    # If JSON isn't at the start, find the first {...} or [...]
    if not (s.startswith("{") or s.startswith("[")):
        m2 = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", s)
        if m2:
            s = m2.group(1)

    if not s:
        raise ValueError("No JSON content found in response")

    # Remove illegal ASCII control chars except common ones \r\n\t
    s = "".join(ch for ch in s if ch >= " " or ch in "\r\n\t")

    # Normalize quotes and slashes
    s = s.replace("\r\n", "\n")
    s = s.replace("\\\\", "\\")
    s = re.sub(r'\\"', '"', s)

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Remove bad escape sequences (anything like \X where X is not valid)
        s = re.sub(r'\\(?!["\\/bfnrt])', '', s)
        return json.loads(s)


def infer_expected_format(questions_text: str):
    """Infer expected output format from questions text."""
    # Look for JSON object example in questions
    m = re.search(r'(\{[\s\S]*\})', questions_text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return ("object", list(obj.keys()))
        except Exception:
            pass
    
    # Count numbered questions
    count = len(re.findall(r'^\s*\d+\.\s+', questions_text, re.M))
    if count:
        return ("array", count)
    
    return ("unknown", None)

def coerce_result_to_format(data, expected):
    """Coerce result to match expected format."""
    kind, meta = expected
    if kind == "array":
        if isinstance(data, dict):
            data = list(data.values())
        if not isinstance(data, list):
            data = [data]
        if isinstance(meta, int):
            if len(data) < meta:
                data += [None] * (meta - len(data))
            elif len(data) > meta:
                data = data[:meta]
        return data
    if kind == "object" and isinstance(meta, list):
        if isinstance(data, list):
            return {k: (data[i] if i < len(data) else None) for i, k in enumerate(meta)}
        if isinstance(data, dict):
            return {k: data.get(k) for k in meta}
        return {k: None for k in meta}
    return data

def infer_answer_types(questions_text: str) -> list[str]:
    """Infer expected data types for each answer based on question content."""
    q_lines = [q.strip() for q in re.findall(r'^\s*\d+\.\s+(.*)', questions_text, re.M)] or [questions_text.strip()]
    types_out = []
    for q in q_lines:
        lq = q.lower()
        if any(k in lq for k in ["how many", "count", "number of"]):
            types_out.append("int")
        elif any(k in lq for k in ["correlation", "slope", "mean", "median", "std", "rate"]):
            types_out.append("float")
        elif any(k in lq for k in ["plot", "figure", "chart", "encode", "base64", "image"]):
            types_out.append("image")
        elif any(k in lq for k in ["earliest", "first", "which", "who", "name", "title"]):
            types_out.append("string")
        else:
            types_out.append("string")
    return types_out

def coerce_by_types(data: list, types_out: list[str]) -> list:
    """Coerce individual answer values to their inferred types."""
    out = []
    for i, val in enumerate(data):
        t = types_out[i] if i < len(types_out) else "string"
        if t == "int":
            m = re.search(r'[-+]?\d+', str(val))
            out.append(int(m.group(0)) if m else 0)
        elif t == "float":
            m = re.search(r'[-+]?(?:\d*\.\d+|\d+)', str(val))
            out.append(float(m.group(0)) if m else 0.0)
        elif t == "image":
            s = str(val) if val is not None else ""
            s = s if s.startswith("data:image") else ""
            out.append(s[:MAX_BASE64_BYTES] if s else "")
        else:
            out.append("" if val is None else str(val))
    return out

# ---------------------------
# Metadata Extraction
# ---------------------------
def extract_metadata(files_map, questions_text):
    metadata = {}

    # 1. Add uploaded files
    for name, path in files_map.items():
        metadata[name] = get_file_metadata(path)

    # 2. Detect URLs in questions.txt
    urls = re.findall(r"https?://\S+", questions_text)
    for i, url in enumerate(urls, start=1):
        try:
            resp = requests.get(url, timeout=5, stream=True)
            resp.raise_for_status()
            content = resp.content[:MAX_BYTES_FETCH]
            # Save to temp file for consistency
            tmp_path = f"/tmp/url_source_{i}"
            with open(tmp_path, "wb") as f:
                f.write(content)
            metadata[url] = get_file_metadata(tmp_path, url=url)
        except Exception as e:
            metadata[url] = {"error": str(e)}

    return metadata

def get_file_metadata(path, url=None):
    info = {"source": url or path}
    try:
        ext = os.path.splitext(path)[1].lower()

        if ext in [".csv", ".tsv"]:
            df = pd.read_csv(path, nrows=MAX_ROWS_PREVIEW)
            info.update({
                "type": "table",
                "columns": list(df.columns),
                "rows_preview": df.head(5).to_dict(orient="records"),
                "row_count_est": len(df)
            })

        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(path, nrows=MAX_ROWS_PREVIEW)
            info.update({
                "type": "spreadsheet",
                "columns": list(df.columns),
                "rows_preview": df.head(5).to_dict(orient="records"),
                "row_count_est": len(df)
            })

        elif ext in [".json"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            info.update({
                "type": "json",
                "keys": list(data.keys()) if isinstance(data, dict) else None,
                "sample": data[:5] if isinstance(data, list) else None
            })

        else:
            # Fallback: read text preview
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text_sample = f.read(1000)
            info.update({
                "type": "text",
                "preview": text_sample
            })

    except Exception as e:
        info["error"] = str(e)
    return info

# ---------------------------
# LLM Prompts
# ---------------------------
PLANNER_SYSTEM = (
    "You are an expert data analyst. "
    "Given QUESTIONS, ATTACHMENTS metadata, and available data sources, "
    "break them into programmable ordered steps or tasks. Provide executable Python where suitable. "
    "Do NOT invent data — use only provided files or URLs in QUESTIONS. "
    "If plotting, label axes and draw a dotted red regression line; return PNG base64 under the size limit. "
    f"Keep image data URIs under {MAX_BASE64_BYTES} bytes by using small figures. "
    "Output plain JSON only (no markdown). Return strictly valid JSON: "
    "{plan_text: [...], steps: [{id, action, args, code, estimated_seconds}], estimated_total_seconds: int}."
)

FIX_VERIFY_SYSTEM = (
    "You are a Python debugging assistant. "
    "Given code, stdout, and stderr, return corrected code only if needed. "
    "If output format is wrong, adjust it to match the intended JSON format."
)

ANSWERER_SYSTEM = (
    "You are a concise analyst. Given QUESTIONS and the results of each step, "
    "produce final JSON in the requested format. Output valid JSON only."
)

# ---------------------------
# Core Functions
# ---------------------------
def plan_tasks(questions, files, metadata):
    user_prompt = f"QUESTIONS:\n{questions}\n\nMETADATA:\n{json.dumps(metadata, indent=2)}"
    resp = call_llm(PLANNER_SYSTEM, user_prompt)
    print("DEBUG - Raw LLM response for plan_tasks:\n", resp)
    try:
        return parse_json_loosely(resp)
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON for planning:\n{resp}\nError: {e}")

def execute_task_code(code, files, timeout=60):
    with open("requirements.txt") as reqfile:
        requirements = reqfile.read()
    success, stdout, stderr = run_code_safely(code, files, requirements, timeout=timeout)
    return stdout.strip(), stderr.strip()

def fix_or_verify_code(code, stdout, stderr):
    if not stderr and stdout:
        return code  # no fix needed
    prompt = json.dumps({"code": code, "stdout": stdout, "stderr": stderr})
    fixed_code = call_llm(FIX_VERIFY_SYSTEM, prompt)
    return fixed_code.strip()

def answer_questions(questions, plan, max_retries=2):
    artifacts_preview = {s["id"]: s.get("result", "")[:500] for s in plan.get("steps", [])}
    prompt = f"QUESTIONS:\n{questions}\n\nARTIFACTS:\n{json.dumps(artifacts_preview)}"
    
    for attempt in range(max_retries + 1):
        resp = call_llm(ANSWERER_SYSTEM, prompt).strip()
        
        if not resp:
            if attempt < max_retries:
                continue
            raise ValueError("LLM returned empty answer after retries")
        
        try:
            data = parse_json_loosely(resp)
            expected = infer_expected_format(questions)
            
            # Apply type coercion based on inferred types
            if expected[0] == "array" and isinstance(data, list):
                data = coerce_by_types(data, infer_answer_types(questions))
            elif expected[0] == "object" and isinstance(data, dict):
                question_list = expected[1]
                inferred_types_for_keys = infer_answer_types(questions)
                coerced_values = coerce_by_types(list(data.values()), inferred_types_for_keys)
                data = {k: coerced_values[i] for i, k in enumerate(question_list)}
            
            return coerce_result_to_format(data, expected)
            
        except Exception as e:
            if attempt < max_retries:
                # Append clarification for the LLM to try again
                prompt += "\n\nPlease return only valid JSON. No markdown, no explanations."
                continue
            raise ValueError(f"LLM returned invalid JSON after retries:\n{resp}\nError: {e}")
