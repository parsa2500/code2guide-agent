"""Phase-one guide lab: pinned Brain API retrieval, local provenance, optional Gemini.

No source parser, local knowledge index, production auth claims or database access.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.integrations.code_kb_client import CodeKbClient
from src.app.services.guide_lab_settings import GuideSettings, FIXED_GUARD

HELP_FILES = {"SuggestedSuppliers.md", "evaluationCriteria.md", "documentation.md",
              "NotificationTemplates.md", "Claims.md", "TemplateIntroduction.md",
              "Setting--evaluation-templates.md"}


def normalized(value: str) -> str:
    return value.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")


def restricted_question(question: str) -> bool:
    text = normalized(question)
    return bool(re.search(r"انتقال کارتابل|جابه.?جایی پست|تنظیم[^.!?؟\n]*دسترسی|دسترسی[^.!?؟\n]*تنظیم|اعطای دسترسی|مدیریت امنیت|رمز عبور|توکن دسترسی|ignore.{0,30}instructions", text, re.I))


def topic_files(question: str) -> set[str]:
    text = normalized(question)
    if re.search(r"منبع|منابع", text):
        return {"SuggestedSuppliers.md"}
    if re.search(r"اعلان|اطلاع رسانی|پیامک|ایمیل|یادآوری", text):
        return {"NotificationTemplates.md"}
    if re.search(r"پرونده|دعاوی", text):
        return {"Claims.md"}
    if re.search(r"ارزیابی|معیار|وزن", text):
        return {"evaluationCriteria.md", "Setting--evaluation-templates.md"}
    if re.search(r"قالب|مستند", text):
        return {"documentation.md", "TemplateIntroduction.md"}
    return set()


class GeminiGuideWriter:
    def __init__(self, key: str, model: str = "gemini-3.1-flash-lite", settings=None):
        if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", model):
            raise ValueError("Invalid Gemini model identifier")
        self.key, self.model = key, model
        self.settings = settings or GuideSettings(model=model).model_dump()

    def generate(self, prompt: str) -> dict[str, Any]:
        schema = {"type": "OBJECT", "properties": {
            "answer": {"type": "STRING"},
            "steps": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "text": {"type": "STRING"}, "citation_ids": {"type": "ARRAY", "items": {"type": "STRING"}}
            }, "required": ["text", "citation_ids"]}},
            "clarification": {"type": "STRING"}
        }, "required": ["answer", "steps", "clarification"]}
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            response = client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.key}, json={
                    "systemInstruction": {"parts": [{"text": FIXED_GUARD + "\n\n" + self.settings["system_prompt"]}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": self.settings["temperature"], "maxOutputTokens": self.settings["max_output_tokens"],
                        **({"thinkingConfig": {"thinkingBudget": 0}} if self.model == "gemini-2.5-flash" else {}),
                        "responseMimeType": "application/json", "responseSchema": schema}
                })
        response.raise_for_status()
        data = response.json()
        result = json.loads("".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought")))
        result["usage"] = data.get("usageMetadata", {})
        return result


class ContractsGuideLab:
    def __init__(self, client: CodeKbClient, workspace: str, revision: str, trace_dir: Path, writer=None, settings_store=None, provider_key=None, managed_knowledge=False):
        if not workspace or not revision:
            raise ValueError("Lab requires a pinned workspace and revision")
        self.client, self.workspace, self.revision = client, workspace, revision
        self.trace_dir, self.writer = trace_dir, writer
        self.settings_store, self.provider_key = settings_store, provider_key
        self.managed_knowledge, self.pipeline = managed_knowledge, None

    def answer(self, question: str, run_id=None) -> dict[str, Any]:
        started = time.perf_counter()
        revision = self.revision
        saved_settings = self.settings_store.get() if self.settings_store else {"revision": "defaults", "settings": GuideSettings().model_dump()}
        settings = saved_settings["settings"]
        writer = self.writer
        if self.settings_store:
            writer = GeminiGuideWriter(self.provider_key, settings["model"], settings) if settings["provider"] == "gemini" and self.provider_key else None
        trace_id = run_id or uuid.uuid4().hex
        out: dict[str, Any] = {"trace_id": trace_id, "status": "partial", "answer": "",
            "steps": [], "citations": [], "code_notes": [], "clarification": "",
            "revision": revision, "workspace": self.workspace,
            "review_status": "pending-human", "role": None, "tenant": None, "app_version": None,
            "model": writer.model if writer else "none", "model_called": False,
            "settings_revision": saved_settings["revision"]}
        trace: dict[str, Any] = {"question": question, "workspace": self.workspace, "revision": revision,
            "prompt_evidence": [], "code_evidence_local_only": [], "model_prompt": None,
            "started_at": datetime.now(timezone.utc).isoformat(), "settings_revision": saved_settings["revision"],
            "settings_snapshot": settings, "system_prompt": FIXED_GUARD + "\n\n" + settings["system_prompt"],
            "events": [], "_started": started}
        if self.pipeline:
            self.pipeline.begin(trace_id,question,revision,saved_settings["revision"])
        def event(stage, **details):
            elapsed_ms=round((time.perf_counter()-started)*1000)
            trace["events"].append({"stage":stage,"elapsed_ms":elapsed_ms,**details})
            if self.pipeline:self.pipeline.event(trace_id,stage,elapsed_ms,**details)
        event("policy")
        if restricted_question(question):
            out.update(status="refuse", answer="این موضوع به مدیریت امنیت یا ساختار سازمانی مربوط است. برای انجام آن به راهبر سامانه مراجعه کنید.")
            return self._finish(out, trace)
        allowed_files = topic_files(question)
        catalog=None
        if self.managed_knowledge:
            try:
                catalog=self.client._request_json("GET",f"/api/lab/knowledge/catalog?revision={revision}")
                filenames={d["name"] for d in catalog["documents"]}
                allowed_files &= filenames
                allowed_files |= {d["name"] for d in catalog["documents"] if any(normalized(k) in normalized(question) for k in d["keywords"])}
            except Exception as exc:
                event("error",error_type=type(exc).__name__)
                out.update(status="escalate",answer="نسخه منابع مجاز در دسترس نیست؛ دوباره تلاش کنید.")
                return self._finish(out,trace)
        event("topic", files=sorted(allowed_files))
        if not allowed_files:
            out.update(status="clarify", answer="این آزمایش فعلاً پنج موضوع منتخب را پوشش می‌دهد.", clarification="منظورتان منابع پیشنهادی، معیار ارزیابی، قالب مستندات، اعلان یا پرونده دعاوی است؟")
            return self._finish(out, trace)
        try:
            event("retrieval_started",question=question,revision=revision,workspace=self.workspace)
            hub = self.client._request_json("POST", f"/api/v2/workspaces/{self.workspace}/query", {
                "brain": "guide", "text": question, "revisionId": revision,
                "budget": {"maxSearchHits": settings["max_search_hits"], "maxSeeds": settings["max_seeds"], "maxEvidenceItems": settings["max_evidence_items"], "maxEvidenceTokens": settings["max_evidence_tokens"]}})
            packet = hub.get("evidencePacket") or {}
            actual = (packet.get("meta") or {}).get("revision")
            scope = packet.get("query") or {}
            if actual != revision or scope.get("workspaceId") != self.workspace:
                raise ValueError("Brain scope/revision mismatch")
            rows = {r["evidence"]["id"]: r["evidence"] for r in (packet.get("data") or {}).get("evidence", [])}
            event("retrieval_finished", count=len(rows))
            docs, local, local_documents = [], [], []
            managed={d["name"]:d for d in catalog["documents"]} if catalog else None
            for citation in packet.get("citations", []):
                evidence = rows.get(citation.get("evidenceId"), {})
                resource = (evidence.get("metadata") or {}).get("resource") or {}
                attrs = resource.get("attributes") or {}
                if evidence.get("kind") != "document" or not attrs.get("sourceHash"):
                    continue
                uri = citation.get("uri", "")
                content = evidence.get("content", "")
                item = {"id": citation["id"], "uri": uri, "start_line": citation.get("startLine"),
                    "end_line": citation.get("endLine"), "source_hash": attrs["sourceHash"],
                    "excerpt": content, "review_status": attrs.get("reviewStatus", "unknown"),
                    "revision": actual, "title": citation.get("title", "")}
                if uri.endswith("/q05-code-links.md") and "منابع" in question:
                    local.append(item)
                elif uri.rsplit("/", 1)[-1] in allowed_files and not any(word in normalized(content) for word in ["دسترسی", "کاربر جدید", "پست سازمانی", "مدیریت امنیت"]):
                    name=uri.rsplit("/",1)[-1]
                    if managed is not None:
                        permission=managed.get(name)
                        if not permission or permission["sourceHash"]!=attrs["sourceHash"]:
                            raise ValueError("Published document hash mismatch")
                        if not permission["externalEligible"]:
                            local_documents.append(item)
                            continue
                    elif name not in HELP_FILES:
                        continue
                    docs.append(item)
            docs = docs[:settings["max_document_chunks"]]
            local = local[:settings["max_code_notes"]]
            event("evidence_selected", document_chunks=len(docs), local_code_chunks=len(local), documents=docs, local_code=local, local_documents=local_documents)
            trace["retrieved_evidence_ids"] = list(rows)
            trace["code_evidence_local_only"] = local
            out["code_notes"] = [{"text": x["excerpt"], "citation_id": x["id"]} for x in local]
            out["local_document_notes"] = local_documents
            out["citations"] = [{**x, "url": f"/api/evidence/{trace_id}/{x['id']}"} for x in docs + local + local_documents]
            if not docs:
                out.update(status="clarify", answer="برای این سؤال شاهد کافی از راهنمای مجاز پیدا نشد.", clarification="نام فرم یا مرحله‌ای که در آن هستید چیست؟")
                return self._finish(out, trace)
            if writer is None:
                out.update(answer="شواهد مرتبط پیدا شد. تولید پاسخ با مدل در این اجرا فعال نیست؛ منابع را بررسی کنید.")
                return self._finish(out, trace)
            prompt = json.dumps({"question": question, "scope": settings["scope_prompt"], "evidence": docs}, ensure_ascii=False)
            trace["prompt_evidence"], trace["model_prompt"] = docs, prompt
            trace["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
            out["model_called"] = True
            event("generation_started", model=writer.model, prompt=prompt, system_prompt=trace["system_prompt"])
            generated = writer.generate(prompt)
            trace["usage"] = generated.get("usage", {})
            event("generation_finished",output=generated)
            event("citation_validation_started")
            valid_ids = {x["id"] for x in docs}
            steps = generated.get("steps")
            if not isinstance(steps, list) or len(steps) > settings["max_steps"]:
                raise ValueError("Invalid steps")
            for step in steps:
                if not isinstance(step, dict) or not isinstance(step.get("text"), str) or not step["text"].strip():
                    raise ValueError("Invalid step text")
                ids = step.get("citation_ids")
                if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i in valid_ids for i in ids):
                    raise ValueError("Unsupported citation")
                if restricted_question(step["text"]):
                    raise ValueError("Administrative instruction rejected")
            clarification = str(generated.get("clarification") or "").strip()[:600]
            # Do not display unsupported certainty statements from a free-text model field.
            if steps:
                clarification = ""
            elif not clarification.endswith(("؟", "?")) or restricted_question(clarification):
                clarification = "نام فرم و مرحله‌ای که در آن هستید چیست؟"
            out.update(steps=steps, clarification=clarification,
                answer="پیش‌نویس پاسخ بر اساس راهنمای موجود؛ نقش و نسخهٔ سامانه شما هنوز تطبیق داده نشده است.",
                status="partial" if steps else "clarify")
            event("citation_validation", steps=len(steps), passed=True)
        except Exception as exc:
            # Provider/network error messages can contain private URLs: keep only class.
            out.update(status="escalate", answer="بازیابی یا تولید پاسخ معتبر کامل نشد. دوباره تلاش کنید یا به پشتیبانی ارجاع دهید.", steps=[], code_notes=[])
            trace["error_type"] = type(exc).__name__
            event("error", error_type=type(exc).__name__)
            if isinstance(exc, httpx.HTTPStatusError):
                trace["provider_http_status"] = exc.response.status_code
                try:
                    code = exc.response.json().get("error", {}).get("status")
                    if isinstance(code, str) and re.fullmatch(r"[A-Z_]+", code):
                        trace["provider_error_code"] = code
                except ValueError:
                    pass
        return self._finish(out, trace)

    def _finish(self, out: dict, trace: dict) -> dict:
        duration = round((time.perf_counter() - trace.pop("_started", time.perf_counter())) * 1000)
        trace["duration_ms"] = duration
        trace.setdefault("events", []).append({"stage": "finished", "elapsed_ms": duration, "status": out["status"]})
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        trace["response"] = out
        (self.trace_dir / f"{out['trace_id']}.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.pipeline:
            self.pipeline.complete(out["trace_id"],out,duration)
        return out

    def evidence(self, trace_id: str, citation_id: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{32}", trace_id):
            return None
        try:
            trace = json.loads((self.trace_dir / f"{trace_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return next((x for x in trace["response"]["citations"] if x["id"] == citation_id), None)
