from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN not set in environment variables.")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "User-Agent": "GitHub-Repo-Analyzer",
    "Accept": "application/vnd.github+json"
}

GITHUB_API = "https://api.github.com/repos"

app = FastAPI(title="GitHub Repository Intelligence Analyzer")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class RepoRequest(BaseModel):
    repo_url: str

def parse_repo(url: str):
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return None, None
    return parts[-2], parts[-1]

def github_get(url):
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise HTTPException(status_code=429, detail="GitHub API rate limit exceeded")
    return r

def get_commit_count(owner, repo):
    url = f"{GITHUB_API}/{owner}/{repo}/commits?per_page=1"
    r = github_get(url)
    if r.status_code != 200:
        return 0
    if 'Link' in r.headers:
        links = r.headers['Link'].split(',')
        for link in links:
            if 'rel="last"' in link:
                last_url = link.split(';')[0].strip()[1:-1]
                return int(last_url.split('page=')[-1])
    return len(r.json())

def get_repo_files(owner, repo):
    """List root-level files/folders for analysis"""
    r = github_get(f"{GITHUB_API}/{owner}/{repo}/contents")
    if r.status_code != 200:
        return []
    return [c['name'].lower() for c in r.json()]

def analyze_repo(owner, repo):
    repo_api = f"{GITHUB_API}/{owner}/{repo}"
    r = github_get(repo_api)
    if r.status_code != 200:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo_data = r.json()

    readme = github_get(f"{repo_api}/readme")
    has_readme = readme.status_code == 200

    commit_count = get_commit_count(owner, repo)

    langs = github_get(f"{repo_api}/languages")
    languages = list(langs.json().keys()) if langs.status_code == 200 else []

    files = get_repo_files(owner, repo)

    return {
        "stars": repo_data.get("stargazers_count", 0),
        "has_readme": has_readme,
        "commit_count": commit_count,
        "languages": languages,
        "files": files
    }

def score_repo(data):
    score = 0
    if data["has_readme"]:
        score += 20
    if data["commit_count"] >= 10:
        score += 20
    if data["languages"]:
        score += 20
    if data["commit_count"] >= 30:
        score += 10
    if data["stars"] > 0:
        score += 10
    score = min(score, 100)

    if score < 40:
        level = "Beginner"
    elif score < 70:
        level = "Intermediate"
    else:
        level = "Advanced"
    return score, level

def generate_summary(data, level):
    return (
        f"This repository is rated as {level}. "
        + ("Documentation is present. " if data["has_readme"] else "Documentation is missing. ")
        + ("Commits show reasonable development activity." if data["commit_count"] >= 10 else "Commit history is limited.")
    )

def generate_dynamic_roadmap(data):
    roadmap = []

    # README
    if not data["has_readme"]:
        roadmap.append("Add a detailed README with setup and usage instructions.")

    # Commits
    if data["commit_count"] < 10:
        roadmap.append("Increase commit frequency with meaningful messages.")

    # Tests folder
    if "tests" not in data["files"]:
        roadmap.append("Add unit tests to improve code reliability.")

    # CI/CD
    if ".github" not in data["files"]:
        roadmap.append("Set up GitHub Actions for CI/CD.")

    # Documentation folder
    if "docs" not in data["files"]:
        roadmap.append("Add project documentation or a docs folder.")

    # Stars & popularity
    if data["stars"] < 5:
        roadmap.append("Promote repository to gain attention and community feedback.")

    # Languages
    if len(data["languages"]) == 0:
        roadmap.append("Include code in a primary programming language.")

    return roadmap

@app.post("/analyze")
def analyze(request: RepoRequest):
    owner, repo = parse_repo(request.repo_url)
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    data = analyze_repo(owner, repo)
    score, level = score_repo(data)

    return {
        "score": score,
        "level": level,
        "summary": generate_summary(data, level),
        "roadmap": generate_dynamic_roadmap(data),
        "languages": data["languages"],
        "commit_count": data["commit_count"]
    }

@app.get("/", response_class=HTMLResponse)
def get_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()