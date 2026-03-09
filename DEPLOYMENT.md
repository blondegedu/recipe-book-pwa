# Recipe Book - Cloud Deployment Guide

## Prerequisites
- GitHub repository (already set up)
- Cloud platform account (choose one below)

---

## Option 1: Railway (Recommended - $5/month)

### Why Railway?
- ✅ Easiest deployment
- ✅ Auto-deploys from GitHub
- ✅ Persistent storage included
- ✅ Custom domain support
- ✅ HTTPS automatic

### Steps:
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your `recipe-book` repository
5. Railway auto-detects Dockerfile and deploys
6. Click "Generate Domain" for public URL
7. Done! Your app is live

### Cost: $5/month (includes 500 hours + storage)

---

## Option 2: Render (Free Tier)

### Why Render?
- ✅ Free tier available
- ✅ Auto-deploys from GitHub
- ✅ HTTPS automatic
- ⚠️ Sleeps after 15 min inactivity (free tier)
- ⚠️ Slower cold starts

### Steps:
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Click "New" → "Web Service"
4. Connect your `recipe-book` repository
5. Render detects `render.yaml` automatically
6. Click "Create Web Service"
7. Wait for deployment (~5 minutes)
8. Your app URL appears at top

### Cost: Free (or $7/month for always-on)

---

## Option 3: DigitalOcean App Platform ($5/month)

### Why DigitalOcean?
- ✅ Fast and reliable
- ✅ Auto-deploys from GitHub
- ✅ Good documentation
- ⚠️ Slightly more complex setup

### Steps:
1. Go to [digitalocean.com](https://digitalocean.com)
2. Create account (get $200 credit with referral)
3. Go to "Apps" → "Create App"
4. Connect GitHub → Select repository
5. Choose "Dockerfile" as build method
6. Set environment variables:
   - `PORT`: 8080
   - `HOST`: 0.0.0.0
7. Click "Create Resources"
8. Wait for deployment

### Cost: $5/month

---

## Option 4: Fly.io (Free Tier)

### Why Fly.io?
- ✅ Generous free tier (3 VMs)
- ✅ Fast global deployment
- ✅ Good for Docker apps
- ⚠️ Command-line deployment

### Steps:
1. Install flyctl: `curl -L https://fly.io/install.sh | sh`
2. Sign up: `flyctl auth signup`
3. In your project directory:
   ```bash
   cd ~/RecipeBook-Dev
   flyctl launch
   ```
4. Follow prompts (choose region, name)
5. Deploy: `flyctl deploy`
6. Open: `flyctl open`

### Cost: Free (3 shared VMs, 3GB storage)

---

## Option 5: Docker + VPS (Advanced)

### For any VPS (Linode, Vultr, AWS EC2, etc.):

1. **SSH into your server:**
   ```bash
   ssh user@your-server-ip
   ```

2. **Install Docker:**
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

3. **Clone repository:**
   ```bash
   git clone https://github.com/yourusername/recipe-book.git
   cd recipe-book
   ```

4. **Build and run:**
   ```bash
   docker build -t recipe-book .
   docker run -d -p 80:8080 \
     -v $(pwd)/user_recipes:/app/user_recipes \
     -v $(pwd)/users.json:/app/users.json \
     -v $(pwd)/sessions.json:/app/sessions.json \
     -v $(pwd)/shared_recipes.json:/app/shared_recipes.json \
     --restart unless-stopped \
     recipe-book
   ```

5. **Setup HTTPS with Caddy (optional):**
   ```bash
   sudo apt install caddy
   sudo nano /etc/caddy/Caddyfile
   ```
   Add:
   ```
   yourdomain.com {
     reverse_proxy localhost:8080
   }
   ```
   ```bash
   sudo systemctl restart caddy
   ```

### Cost: $5-10/month (VPS)

---

## Post-Deployment Checklist

### 1. Update Ko-fi Link
Edit `recipe_server_multiuser.py` line ~871:
```python
<a href="https://ko-fi.com/YOURNAME" target="_blank" ...>
```

### 2. Test All Features
- [ ] Sign up new account
- [ ] Add recipe from URL
- [ ] Add manual recipe
- [ ] Edit recipe
- [ ] Theme customization
- [ ] Share recipe (test public link)
- [ ] PDF export
- [ ] PWA install (mobile)
- [ ] Offline mode

### 3. Setup Custom Domain (Optional)
Most platforms support custom domains:
- Buy domain from Namecheap/Cloudflare ($10-15/year)
- Add CNAME record pointing to your app URL
- Configure in platform settings

### 4. Backup Strategy
**Important:** JSON files store all data!

**Option A: Git backups (simple)**
```bash
# Add to crontab (daily backup)
0 2 * * * cd ~/RecipeBook-Dev && git add users.json sessions.json user_recipes/ shared_recipes.json && git commit -m "Auto backup" && git push
```

**Option B: Cloud storage**
- Use platform's backup feature
- Or sync to S3/Backblaze B2

---

## Monitoring & Maintenance

### Check Logs
- **Railway:** Click "Deployments" → View logs
- **Render:** Click "Logs" tab
- **Fly.io:** `flyctl logs`

### Update App
1. Push changes to GitHub
2. Platform auto-deploys (Railway/Render)
3. Or manually: `flyctl deploy` (Fly.io)

### Scale Up (if needed)
- Railway: Upgrade plan for more resources
- Render: Switch to paid tier ($7/month)
- Fly.io: Add more VMs in dashboard

---

## Recommended Choice

**For beginners:** Render (free tier) or Railway ($5/month)
**For developers:** Fly.io (free, CLI-based)
**For full control:** VPS with Docker

**My recommendation:** Start with **Render free tier** to test, then upgrade to **Railway** ($5/month) for production use.

---

## Need Help?

- Railway docs: https://docs.railway.app
- Render docs: https://render.com/docs
- Fly.io docs: https://fly.io/docs
- Docker docs: https://docs.docker.com

---

## Security Notes

1. **HTTPS:** All platforms provide free SSL
2. **Passwords:** Already hashed with SHA256
3. **Sessions:** 90-day expiry, HttpOnly cookies
4. **Data:** JSON files - consider PostgreSQL for production scale

---

**Your app is ready to deploy! Choose a platform and follow the steps above.**
