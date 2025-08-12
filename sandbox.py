import subprocess
import tempfile
import os
import shutil
import uuid
import shutil as _shutil

DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")

def _docker_available() -> bool:
    """Check if Docker is available and enabled."""
    if os.getenv("DISABLE_DOCKER", "0") == "1":
        return False
    return _shutil.which("docker") is not None

def _run_subprocess(code_path: str, workdir: str, timeout: int):
    """Run Python code in a subprocess without Docker."""
    try:
        proc = subprocess.run(
            ["python", os.path.basename(code_path)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (proc.returncode == 0, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", f"timeout after {timeout}s")

def run_code_safely(code: str, attachments: dict, requirements: str, timeout: int = 60):
    """Run code inside a Docker sandbox if available, else use local subprocess."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Copy attachments into temp_dir
        for name, path in attachments.items():
            safe_name = name.replace("/", "_")
            shutil.copy2(path, os.path.join(temp_dir, safe_name))

        # Write the main script file
        script_path = os.path.join(temp_dir, "agent_step.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Write requirements (for debugging visibility)
        with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write(requirements)

        if _docker_available():
            container_name = f"ds-agent-{uuid.uuid4()}"
            cmd = [
                "docker", "run", "--rm",
                f"--name={container_name}",
                "-v", f"{temp_dir}:/code",
                "-w", "/code",
                "--network=none",
                DOCKER_IMAGE,
                "timeout", str(timeout),
                "python", "agent_step.py",
            ]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 5
                )
                return (result.returncode == 0, result.stdout, result.stderr)
            except subprocess.TimeoutExpired:
                return (False, "", f"timeout after {timeout}s")
            except Exception:
                # Fall through to subprocess fallback if Docker fails
                pass

        # Fallback: run in regular subprocess (no Docker)
        return _run_subprocess(script_path, temp_dir, timeout)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
