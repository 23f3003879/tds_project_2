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

    if not file_paths:
        guessed = []
        if os.path.exists("questions.txt"):
            guessed.append("questions.txt")
        elif os.path.exists("question.txt"):
            guessed.append("question.txt")

        for pattern in ("*.csv", "*.json", "*.parquet", "*.xlsx", "*.png", "*.jpg", "*.jpeg"):
            guessed.extend(glob.glob(pattern))

        if not guessed:
            print("[run.py] ERROR: No files found to upload")
            sys.exit(1)

        file_paths = guessed
        print(f"[run.py] Auto-attaching files: {file_paths}")

    # Attach files all under the same "files" field
    open_files = [open(path, "rb") for path in file_paths]
    files = [("files", (os.path.basename(path), f)) for path, f in zip(file_paths, open_files)]

    try:
        response = requests.post(url, files=files)
        response.raise_for_status()
        print(response.text)
    finally:
        for f in open_files:
            f.close()

if __name__ == "__main__":
    main()
