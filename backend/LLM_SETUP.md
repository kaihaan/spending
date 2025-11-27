# LLM Enrichment Setup Guide

This guide explains how to configure and use the AI-powered LLM enrichment system for transaction categorization and enrichment.

## Quick Start (3 steps)

### 1. Choose an LLM Provider

Pick one of these options based on your needs:

| Provider | Cost | Speed | Quality | Best For |
|----------|------|-------|---------|----------|
| **Ollama (Local)** | Free | Variable | Good | Privacy-focused, offline, no API keys |
| **Deepseek** | $0.14-0.28/1M | Fast | Good | Budget-conscious, high volume |
| **Google Gemini** | $0.075-10.50/1M | Very Fast | Good | Fast responses, free tier |
| **Anthropic Claude** | $0.80-75/1M | Moderate | Excellent | Complex categorization |
| **OpenAI GPT** | $0.50-30/1M | Moderate | Excellent | Well-tested, mature API |

**Recommendation for beginners:**
- **Privacy-first:** Use Ollama (free, runs locally, no API keys needed)
- **Budget:** Use Deepseek (cheapest cloud option) or Google Gemini Flash (free tier available)
- **Quality:** Use Anthropic Claude (best results)

### 2. Get an API Key

Choose your provider and get an API key:

#### Anthropic Claude
1. Go to https://console.anthropic.com/
2. Create an account or log in
3. Navigate to **API Keys** section
4. Click **Create Key**
5. Copy the API key

#### OpenAI GPT
1. Go to https://platform.openai.com/api-keys
2. Create an account or log in
3. Click **Create new secret key**
4. Copy the API key

#### Google Gemini
1. Go to https://aistudio.google.com/app/apikey
2. Create an account or log in with Google
3. Click **Create API Key**
4. Copy the API key (free tier: 60 requests/minute)

#### Deepseek
1. Go to https://platform.deepseek.com/
2. Create an account or log in
3. Navigate to **API Keys**
4. Click **Create new key**
5. Copy the API key

#### Ollama (Local - No API Key Needed!)
1. Download Ollama from https://ollama.ai/
2. Install for your OS (Windows, macOS, Linux)
3. Open a terminal and pull a model:
   ```bash
   ollama pull mistral:7b    # Recommended: Fast and capable
   # or
   ollama pull llama2:7b     # Alternative: Solid general-purpose model
   ```
4. Ollama runs on `http://localhost:11434` by default
5. Use any dummy value (like "local") for `LLM_API_KEY`

**Ollama Model Options:**
- `mistral:7b` - Recommended, fast and capable (recommended)
- `llama2:7b` - Solid general-purpose model
- `llama2:13b` - More powerful, slower
- `neural-chat:7b` - Optimized for chat/classification
- Any other Ollama-supported model

### 3. Configure the Backend

Edit `/backend/.env`:

```bash
# Uncomment ONE provider section and add your API key

# Option A: Ollama (local, free, no API key needed)
# LLM_PROVIDER=ollama
# LLM_API_KEY=local              # Can be any dummy value
# LLM_MODEL=mistral:7b           # Or llama2:7b, neural-chat:7b, etc.
# LLM_BATCH_SIZE=5               # Adjust based on your hardware

# Option B: Anthropic (recommended for quality)
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-actual-key-here

# Option C: OpenAI
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-proj-your-actual-key-here

# Option D: Google Gemini (recommended for cost)
# LLM_PROVIDER=google
# LLM_API_KEY=your-actual-key-here

# Option E: Deepseek (most affordable cloud option)
# LLM_PROVIDER=deepseek
# LLM_API_KEY=your-actual-key-here
```

### 4. Restart the Backend

```bash
source venv/bin/activate
cd backend
python app.py
```

The backend will automatically load the `.env` file and initialize the LLM system.

## Using LLM Enrichment

### Via Settings Page

1. Go to **Settings** → **LLM Enrichment**
2. Click **🔍 Validate Configuration** to test your API key
3. Select transaction direction (Expenses or Income)
4. Click **✨ Enrich All Transactions**
5. Wait for completion - see results and cost

