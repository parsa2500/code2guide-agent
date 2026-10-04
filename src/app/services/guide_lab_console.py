"""Local operations console: finite allowlisted actions, versioned settings and trace review."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock, Thread, Timer
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


from src.app.services.guide_lab_pipeline import GuidePipeline
from src.integrations.code_kb_client import CodeKbClient


class GuideLabConsole:
    def __init__(self, service, project_dir: Path, state_dir: Path):
        self.service, self.project_dir, self.state_dir = service, project_dir.resolve(), state_dir
        self.lock = RLock()
        self.current = None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline=GuidePipeline(state_dir/"pipeline")
        service.pipeline=self.pipeline
        # A crash must not leave a job permanently running in the UI.
        for path in (state_dir / "jobs").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "running":
                data.update(status="interrupted", finished_at=now())
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def knowledge(self):
        return self.service.client._request_json("GET", "/api/lab/knowledge")

    def edit_knowledge(self, method, path, body):
        with self.lock:
            if self.current:raise ValueError("job_running")
            return self.service.client._request_json(method,"/api/lab/knowledge/"+path,body)

    def start_answer(self, question):
        with self.lock:
            if self.current or self.pipeline.active():raise ValueError("pipeline_running")
            run_id=uuid.uuid4().hex
            self.pipeline.begin(run_id,question,self.service.revision,self.service.settings_store.get()["revision"])
            def answer():
                try:self.service.answer(question,run_id=run_id)
                except Exception as exc:
                    self.pipeline.event(run_id,"error",0,error_type=type(exc).__name__)
            Thread(target=answer,daemon=True).start()
            return {"id":run_id,"status":"running"}

    def health(self):
        result = {"chat": "running", "brain": "unknown", "database": "unknown", "workspace": self.service.workspace,
                  "revision": self.service.revision, "review_status": "pending-human",
                  "settings_revision": self.service.settings_store.get()["revision"], "provider_key_configured": bool(self.service.provider_key)}
        try:
            data = self.service.client._request_json("GET", "/api/lab/status")
            result.update(brain="running", database=data["database"], startup_events=data.get("events", []))
        except Exception as exc:
            result.update(brain="unavailable", error_type=type(exc).__name__)
        return result

    def traces(self, limit=200):
        root = self.service.trace_dir.parent
        items = []
        files = sorted(root.glob("contracts-guide-lab-*/*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                response = data.get("response", {})
                items.append({"id": path.stem, "workspace": path.parent.name, "question": data.get("question"),
                              "status": response.get("status"), "model": response.get("model"),
                              "usage": data.get("usage", {}), "duration_ms": data.get("duration_ms"),
                              "started_at": data.get("started_at"), "settings_revision": data.get("settings_revision"),
                              "revision": data.get("revision"), "error_type": data.get("error_type")})
            except (ValueError, OSError):
                continue
        return {"items": items, "limit": limit, "total_files": len(files)}

    def trace(self, workspace, trace_id):
        if not re.fullmatch(r"contracts-guide-lab-\d+", workspace) or not re.fullmatch(r"[a-f0-9]{32}", trace_id):
            raise ValueError("invalid_trace_id")
        path = self.service.trace_dir.parent / workspace / f"{trace_id}.json"
        if not path.exists():
            raise FileNotFoundError()
        return json.loads(path.read_text(encoding="utf-8"))

    def evaluations(self):
        result = []
        for path in sorted((self.project_dir / "phase1/evaluation").glob("*/run.json"), reverse=True):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                results_path = path.parent / "results.json"
                rows = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else []
            except (OSError, ValueError):
                continue
            result.append({"id": path.parent.name, "run": run, "results": rows})
        review_path = self.project_dir / "phase1/P1-05-agent-review.json"
        return {"runs": result, "agent_review": json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else None}

    def reviews(self):
        path = self.state_dir / "reviews.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save_review(self, target, reviewer, decision, note):
        if not re.fullmatch(r"[a-zA-Z0-9:_-]{1,160}", target):
            raise ValueError("invalid_review_target")
        with self.lock:
            records = self.reviews()
            records[target] = {"reviewer": reviewer, "decision": decision, "note": note, "reviewed_at": now(),
                               "scope": "Local operator review only; canonical evidence truth is unchanged"}
            temporary = self.state_dir / "reviews.tmp"
            temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.state_dir / "reviews.json")
            return records[target]

    def jobs(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.state_dir / "jobs").glob("*.json"), reverse=True)]

    def start_job(self, kind, version=None):
        if kind not in {"unit-tests", "evaluate-pilot", "evaluate-all", "resync", "publish-knowledge"}:
            raise ValueError("unsupported_job")
        with self.lock:
            if self.current is not None or self.pipeline.active():
                raise ValueError("job_running")
            settings = self.service.settings_store.get()
            if kind.startswith("evaluate") and settings["settings"]["provider"] != "gemini":
                raise ValueError("evaluation_requires_gemini")
            job = {"id": uuid.uuid4().hex, "kind": kind, "status": "running", "started_at": now(), "lines": [],
                   "settings_revision": settings["revision"], "workspace": self.service.workspace, "revision": self.service.revision, "knowledge_version": version}
            self.current = job["id"]
            self._save_job(job)
            Thread(target=self._run_job, args=(job,), daemon=True).start()
            return dict(job)

    def _save_job(self, job):
        directory = self.state_dir / "jobs"
        directory.mkdir(exist_ok=True)
        tmp = directory / f"{job['id']}.tmp"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(directory / f"{job['id']}.json")

    def _run_job(self, job):
        try:
            if job["kind"] in {"resync","publish-knowledge"}:
                client=self.service.client
                publisher=CodeKbClient(base_url=client.base_url,token=client.token,timeout_seconds=240) if isinstance(client,CodeKbClient) else client
                result = publisher._request_json("POST", "/api/lab/resync", {"version":job.get("knowledge_version")})
                self.service.revision = result["revision"]
                job.update(status="passed", result=result)
            else:
                repo = Path(__file__).resolve().parents[3]
                if job["kind"] == "unit-tests":
                    command = [sys.executable, "-X", "utf8", "scripts/test_guide_console.py"]
                else:
                    command = [sys.executable, "-X", "utf8", str(self.project_dir / "scripts/evaluate-phase1.py"),
                               "--project", str(self.project_dir), "--label", "console-" + job["id"][:8]]
                    if job["kind"] == "evaluate-pilot":
                        command.extend(["--ids", "Q05", "Q06", "Q12", "Q13", "Q19"])
                # Do not pass provider/DB/Brain credentials to the evaluation/test subprocess.
                environment = {k: v for k, v in os.environ.items() if not any(term in k.upper() for term in ["KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL"])}
                process = subprocess.Popen(command, cwd=repo, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace", shell=False)
                timer = Timer(240, process.kill)
                timer.start()
                try:
                    for line in process.stdout:
                        with self.lock:
                            job["lines"] = (job["lines"] + [line.rstrip()])[-100:]
                            self._save_job(job)
                    code = process.wait()
                    job.update(status="passed" if code == 0 else "failed", exit_code=code)
                finally:
                    timer.cancel()
        except Exception as exc:
            job.update(status="failed", error_type=type(exc).__name__)
        finally:
            job["finished_at"] = now()
            with self.lock:
                self._save_job(job)
                self.current = None
