# Data Analyst Agent

An API that uses Large Language Models (LLMs) to source, prepare, analyze, and visualize given data. The agent can handle web scraping, data extraction, statistical analysis, and generate visualizations with a simple API endpoint.

## 🚀 Features

- **Multi-format Data Support**: CSV, TSV, JSON, Excel, Parquet files
- **Web Scraping**: Automatic extraction from URLs mentioned in questions
- **Statistical Analysis**: Correlation, regression, descriptive statistics
- **Data Visualization**: Generate scatterplots, charts with regression lines
- **Flexible Output**: JSON arrays or objects based on question format
- **Sandboxed Execution**: Secure code execution environment
- **Multiple LLM Support**: OpenAI GPT and Google Gemini integration
- **Fast Response**: Designed to answer within 3 minutes

## 📋 Requirements

- Python 3.8+
- LLM API key (OpenAI or Google Gemini)
- Docker (optional, for enhanced sandboxing)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd data-analyst-agent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   # On Windows
   .venv\Scripts\activate
   # On Unix/MacOS
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   cd app
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # For OpenAI
   $env:OPENAI_API_KEY="your-openai-api-key"
   $env:LLM_PROVIDER="openai"
   
   # For Google Gemini
   $env:GEMINI_API_KEY="your-gemini-api-key"
   $env:LLM_PROVIDER="gemini"
   ```

## 🚀 Usage

### Starting the Server

```bash
cd app
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### API Endpoint

**POST** `http://127.0.0.1:8000/api/`

### Request Format

Send a `multipart/form-data` request with:
- `questions.txt` (required): Contains your data analysis questions
- Additional files (optional): CSV, JSON, Excel, etc.

### Example Request

```bash
curl -X POST "http://127.0.0.1:8000/api/" \
  -F "questions.txt=@questions.txt" \
  -F "data.csv=@data.csv"
```

### Example Questions File

```txt
Scrape the list of highest grossing films from Wikipedia. It is at the URL:
https://en.wikipedia.org/wiki/List_of_highest-grossing_films

Answer the following questions and respond with a JSON array of strings containing the answer.

1. How many $2 bn movies were released before 2000?
2. Which is the earliest film that grossed over $1.5 bn?
3. What's the correlation between the Rank and Peak?
4. Draw a scatterplot of Rank and Peak along with a dotted red regression line through it.
   Return as a base-64 encoded data URI, `"data:image/png;base64,iVBORw0KG..."` under 100,000 bytes.
```

### Example Response

```json
[1, "Titanic", 0.485782, "data:image/png;base64,iVBORw0KG..."]
```

## 🏗️ Architecture

The application uses an **agentic execution loop**:

1. **Planner LLM**: Analyzes questions and creates execution plan
2. **Code Execution**: Runs Python code in sandboxed environment
3. **Critic/Fixer LLM**: Validates and fixes code errors
4. **Answerer LLM**: Formats final response in requested format

### Core Components

- **`main.py`**: FastAPI application and request handling
- **`agent_task.py`**: Core agent logic and LLM prompts
- **`llm_client.py`**: LLM provider abstraction (OpenAI/Gemini)
- **`sandbox.py`**: Secure code execution environment

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider: "openai" or "gemini" | "openai" |
| `OPENAI_API_KEY` | OpenAI API key | Required if using OpenAI |
| `GEMINI_API_KEY` | Google Gemini API key | Required if using Gemini |
| `OPENAI_CHAT_MODEL` | OpenAI model name | "gpt-4o-mini" |
| `GEMINI_MODEL` | Gemini model name | "gemini-2.0-flash" |

### Limits

- **Request size**: 16MB maximum
- **Image size**: 100KB maximum for base64 encoded images
- **URL fetch**: 200KB maximum per URL
- **Execution timeout**: 90 seconds per code execution

### Docker Deployment

```bash
# Build the image
docker build -t data-analyst-agent .

# Run the container
docker run -p 8000:8000 \
  -e GEMINI_API_KEY="your-key" \
  -e LLM_PROVIDER="gemini" \
  data-analyst-agent
```

## 📊 Supported Data Formats

- **CSV/TSV**: Tabular data with automatic column detection
- **Excel**: .xlsx and .xls files
- **JSON**: Structured data with key extraction
- **Parquet**: Columnar data format
- **Text**: Plain text files for analysis

## 🔒 Security

- **Sandboxed Execution**: Code runs in isolated environment
- **File Size Limits**: Prevents resource exhaustion
- **Timeout Protection**: Prevents infinite loops
- **Input Validation**: Sanitizes file uploads

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🐛 Troubleshooting

### Common Issues

1. **"questions.txt is required"**: Ensure your form field is named exactly `questions.txt`
2. **API Key errors**: Verify your environment variables are set correctly
3. **Import errors**: Check that all dependencies are installed
4. **Timeout errors**: Reduce data size or simplify analysis

### Debug Mode

Enable debug logging by setting:
```bash
$env:DEBUG="true"
```