### Via File Import

1. When importing a bank statement file, check **"Auto-enrich with LLM during import"**
2. Click **Import**
3. Transactions will be automatically categorized during import
4. See enrichment results in the success message

### Manual Batch Enrichment

Send a POST request to the API:

```bash
curl -X POST http://localhost:5000/api/enrichment/enrich \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_ids": null,  # null = all transactions
    "direction": "out",       # "out" for expenses, "in" for income
    "force_refresh": false    # true to bypass cache
  }'
```

## Monitoring & Management

### Check Configuration

```bash
curl http://localhost:5000/api/enrichment/config
```

### View Cache Statistics

```bash
curl http://localhost:5000/api/enrichment/cache/stats
```

### Get Failed Enrichments

```bash
curl http://localhost:5000/api/enrichment/failed?limit=50
```

### Retry Failed Enrichments

```bash
curl -X POST http://localhost:5000/api/enrichment/retry-failed \
  -H "Content-Type: application/json" \
  -d '{"direction": "out", "limit": 50}'
```

## Advanced Configuration

Edit `.env` to customize:

```bash
# Timeout for API requests (seconds)
LLM_TIMEOUT=30

# Batch size (gets optimized per provider)
LLM_BATCH_SIZE_INITIAL=10

# Enable result caching (saves money)
LLM_CACHE_ENABLED=true

# Enable debug logging
LLM_DEBUG=false

# Custom API base URL (for proxies)
# LLM_API_BASE_URL=https://api.proxy.com
```

### Custom Models

Override the default model:

```bash
# Ollama options (requires Ollama running)
LLM_MODEL=mistral:7b        # Recommended: Fast, capable
LLM_MODEL=llama2:7b         # Good general model
LLM_MODEL=llama2:13b        # More powerful, slower
LLM_MODEL=neural-chat:7b    # Optimized for chat

# Anthropic options
LLM_MODEL=claude-3-5-opus-20241022    # Most capable
LLM_MODEL=claude-3-5-sonnet-20241022  # Balanced (default)
LLM_MODEL=claude-3-5-haiku-20241022   # Fastest/cheapest

# OpenAI options
LLM_MODEL=gpt-4-turbo      # Most capable
LLM_MODEL=gpt-4o           # Balanced (default)
LLM_MODEL=gpt-3.5-turbo    # Cheapest

# Google options
LLM_MODEL=gemini-1.5-pro   # Most capable
LLM_MODEL=gemini-1.5-flash # Fast/cheap (default)
LLM_MODEL=gemini-pro       # Legacy

# Deepseek options
LLM_MODEL=deepseek-chat    # Standard (default)
```

## What Gets Enriched

The LLM analyzes transaction descriptions and extracts:

- **Primary Category** - Main spending category (Groceries, Transport, etc.)
- **Subcategory** - Specific type (e.g., Fast Food under Groceries)
- **Merchant Name** - Clean, normalized merchant name
- **Merchant Type** - Category of business (Retailer, Service, Subscription, etc.)
- **Essential/Discretionary** - Flag for budget analysis
- **Payment Method** - How it was paid (Card, Online Transfer, Direct Debit, etc.)
- **Payment Subtype** - Specific payment method details
- **Payee** - Who/what received the payment
- **Purchase Date** - When the transaction occurred (if detectable)

## Cost Estimates

For reference, here are approximate costs per 1,000 transactions:

| Provider | Cost | Notes |
|----------|------|-------|
| **Ollama (Local)** | **$0** | Free! Runs on your hardware, fully private |
| Deepseek | $0.05-0.10 | Cheapest cloud option |
| Google Gemini Flash | $0.10-0.30 | Free tier available (60 req/min) |
| Google Gemini Pro | $1.50-3.50 | More capable than Flash |
| OpenAI GPT-3.5 | $0.50-1.50 | Budget-friendly GPT |
| OpenAI GPT-4o | $5-15 | Balanced capability/cost |
| Anthropic Haiku | $0.80-4.00 | Claude family, most affordable |
| Anthropic Sonnet | $3-15 | Claude family, balanced |
| Anthropic Opus | $15-75 | Claude family, most capable |

