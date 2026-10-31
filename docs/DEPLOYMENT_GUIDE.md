# Complete DevOps Deployment Guide
## AI-Powered Food Freshness Detection & Shelf-Life Monitoring Platform

This guide provides end-to-end instructions for deploying the **AI-Powered Food Freshness Monitoring Platform** to production using industry best practices.

---

## 1. System Architecture Overview

```
                      +------------------------------------------+
                      |         User Web Browser                 |
                      +------------------------------------------+
                                     |           |
               Static Assets (HTML/CSS/JS)   API Calls (/api/*)
                                     |           |
                                     v           v
           +-----------------------------+   +-----------------------------+
           |       Vercel Edge CDN       |-->|   Production FastAPI Server |
           |  (Global Low-Latency Edge)  |   |  (Render / Railway / Docker)|
           +-----------------------------+   +-----------------------------+
                                                           |
                                              +------------+------------+
                                              |                         |
                                              v                         v
                                    +--------------------+   +--------------------+
                                    |   MongoDB Atlas    |   |  Persistent Volume |
                                    | (Cloud M0 Cluster) |   |  (/app/uploads)    |
                                    +--------------------+   +--------------------+
```

### Why Decouple Frontend & Backend?
1. **Frontend (Vercel)**:
   - Pure HTML5, CSS3, Chart.js, Vanilla JavaScript.
   - Ultra-fast global CDN delivery with zero-latency edge points.
   - Automatic SSL certificates, custom domains, and continuous Git deployment.

2. **Backend (Render / Railway / Docker)**:
   - FastAPI with Computer Vision (`opencv-python-headless`) and Machine Learning (`scikit-learn`, `numpy`).
   - Serverless functions (like Vercel Lambda) have a strict 250MB unzipped bundle limit, missing GLib dependencies, and cold starts. A containerized Docker service provides dedicated memory, persistent image uploads (`/uploads`), and unrestricted ML execution.

---

## 2. Step 1: Set Up Cloud MongoDB Atlas

1. Log in to [MongoDB Cloud](https://cloud.mongodb.com/).
2. Create a free **M0 Shared Cluster** (AWS or GCP region closest to your users).
3. Under **Security > Database Access**:
   - Create a database user (e.g. `freshness_admin`) with password.
4. Under **Security > Network Access**:
   - Add IP address `0.0.0.0/0` (Allow access from anywhere) so production containers can connect.
5. Under **Deployment > Database > Connect**:
   - Select **Drivers** (Python 3.11+).
   - Copy your connection string:
     ```
     mongodb+srv://freshness_admin:<password>@cluster0.xxxxx.mongodb.net/food_freshness_db?retryWrites=true&w=majority
     ```

---

## 3. Step 2: Deploy Backend to Render (1-Click or Blueprint)

### Option A: Using `render.yaml` (Recommended)
1. Fork or push this repository to GitHub: `https://github.com/santosh3105/Food-Freshness_Monitoring`
2. Go to [Render Dashboard](https://dashboard.render.com/) and click **New > Blueprint**.
3. Connect your repository. Render will automatically read `render.yaml`.
4. Fill in the required environment variable:
   - `MONGO_URI`: Your MongoDB Atlas connection URI.
5. Click **Apply**. Render will automatically build the Dockerfile and start the service with healthy `/health` status probes.

### Option B: Manual Web Service on Render
1. Click **New > Web Service**.
2. Connect your GitHub repository.
3. Choose **Docker** as Runtime (it uses the included `Dockerfile`).
4. Set Environment Variables:
   - `MONGO_URI`: `mongodb+srv://...`
   - `DATABASE_NAME`: `food_freshness_db`
   - `JWT_SECRET`: Generate a secure 64-character secret.
   - `JWT_ALGORITHM`: `HS256`
   - `ENVIRONMENT`: `production`
   - `DEBUG`: `false`
   - `CORS_ORIGINS`: `*`
   - `PORT`: `8000`
5. Click **Create Web Service**. Your backend URL will be:
   `https://food-freshness-backend.onrender.com`

---

## 4. Step 3: Deploy Frontend to Vercel

### Method 1: Using GitHub Integration (Easiest)
1. Go to [Vercel Dashboard](https://vercel.com/new).
2. Import the GitHub repository: `santosh3105/Food-Freshness_Monitoring`.
3. In Project Settings:
   - **Framework Preset**: Other
   - **Root Directory**: `Food Monitoring` (or `.`)
   - **Output Directory**: `frontend`
4. Update `vercel.json` rewrite target with your actual deployed Render URL:
   ```json
   {
     "rewrites": [
       {
         "source": "/api/:path*",
         "destination": "https://food-freshness-backend.onrender.com/api/:path*"
       },
       {
         "source": "/uploads/:path*",
         "destination": "https://food-freshness-backend.onrender.com/uploads/:path*"
       }
     ]
   }
   ```
5. Click **Deploy**. Vercel will produce your live production URL (e.g. `https://food-freshness-platform.vercel.app`).

### Method 2: Using Vercel CLI
```bash
# 1. Log in to Vercel
vercel login

# 2. Deploy to Production
cd "Food Monitoring"
vercel --prod
```

---

## 5. Step 4: Verification & Smoke Testing

After deployment, test every critical endpoint:

1. **System Health Probe**:
   `GET https://<your-backend-url>/health` -> `{"status":"healthy","database":"connected"}`

2. **System Readiness Probe**:
   `GET https://<your-backend-url>/ready` -> `{"status":"ready","models_loaded":true}`

3. **User Authentication**:
   Navigate to `https://<your-frontend-url>/login.html` and sign in with demo accounts:
   - **Consumer**: `consumer@foodfresh.com` / `ConsumerPass123!`
   - **Retailer**: `retailer@foodfresh.com` / `RetailerPass123!`
   - **Inspector**: `inspector@foodfresh.com` / `InspectorPass123!`
   - **Warehouse**: `warehouse@foodfresh.com` / `WarehousePass123!`
   - **Admin**: `admin@foodfresh.com` / `AdminPass123!`

4. **Interactive Features**:
   - Verify dynamic metrics display without "Calculating categories..." hanging.
   - Verify inventory table columns and responsive formatting.
   - Run AI Freshness Scanner with photo upload.
   - Test Arrhenius kinetic shelf life prediction.
