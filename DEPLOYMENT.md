# Streamlit Cloud Deployment Guide

This guide explains how to deploy "The Draft Desk" to Streamlit Cloud.

## Prerequisites

- A Streamlit Cloud account (free tier works)
- Google Cloud project with Gmail API enabled
- Gemini API key

## Step 1: Configure Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Gmail API and Calendar API
4. Create OAuth 2.0 credentials:
   - Go to APIs & Services > Credentials
   - Create OAuth client ID (Desktop application type)
   - Download the JSON file

## Step 2: Set Up Streamlit Secrets

For production deployment on Streamlit Cloud, you need to configure secrets:

1. Go to your Streamlit Cloud app dashboard
2. Click "Manage app" > "Secrets"
3. Add the following secrets:

### Required Secrets
```toml
# Gemini API Key (required for AI triage and drafting)
GEMINI_API_KEY = "your_actual_gemini_api_key_here"
```

### Optional: OAuth Token Method (Easier for development)
```toml
# Pre-authorized OAuth tokens
OAUTH_ACCESS_TOKEN = "your_access_token"
OAUTH_REFRESH_TOKEN = "your_refresh_token" 
OAUTH_CLIENT_ID = "your_client_id"
OAUTH_CLIENT_SECRET = "your_client_secret"
```

### Recommended: Service Account Method (Better for production)
```toml
# Service account credentials (JSON string)
GOOGLE_CREDENTIALS_JSON = '{"type": "service_account", "project_id": "...", ...}'
```

### Optional: Tone Profile and Past Replies
```toml
# Tone profile (JSON string)
tone_profile = '{"name": "Your Name", "role": "Your Role", ...}'

# Past replies (JSON array string)
past_replies = '[{"subject": "Example", "body": "..."}, ...]'
```

## Step 3: Deploy to Streamlit Cloud

1. Push your code to a GitHub repository
2. Make sure `.streamlit/config.toml` is committed
3. Make sure `.env` and credential files are in `.gitignore`
4. In Streamlit Cloud, click "New app"
5. Connect your GitHub repository
6. Select the repository and branch
7. Set main file path to `app.py`
8. Click "Deploy"

## Step 4: Post-Deployment Configuration

After deployment:

1. **Test with sample threads first**: Use "Sample threads for demo" in the sidebar to verify the pipeline works without Gmail integration
2. **Configure Gmail integration**: Once sample threads work, switch to "Gmail (via engine.py)" and configure your OAuth credentials in Streamlit secrets
3. **Test full pipeline**: Run the full pipeline to verify fetch, triage, and draft generation work end-to-end

## Troubleshooting

### "No API key found" Error
- Ensure `GEMINI_API_KEY` is set in Streamlit secrets
- Check the secret name matches exactly (case-sensitive)

### OAuth Authentication Fails
- For local development: Ensure `~/.gmail-mcp/gcp-oauth.keys.json` exists
- For cloud: Use service account credentials or pre-authorized tokens in secrets
- Browser-based OAuth won't work on Streamlit Cloud

### File Not Found Errors
- The app now uses Streamlit session state for cloud deployment
- Local files like `action_log.json` are only used as fallback
- Configure tone profile and past replies in Streamlit secrets for cloud deployment

### Rate Limiting Errors
- Gemini API free tier has rate limits (15 requests/minute)
- The app includes automatic retry logic with exponential backoff
- Consider upgrading to paid tier for production use

## Security Notes

- Never commit `.env` files or credential JSON files to Git
- Use Streamlit secrets for all sensitive configuration
- Service account credentials are more secure than OAuth tokens for production
- Regularly rotate API keys and credentials

## Local Development

For local development, you can still use the `.env` file approach:

1. Copy `.streamlit/secrets.toml.example` to `.env`
2. Fill in your actual API keys and credentials
3. The app will automatically use `.env` when not running on Streamlit Cloud