*Actual costs vary based on transaction complexity and description length.*

### Ollama Hardware Requirements

- **Mistral 7B** (recommended): ~4GB RAM, ~15GB disk space
- **Llama 2 7B**: ~4GB RAM, ~15GB disk space
- **Llama 2 13B**: ~8GB RAM, ~25GB disk space
- GPU support available (CUDA/Metal) for faster inference

**First run download time**: 5-15 minutes depending on internet speed

## Troubleshooting

### "LLM enrichment not configured"
- Ensure `.env` file exists in `/backend/`
- Check `LLM_PROVIDER` and `LLM_API_KEY` are set
- Restart the backend after changing `.env`

### "Invalid API key"
- Verify your API key is correct
- Check for extra spaces in `.env`
- Test key on provider's website
- Regenerate key if needed

### "API rate limit exceeded"
- Wait a few minutes before retrying
- Consider reducing batch size in `.env`
- For high volume, use cheaper provider (Deepseek)

### "No results returned from LLM"
- Check transaction descriptions aren't empty
- Increase `LLM_TIMEOUT` in `.env`
- Enable `LLM_DEBUG=true` to see API responses
- Check provider API status

### "High costs"
- Switch to cheaper provider (Deepseek, Google Flash, or Ollama for free)
- Use cheaper models (Haiku, GPT-3.5, Flash)
- Enable caching to avoid re-processing
- Reduce batch sizes for better cache hits

### Ollama-Specific Issues

#### "Ollama connection failed" or "Ollama model not found"
1. Ensure Ollama is running: Open a terminal and run `ollama serve`
2. Check Ollama is accessible at `http://localhost:11434`
3. Verify the model is pulled: `ollama list`
4. If model missing, pull it: `ollama pull mistral:7b`
5. Restart the backend after pulling

#### "Slow inference / high response times"
- Reduce batch size with `LLM_BATCH_SIZE=1` or `LLM_BATCH_SIZE=2`
- Use faster model: `mistral:7b` or `neural-chat:7b`
- Enable GPU acceleration if available:
  - NVIDIA: Install CUDA
  - Apple: Metal support is automatic
  - Linux: Install CUDA toolkit

#### "Out of memory errors"
- Use smaller model: `mistral:7b` (4GB) instead of `llama2:13b` (8GB)
- Reduce batch size further
- Close other applications

#### "Model keeps getting unloaded"
- Ollama auto-unloads unused models to save memory
- This is normal - models reload on next use
- If you want to keep model loaded, see Ollama docs

## Security Notes

⚠️ **Never share your `.env` file or API keys!**

- `.env` is in `.gitignore` - won't be committed to git
- Don't paste API keys in public channels
- Rotate keys periodically in provider dashboards
- Use minimal permission keys if provider allows

### Ollama Privacy
- **No data leaves your machine** - All processing happens locally
- **No API calls** - No transaction data sent to external services
- **Fully offline** - Works without internet connection
- **Private by default** - Perfect for sensitive financial data

## Disabling LLM Enrichment

To disable LLM enrichment:

1. Delete or comment out `LLM_PROVIDER` in `.env`
2. Restart the backend
3. The system will work without LLM enrichment

Transaction categorization will fall back to rule-based system.

## Support

If you encounter issues:

1. Check `.env` is in `/backend/` directory
2. Enable `LLM_DEBUG=true` and check logs
3. Test API key directly on provider's website
4. Check provider API status/documentation
5. Review error messages in browser console

## Further Reading

- [Ollama Documentation](https://github.com/ollama/ollama) - Local LLM running
- [Anthropic API Docs](https://docs.anthropic.com/)
- [OpenAI API Docs](https://platform.openai.com/docs/)
- [Google Generative AI Docs](https://ai.google.dev/docs)
- [Deepseek API Docs](https://platform.deepseek.com/docs)
