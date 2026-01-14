# Testing Guide for Lexora

## Quick Start Testing

### Step 1: Environment Setup

```bash
# 1. Create .env file from example
cp .env.example .env

# 2. Edit .env and add your OpenAI API key (required for playbook/redlines)
# For now, you can test without it, but playbook/redline generation won't work
nano .env  # or use your favorite editor
```

**Important**: Add your OpenAI API key:
```
OPENAI_API_KEY=your-api-key-here
```

### Step 2: Start Services

```bash
# Start all services (PostgreSQL, Redis, Backend, Frontend)
make up

# Wait 30-60 seconds for services to start
# Check status:
make status

# View logs to see if everything is running:
make logs
```

You should see:
- ✅ postgres: running
- ✅ redis: running
- ✅ backend: running
- ✅ frontend: running

### Step 3: Run Database Migrations

```bash
# Create database tables
make migrate
```

You should see:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial, Initial migration
```

### Step 4: Test the Application

#### Option A: Test via Web UI (Recommended)

1. **Open the frontend**: http://localhost:3000

2. **Upload a PDF contract**:
   - Click "Upload" tab (should be default)
   - Select a PDF file (any contract PDF)
   - Click "Upload and Extract Text"
   - Wait for confirmation

3. **Analyze the document**:
   - Click "Analyze Document" button
   - Wait 10-30 seconds
   - Check the clause list on the right sidebar
   - You should see clauses with types, risk scores, and heatmap bars

4. **Generate Playbook** (requires OpenAI API key):
   - Click "Generate Playbook" button
   - Wait 30-60 seconds
   - Go to "Report" tab
   - View the negotiation playbook

5. **Generate Redlines** (requires OpenAI API key):
   - Go back to "Analyze" tab
   - Click "Generate Redlines" button
   - Wait 30-60 seconds
   - Go to "Report" tab
   - View redline suggestions

#### Option B: Test via API (curl/Postman)

1. **Check health**:
```bash
curl http://localhost:8000/health
```

2. **List documents**:
```bash
curl http://localhost:8000/api/documents
```

3. **Upload a PDF**:
```bash
curl -X POST -F "file=@/path/to/your/contract.pdf" http://localhost:8000/api/upload
```

Save the `document_id` from the response.

4. **Analyze document**:
```bash
curl -X POST http://localhost:8000/api/analyze/1
# Replace 1 with your document_id
```

5. **Get report**:
```bash
curl http://localhost:8000/api/report/1
# Replace 1 with your document_id
```

6. **Generate playbook** (requires API key):
```bash
curl -X POST http://localhost:8000/api/playbook/1
```

7. **Generate redlines** (requires API key):
```bash
curl -X POST http://localhost:8000/api/redlines/1
```

#### Option C: Test with Sample Data

```bash
# Seed sample data
make seed

# Then access document ID 1 via API or UI
```

### Step 5: View API Documentation

Visit http://localhost:8000/docs to see interactive API documentation (Swagger UI).

## Testing Without OpenAI API Key

You can test most features without an API key:

✅ **Works without API key**:
- PDF upload
- Text extraction
- Clause segmentation
- Clause classification (uses dummy classifier)
- Risk scoring (uses dummy classifier)
- Report viewing

❌ **Requires API key**:
- Playbook generation
- Redline generation

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker ps

# Check what's wrong
make logs

# Try restarting
make restart

# Or rebuild everything
make clean
make build
make up
```

### Database connection errors

```bash
# Wait for PostgreSQL to be ready (30 seconds after make up)
# Check if PostgreSQL is healthy
docker-compose ps

# If not, restart
docker-compose restart postgres

# Or reset database
make clean
make up
sleep 30
make migrate
```

### Backend errors

```bash
# Check backend logs
make logs-backend

# Common issues:
# - Missing OpenAI API key (only affects playbook/redlines)
# - Database not ready (wait longer)
# - Port conflicts (check if 8000 is already in use)
```

### Frontend not loading

```bash
# Check frontend logs
make logs-frontend

# Common issues:
# - Build errors (check node_modules)
# - Port 3000 already in use
# - API connection errors (check NEXT_PUBLIC_API_URL in .env)
```

### PDF upload fails

```bash
# Check file size (max 10MB by default)
# Check file type (must be PDF)
# Check backend logs:
make logs-backend
```

### Analysis fails

The dummy ONNX model should always work. If it fails:
```bash
# Check backend logs
make logs-backend

# Verify model path in .env
# Default: /app/models/clause_risknet.onnx
# Dummy classifier will be used if file doesn't exist
```

### Playbook/Redlines fail

This is expected if you don't have an OpenAI API key. To test:

1. Get an API key from https://platform.openai.com/api-keys
2. Add it to `.env`:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```
3. Restart backend:
   ```bash
   docker-compose restart backend
   ```

## Running Tests

### Backend tests

```bash
# Run all backend tests
docker-compose exec backend pytest

# Run specific test
docker-compose exec backend pytest tests/test_clause_segment.py

# Run with verbose output
docker-compose exec backend pytest -v
```

### Frontend tests

```bash
# Install dependencies first (if not already done)
cd frontend
npm install

# Run tests
npm test
```

## Expected Test Results

### Backend Tests
- ✅ `test_clause_segment.py` - Clause segmentation works
- ✅ `test_onnx_infer.py` - ONNX inference works (dummy mode)
- ✅ `test_schemas.py` - Pydantic schemas validate correctly

### Frontend Tests
- ✅ `UploadComponent.test.tsx` - Upload component renders

## Performance Testing

Expected response times:
- PDF upload: 1-3 seconds
- Text extraction: 1-5 seconds
- Clause analysis: 5-15 seconds (depends on document size)
- Playbook generation: 30-60 seconds (depends on LLM)
- Redline generation: 30-60 seconds (depends on LLM)

## Manual Testing Checklist

- [ ] Services start successfully (`make up`)
- [ ] Migrations run successfully (`make migrate`)
- [ ] Frontend loads at http://localhost:3000
- [ ] API docs load at http://localhost:8000/docs
- [ ] Can upload PDF via UI
- [ ] Can analyze document
- [ ] Clause list shows with types and risk scores
- [ ] Heatmap visualization works
- [ ] Can generate playbook (if API key set)
- [ ] Can generate redlines (if API key set)
- [ ] Report displays correctly
- [ ] All API endpoints respond correctly

## Sample Test Contract

If you don't have a contract PDF, you can:

1. Use any public contract PDF
2. Create a simple PDF with contract-like text
3. Use the seed data:
   ```bash
   make seed
   # Then test with document ID 1
   ```

## Next Steps After Testing

1. **Train the model** (optional, requires GPU):
   ```bash
   make train_model
   ```

2. **Customize configuration** in `.env`

3. **Add more tests** as needed

4. **Deploy to production** with proper security settings

## Getting Help

- Check logs: `make logs`
- Check API docs: http://localhost:8000/docs
- Review architecture: `docs/ARCHITECTURE.md`
- Review demo guide: `docs/DEMO.md`
