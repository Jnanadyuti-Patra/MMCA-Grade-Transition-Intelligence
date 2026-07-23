# GitHub and Streamlit Deployment Guide

The recommended deployment uses:

- **GitHub** for version-controlled source code
- **Streamlit Community Cloud** to run the Python application

GitHub Pages is not used because it serves static files and cannot execute the
Excel-processing and analysis engine.

## Part 1: Prepare the repository

### 1. Extract the project

Extract the downloaded project ZIP. Open the folder and confirm that these files
are directly inside it:

```text
streamlit_app.py
requirements.txt
README.md
DEPLOYMENT_GUIDE.md
src/
config/
.streamlit/
```

Do not upload the project as an extra nested folder.

### 2. Create a GitHub repository

1. Sign in to GitHub.
2. Select **New repository**.
3. Recommended name:

```text
mmca-grade-transition-intelligence
```

4. Recommended description:

```text
Explainable grade-transition, root-cause and financial-impact analytics for continuous-cast copper rod production.
```

5. Choose **Private** when the deployed app will process actual company data.
6. Do not add a generated README, `.gitignore` or licence because these files
   are already included.
7. Create the repository.

### 3. Upload the project

Using the GitHub website:

1. Open the empty repository.
2. Select **Add file → Upload files**.
3. Drag all project files and folders into the upload area.
4. Use the commit message:

```text
Publish MMCA grade transition application
```

5. Select **Commit changes**.

Using Git:

```bash
git init
git add .
git commit -m "Publish MMCA grade transition application"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/mmca-grade-transition-intelligence.git
git push -u origin main
```

## Part 2: Deploy on Streamlit Community Cloud

Official deployment documentation:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

### 1. Create or open your Streamlit account

1. Open `https://share.streamlit.io`.
2. Sign in with GitHub.
3. Authorise Streamlit to access the repository.

Streamlit requires repository access so it can retrieve the app and redeploy
when GitHub changes are pushed.

### 2. Grant access to a private repository

For a private GitHub repository:

1. In Streamlit Community Cloud, open **Settings**.
2. Open **Linked accounts**.
3. Connect GitHub with private-repository access.
4. Approve access to the repository or organisation.

Official instructions:
https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account

### 3. Create the app

1. Select **Create app**.
2. Choose **Yup, I have an app**.
3. Select:
   - Repository: `YOUR-USERNAME/mmca-grade-transition-intelligence`
   - Branch: `main`
   - Main file path: `streamlit_app.py`
4. Open **Advanced settings**.
5. Select Python 3.12.
6. Choose a memorable app URL.
7. Select **Deploy**.

The dependency file is at the repository root. Streamlit Community Cloud reads
`requirements.txt` and installs the required packages automatically.

Official dependency guidance:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies

### 4. Make the app private

1. Open the deployed application.
2. Open **App settings**.
3. Open **Sharing**.
4. Select **Only specific people can view this app**.
5. Add authorised company viewers by email.

Official sharing documentation:
https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app

## Part 3: Test the deployment

1. Open the deployed URL.
2. Upload the product workbook.
3. Upload the process workbook.
4. Run a short date range first.
5. Confirm:
   - Coil count is reasonable
   - Transition sequence is chronological
   - Process records overlap the coil dates
   - Root-cause candidates are generated
   - Financial assumptions can be changed
   - HTML and Excel reports download correctly

## Part 4: Update the application

Any committed GitHub change is automatically reflected in the deployed
Streamlit app.

Website method:

1. Edit or upload the changed file on GitHub.
2. Add a descriptive commit message.
3. Commit the change.
4. Wait for the Streamlit application to redeploy.

Git method:

```bash
git add .
git commit -m "Improve root cause scoring"
git push
```

## Common deployment problems

### The app cannot find a dependency

Confirm that `requirements.txt` is at the repository root and includes every
imported third-party package.

### Excel loading is slow

The project uses the Calamine Excel engine when available and falls back to
OpenPyXL. Start with a short date range after loading.

### Market-price download fails

The application automatically falls back to the manually entered copper price
and USD/MYR exchange rate.

### Memory-limit error

Use a shorter date range, run the application locally, or deploy on an
organisation-managed server with higher memory limits.

### The app is public

Open Streamlit **App settings → Sharing** and change access to specific viewers.

## Local-only alternative

When cloud processing is not allowed:

1. Keep the repository on an authorised company computer.
2. Run `setup_windows.bat`.
3. Run `run_local.bat`.
4. Access the app only through `http://localhost:8501`.

This keeps the company files on the local computer.
