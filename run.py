import sys
import requests

def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <API_URL> [files...]")
        sys.exit(1)

    url = sys.argv[1]
    file_paths = sys.argv[2:]

    files = []
    open_files = []
    try:
        # Pre-upload file diagnostics
        for path in file_paths:
            # Check file exists and show its size and first few bytes
            with open(path, "rb") as tf:
                file_data = tf.read()
                print(f"[run.py] Will upload {path}: {len(file_data)} bytes, First 100 bytes: {file_data[:100]}")
            f = open(path, "rb")
            open_files.append(f)
            files.append(("files", f))

        response = requests.post(url, files=files)
        response.raise_for_status()
        print(response.text)

    finally:
        for f in open_files:
            f.close()

if __name__ == "__main__":
    main()
