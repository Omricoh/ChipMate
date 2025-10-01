# ChipMate Railway.com Deployment Guide

This guide will help you deploy ChipMate to Railway.com with the web interface.

## Prerequisites

1. **GitHub Account** - Your ChipMate code should be in a GitHub repository
2. **Railway.com Account** - Sign up at [railway.app](https://railway.app)
3. **MongoDB Database** - Either MongoDB Atlas or Railway MongoDB addon

## Step-by-Step Deployment

### 1. Prepare Your Repository

Make sure your GitHub repository has all the ChipMate files including the new web interface.

### 2. Set Up MongoDB Database

**Option A: MongoDB Atlas (Recommended)**
1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create a free cluster
3. Create a database user
4. Get your connection string (e.g., `mongodb+srv://username:password@cluster.mongodb.net/chipmate`)

**Option B: Railway MongoDB Addon**
1. In Railway, create a new project
2. Add the MongoDB addon
3. Note the connection string provided

### 3. Deploy to Railway

1. **Connect GitHub Repository**:
   - Go to [railway.app](https://railway.app)
   - Click "Start a New Project"
   - Select "Deploy from GitHub repo"
   - Choose your ChipMate repository

2. **Configure Environment Variables**:
   Click on your service → Variables tab → Add these variables:

   ```
   MONGO_URL=mongodb+srv://your-connection-string
   PORT=5000
   TELEGRAM_BOT_TOKEN=your-bot-token (if keeping Telegram bot)
   TELEGRAM_BOT_USERNAME=your-bot-username (if keeping Telegram bot)
   ```

3. **Deploy**:
   - Railway will automatically detect the `nixpacks.toml` configuration
   - It will build both the Python backend and Angular frontend
   - The deployment process will take 5-10 minutes

### 4. Access Your Application

Once deployed, Railway will provide you with a URL like:
```
https://your-project-name.up.railway.app
```

The web interface will be available at the root URL, and the API will be at `/api/`.

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `MONGO_URL` | ✅ | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/chipmate` |
| `PORT` | ❌ | Server port (Railway sets this) | `5000` |
| `TELEGRAM_BOT_TOKEN` | ❌ | Telegram bot token (if keeping bot) | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `TELEGRAM_BOT_USERNAME` | ❌ | Telegram bot username | `YourBotName_bot` |
| `RAILWAY_ENVIRONMENT_NAME` | ❌ | Auto-set by Railway | `production` |

## Build Process

The deployment includes these automatic steps:

1. **Setup Phase**: Installs Node.js 18 and Python 3.10
2. **Install Phase**:
   - Installs Python dependencies from `requirements.txt`
   - Installs Node.js dependencies with `npm ci`
3. **Build Phase**: Builds Angular app with `npm run build`
4. **Start Phase**: Runs the production server

## File Structure After Deployment

```
/
├── src/api/production_server.py (Main server)
├── web-ui/dist/chipmate-web/ (Built Angular app)
├── requirements.txt (Python dependencies)
├── nixpacks.toml (Build configuration)
└── railway.json (Railway configuration)
```

## Troubleshooting

### Common Issues

1. **Build Fails During npm install**:
   - Check that `web-ui/package.json` exists
   - Verify Node.js version in `nixpacks.toml`

2. **MongoDB Connection Issues**:
   - Verify `MONGO_URL` environment variable
   - Check MongoDB Atlas network access (allow all IPs for testing)
   - Ensure database user has read/write permissions

3. **404 Errors for Web Interface**:
   - Check that Angular build completed successfully
   - Verify `web-ui/dist/chipmate-web/` contains built files
   - Check Railway logs for build errors

4. **API Not Working**:
   - Verify Flask dependencies are installed
   - Check that `src/api/production_server.py` exists
   - Review Railway logs for Python errors

### Checking Logs

1. Go to your Railway project dashboard
2. Click on your service
3. Go to "Deployments" tab
4. Click on the latest deployment
5. Check both "Build Logs" and "Deploy Logs"

### Testing the Deployment

1. **Health Check**: Visit `https://your-app.railway.app/api/health`
   - Should return JSON with status "healthy"

2. **Web Interface**: Visit `https://your-app.railway.app/`
   - Should load the ChipMate web interface

3. **API Endpoints**: Test API at `https://your-app.railway.app/api/`
   - All original API endpoints should work

## Production Configuration

The production server automatically:
- Serves the Angular app at the root URL
- Provides API endpoints at `/api/*`
- Handles Angular routing (SPA routing)
- Sets appropriate CORS headers
- Provides health check endpoint

## Custom Domain (Optional)

To use a custom domain:

1. In Railway project → Settings → Domains
2. Add your custom domain
3. Configure DNS records as shown
4. Update `appUrl` in environment if needed

## Monitoring and Maintenance

- **Logs**: Monitor Railway logs for errors
- **Metrics**: Use Railway's built-in metrics dashboard
- **Updates**: Push to GitHub to trigger automatic redeployment
- **Database**: Monitor MongoDB usage and performance

## Support

If you encounter issues:

1. Check Railway logs first
2. Verify all environment variables are set
3. Test API endpoints individually
4. Check MongoDB connectivity
5. Review this deployment guide

The deployment should work out-of-the-box with these configurations!