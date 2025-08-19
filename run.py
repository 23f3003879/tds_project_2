import sys
import os
import glob
import requests

def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <API_URL> [files...]")
        sys.exit(1)

    url = sys.argv[1]
    file_paths = sys.argv[2:]

    # If no files were passed, auto-detect local files
    if not file_paths:
        guessed = []

        # Questions file is mandatory in eval setup
        if os.path.exists("questions.txt"):
            guessed.append("questions.txt")
        elif os.path.exists("question.txt"):
            guessed.append("question.txt")

        # Also include common dataset file types if present
        for pattern in ("*.csv", "*.json", "*.parquet", "*.xlsx", "*.png", "*.jpg", "*.jpeg"):
            guessed.extend(glob.glob(pattern))

        if not guessed:
            print("[run.py] ERROR: No files found to upload")
            sys.exit(1)

        file_paths = guessed
        print(f"[run.py] Auto-attaching files: {file_paths}")

    files = []
    open_files = []
    try:
        for path in file_paths:
            if not os.path.exists(path):
                print(f"[run.py] ⚠️ Skipping missing file: {path}")
                continue

            with open(path, "rb") as tf:
                preview = tf.read(100)
                size = os.path.getsize(path)
                print(f"[run.py] Will upload {path}: {size} bytes, First 100 bytes: {preview}")

            f = open(path, "rb")
            open_files.append(f)
            files.append(("files", (os.path.basename(path), f)))

        response = requests.post(url, files=files)
        response.raise_for_status()
        print(response.text)

    finally:
        for f in open_files:
            f.close()

if __name__ == "__main__":
    main()
