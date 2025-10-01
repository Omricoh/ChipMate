# 🚀 Railway.com Deployment - Quick Setup Guide

## ✅ Ready to Deploy!

Your ChipMate application is now fully configured for Railway.com deployment. Here's everything you need to know:

## 📋 Pre-Deployment Checklist

Before deploying, make sure you have:
- [x] GitHub repository with all ChipMate files
- [x] Railway.com account
- [x] MongoDB database (Atlas or Railway addon)
- [x] All deployment files created

## 🚀 3-Step Deployment Process

### Step 1: Set Up MongoDB

**Option A: MongoDB Atlas (Recommended)**
```
1. Go to https://www.mongodb.com/cloud/atlas
2. Create a free cluster
3. Create database user with read/write access
4. Get connection string like: mongodb+srv://user:pass@cluster.mongodb.net/chipmate
```

**Option B: Railway MongoDB**
```
1. Create new Railway project
2. Add MongoDB addon
3. Copy provided connection string
```

### Step 2: Deploy to Railway

```
1. Go to https://railway.app
2. Click "Start a New Project"
3. Select "Deploy from GitHub repo"
4. Choose your ChipMate repository
5. Wait for automatic deployment (5-10 minutes)
```

### Step 3: Configure Environment Variables

In Railway dashboard → Your Project → Variables:

**Required Variables:**
```
MONGO_URL=mongodb+srv://your-connection-string-here
```

**Optional Variables:**
```
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_BOT_USERNAME=your-bot-username
```

## 🔧 What Happens During Deployment

Railway will automatically:
1. **Install Dependencies**: Python packages and Node.js modules
2. **Build Angular App**: Creates production-ready web interface
3. **Start Server**: Runs Flask server serving both API and web app
4. **Assign URL**: Provides public URL like `https://your-project.up.railway.app`

## 📁 Files Created for Deployment

| File | Purpose |
|------|---------|
| `nixpacks.toml` | Tells Railway how to build and run your app |
| `railway.json` | Railway-specific configuration |
| `src/api/production_server.py` | Production server (API + Web UI) |
| `requirements.txt` | Updated with web dependencies |
| `DEPLOYMENT.md` | Comprehensive deployment guide |

## 🌐 After Deployment

Your app will be available at:
- **Web Interface**: `https://your-project.railway.app/`
- **API Health Check**: `https://your-project.railway.app/api/health`
- **API Endpoints**: `https://your-project.railway.app/api/*`

## 🎮 How Users Will Access

1. **Players**: Visit your Railway URL directly in browser
2. **Join Games**: Use QR codes or game codes
3. **All Features**: Complete poker game management via web interface

## 🛠️ Troubleshooting

**If deployment fails:**
1. Check Railway build logs
2. Verify `MONGO_URL` environment variable is set
3. Ensure GitHub repo has all files
4. Check `nixpacks.toml` configuration

**If web interface doesn't load:**
1. Check that Angular build completed successfully
2. Visit `/api/health` to verify API is working
3. Review Railway deployment logs

**If MongoDB connection fails:**
1. Verify connection string format
2. Check MongoDB Atlas network access (allow all IPs)
3. Ensure database user has proper permissions

## 📊 Expected Build Output

Railway logs should show:
```
=====> Installing Node.js dependencies
=====> Building Angular application
=====> Installing Python dependencies
=====> Starting production server
=====> Deploy successful
```

## 🎯 Success Indicators

✅ **Deployment Successful** when you see:
- Railway shows "Deployed" status
- Health check at `/api/health` returns JSON
- Web interface loads at root URL
- Players can create and join games

## 📞 Support

If you need help:
1. Check the comprehensive `DEPLOYMENT.md` guide
2. Review Railway logs for specific errors
3. Verify all environment variables are set correctly
4. Test MongoDB connection separately

Your ChipMate application is now ready for production deployment on Railway.com! 🎉