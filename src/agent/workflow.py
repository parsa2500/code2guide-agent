"""LangGraph Workflow and StateGraph ReAct execution cycle for Code2Guide."""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Set

from src.core.config import settings
from src.core.markdown_guide import normalize_guide_markdown
from src.core.normalizer import default_normalizer
from src.parsers.ast_visitor import DiscoveredForm, ComponentInspection
from src.parsers.route_extractor import RouteNode
from src.agent.state import AgentState
from src.agent.tools import Code2GuideToolbox, dump_model
from src.agent.prompts import SYSTEM_PROMPT, UX_GUIDE_TEMPLATE
from src.knowledge.schema import NodeType

try:
    from langgraph.graph import StateGraph, END
    _has_langgraph = True
except ImportError:
    _has_langgraph = False
    StateGraph = None
    END = "__end__"


class Code2GuideWorkflow:
    """Manages LangGraph StateGraph nodes, edges, and ReAct discovery cycle."""

    def __init__(
        self,
        workspace_path: Optional[str] = None,
        toolbox: Optional[Code2GuideToolbox] = None,
    ):
        self.workspace_path = workspace_path or settings.target_workspace_path
        self.toolbox = toolbox or Code2GuideToolbox(self.workspace_path)
        self.normalizer = default_normalizer
        self.compiled_graph = self._build_graph()

    def _build_graph(self):
        """Constructs and compiles StateGraph if langgraph is available."""
        if not _has_langgraph:
            return None

        workflow = StateGraph(AgentState)

        workflow.add_node("discover_routes", self.node_discover_routes)
        workflow.add_node("search_labels", self.node_search_labels)
        workflow.add_node("inspect_ast", self.node_inspect_ast)
        workflow.add_node("synthesize_guide", self.node_synthesize_guide)

        workflow.set_entry_point("discover_routes")
        workflow.add_edge("discover_routes", "search_labels")
        workflow.add_edge("search_labels", "inspect_ast")
        workflow.add_edge("inspect_ast", "synthesize_guide")
        workflow.add_edge("synthesize_guide", END)

        return workflow.compile()

    def node_discover_routes(self, state: AgentState) -> Dict[str, Any]:
        state.iteration += 1
        query = state.query
        cleaned_query = self.normalizer.clean_search_query(query)
        keywords = self.normalizer.extract_keywords(query)
        state.normalized_query = " ".join(keywords)

        index_info = self.toolbox.ensure_indexed()
        from_store = bool(index_info.get("from_store"))

        route_res = self.toolbox.get_route_hierarchy(cleaned_query)
        matching_routes = [RouteNode(**r) for r in route_res.get("routes", [])]

        if not matching_routes and keywords:
            for kw in keywords:
                sub_routes = self.toolbox.get_route_hierarchy(kw).get("routes", [])
                for sr in sub_routes:
                    r_node = RouteNode(**sr)
                    if not any(x.path == r_node.path for x in matching_routes):
                        matching_routes.append(r_node)

        # Graph lexical search for routes when index exists
        if self.toolbox.graph_store.status().get("exists"):
            for n in self.toolbox.graph_store.search_nodes(
                query,
                node_types=[NodeType.ROUTE.value, NodeType.PAGE.value],
                limit=10,
            ):
                path = (n.payload or {}).get("path") or ""
                if path and not any(x.path == path for x in matching_routes):
                    matching_routes.append(
                        RouteNode(
                            path=path,
                            title=n.title or (n.payload or {}).get("title"),
                            component_name=(n.payload or {}).get("component_name"),
                            file_path=n.file_path or None,
                            breadcrumbs=list((n.payload or {}).get("breadcrumbs") or []),
                        )
                    )

        hybrid_res = self.toolbox.hybrid_search(query, limit=12)
        hybrid_hits = hybrid_res.get("hits", [])
        state.hybrid_hits = hybrid_hits
        for r_node in self.toolbox.routes_from_hybrid_hits(hybrid_hits):
            if not any(x.path == r_node.path for x in matching_routes):
                matching_routes.append(r_node)

        best_crumbs = route_res.get("best_breadcrumbs", [])
        if not best_crumbs and matching_routes:
            best_crumbs = matching_routes[0].breadcrumbs
        if not best_crumbs and hybrid_hits:
            meta = hybrid_hits[0].get("metadata") or {}
            crumbs = meta.get("breadcrumbs") or []
            if crumbs:
                best_crumbs = list(crumbs)

        state.identified_routes = matching_routes
        state.extracted_breadcrumbs = best_crumbs

        state.is_backend_query = self.toolbox.is_backend_query(query)
        backend_hits = self.toolbox.search_backend(query, limit=12)
        # If hybrid already returned backend item types, ensure they're included
        for hit in hybrid_hits:
            if hit.get("item_type") in ("api", "service", "entity", "table"):
                hid = hit.get("id") or ""
                if hid and not any(b.get("id") == hid for b in backend_hits):
                    backend_hits.append(
                        {
                            "id": hid,
                            "title": hit.get("title") or "",
                            "node_type": hit.get("item_type"),
                            "file_path": hit.get("file_path") or "",
                            "payload": hit.get("metadata") or {},
                        }
                    )
        state.backend_hits = backend_hits

        route_paths = [r.path for r in matching_routes]
        state.required_roles = self.toolbox.roles_for_routes(route_paths)
        state.api_endpoints = self.toolbox.related_api_endpoints(state.query)
        for ep in state.api_endpoints:
            for role in ep.roles_required:
                if role not in state.required_roles:
                    state.required_roles.append(role)

        state.steps_taken.append(
            f"Discovered {len(matching_routes)} candidate routes"
            + (f", roles={state.required_roles}" if state.required_roles else "")
            + f"; Hybrid hits={len(hybrid_hits)} use_vector={hybrid_res.get('use_vector')} "
            + f"indexed={index_info.get('indexed_count')} from_store={from_store}"
            + f"; backend_hits={len(backend_hits)} backend_query={state.is_backend_query}"
        )
        return dump_model(state)

    def node_search_labels(self, state: AgentState) -> Dict[str, Any]:
        keywords = self.normalizer.extract_keywords(state.query)
        all_matches = []
        seen_lines = set()
        used_index = False

        # Prefer knowledge-graph / hybrid label hits
        for q in [state.normalized_query or state.query, *keywords]:
            if not q:
                continue
            for m in self.toolbox.search_index_labels(q, limit=15):
                used_index = True
                k = (m["file_path"], m["line_number"], m.get("line_content"))
                if k not in seen_lines:
                    seen_lines.add(k)
                    all_matches.append(m)

        # Ripgrep only as fallback when index yields nothing useful
        if not all_matches:
            res = self.toolbox.search_persian_labels(state.normalized_query or state.query)
            for m in res.get("matches", []):
                k = (m["file_path"], m["line_number"])
                if k not in seen_lines:
                    seen_lines.add(k)
                    all_matches.append(m)
            for kw in keywords:
                sub = self.toolbox.search_persian_labels(kw)
                for m in sub.get("matches", []):
                    k = (m["file_path"], m["line_number"])
                    if k not in seen_lines:
                        seen_lines.add(k)
                        all_matches.append(m)

        for hit in state.hybrid_hits:
            fpath = hit.get("file_path") or ""
            if fpath.endswith((".tsx", ".jsx", ".vue")):
                k = (fpath, 0, hit.get("title") or "")
                if k not in seen_lines:
                    seen_lines.add(k)
                    all_matches.append(
                        {
                            "file_path": fpath,
                            "line_number": 0,
                            "line_content": hit.get("title") or "",
                            "context_before": [],
                            "context_after": [],
                            "from_index": True,
                        }
                    )

        target_files = {
            m["file_path"]
            for m in all_matches
            if m.get("file_path", "").endswith((".tsx", ".jsx", ".vue"))
        }
        src = "index" if used_index else "ripgrep"
        state.steps_taken.append(
            f"Found {len(all_matches)} label matches via {src} across {len(target_files)} UI files"
        )
        return dump_model(state)

    def node_inspect_ast(self, state: AgentState) -> Dict[str, Any]:
        target_files: Set[str] = set()
        ws_root = Path(state.workspace_path)
        index_exists = bool(self.toolbox.graph_store.status().get("exists"))

        for r in state.identified_routes:
            if r.file_path and r.file_path.endswith((".tsx", ".jsx", ".vue")):
                full_rf = ws_root / r.file_path
                if full_rf.exists() and r.component_name:
                    try:
                        with open(full_rf, "r", encoding="utf-8") as f:
                            r_code = f.read()
                        m = re.search(
                            r'import\s+.*?' + re.escape(r.component_name) + r'.*?from\s+[\'"]([^\'"]+)[\'"]',
                            r_code,
                        )
                        if m:
                            import_path = m.group(1)
                            resolved_rel = self.toolbox.resolve_import_path(import_path, r.file_path)
                            if resolved_rel:
                                target_files.add(resolved_rel)
                            else:
                                base_dir = full_rf.parent
                                for ext in [".tsx", ".jsx", "/index.tsx", "/index.jsx"]:
                                    cand = (base_dir / (import_path + ext)).resolve()
                                    if cand.exists():
                                        target_files.add(str(cand.relative_to(ws_root)).replace("\\", "/"))
                                        break
                    except Exception:
                        pass
                target_files.add(r.file_path)

        for hit in state.hybrid_hits:
            fpath = (hit.get("file_path") or "").replace("\\", "/")
            if fpath.endswith((".tsx", ".jsx", ".vue")):
                target_files.add(fpath)
            # Field/form hits may only carry form metadata — still use file_path
            meta = hit.get("metadata") or {}
            form_id = meta.get("form_id") or ""
            if form_id.startswith("form:") and ":" in form_id:
                # form:{path}:{idx}
                parts = form_id.split(":")
                if len(parts) >= 2:
                    candidate = ":".join(parts[1:-1]) if len(parts) > 2 else parts[1]
                    if candidate.endswith((".tsx", ".jsx", ".vue")):
                        target_files.add(candidate)

        discovered_forms: List[DiscoveredForm] = []
        inspected_comps: List[ComponentInspection] = []
        validation_notes: List[str] = []
        source = "live_ast"

        if index_exists:
            # Retrieval-first: rehydrate forms from graph for matched files (or all if empty)
            file_list = sorted(target_files) if target_files else None
            indexed_forms = self.toolbox.forms_from_index(file_list)
            if not indexed_forms and target_files:
                # Try without filter if path mismatch
                indexed_forms = self.toolbox.forms_from_index(None)
                # Keep only forms whose file appears in hybrid/route targets or query hits
                if target_files:
                    indexed_forms = [
                        f for f in indexed_forms if f.file_path in target_files
                    ] or indexed_forms
            if indexed_forms:
                source = "index"
                discovered_forms = indexed_forms
                inspected_comps = self.toolbox.components_from_index(
                    [f.file_path for f in indexed_forms]
                )
                for f in indexed_forms:
                    # Pull validation notes stored on form payload if present
                    node = self.toolbox.graph_store.list_nodes(NodeType.FORM)
                    for n in node:
                        if n.file_path == f.file_path:
                            for note in (n.payload or {}).get("validation_notes") or []:
                                if note not in validation_notes:
                                    validation_notes.append(note)

        if not discovered_forms:
            # Fallback: live AST with configurable limit (0 = unlimited)
            keywords = self.normalizer.extract_keywords(state.query)
            for kw in keywords:
                sub = self.toolbox.search_persian_labels(kw)
                for m in sub.get("matches", []):
                    fpath = m["file_path"]
                    if fpath.endswith((".tsx", ".jsx", ".vue")):
                        target_files.add(fpath)

            if not target_files:
                for p in ws_root.glob("**/*.tsx"):
                    if "node_modules" not in str(p) and not p.name.startswith("."):
                        target_files.add(str(p.relative_to(ws_root)).replace("\\", "/"))
                        if len(target_files) >= 5:
                            break

            sorted_files = sorted(
                list(target_files),
                key=lambda x: (
                    0
                    if "pages" in x.lower()
                    or "views" in x.lower()
                    or "create" in x.lower()
                    or "form" in x.lower()
                    else 1
                ),
            )
            limit = settings.ast_inspect_limit
            files_to_parse = sorted_files if not limit or limit <= 0 else sorted_files[:limit]

            for fpath in files_to_parse:
                inspection_data = self.toolbox.inspect_component(fpath)
                if "error" not in inspection_data:
                    forms = [DiscoveredForm(**f) for f in inspection_data.get("forms", [])]
                    for note in inspection_data.get("validation_notes") or []:
                        if note not in validation_notes:
                            validation_notes.append(note)
                    if forms and (forms[0].fields or forms[0].buttons):
                        discovered_forms.extend(forms)
                        inspected_comps.append(
                            ComponentInspection(
                                file_path=fpath,
                                component_name=inspection_data.get("component_name"),
                                forms=forms,
                                standalone_fields=[],
                                standalone_buttons=[],
                            )
                        )
            source = "live_ast"

        state.discovered_forms = discovered_forms
        state.inspected_components = inspected_comps
        state.validation_notes = validation_notes
        state.steps_taken.append(
            f"Loaded forms via {source}: {len(inspected_comps)} components, "
            f"{len(discovered_forms)} forms, {len(validation_notes)} validation notes"
        )
        return dump_model(state)

    def node_synthesize_guide(self, state: AgentState) -> Dict[str, Any]:
        """Synthesizes Persian UX guidance using real LLM if configured, or deterministic template fallback."""
        # 1. Prepare structured data
        nav_lines = []
        if state.extracted_breadcrumbs:
            crumb_str = " > ".join(state.extracted_breadcrumbs)
            nav_lines.append("۱. از طریق منوی سامانه، مسیر زیر را دنبال کنید:\n   **" + crumb_str + "**")
        else:
            nav_lines.append("۱. وارد صفحه اصلی یا داشبورد سامانه شوید.")

        page_url = "/"
        if state.identified_routes:
            best_route = state.identified_routes[0]
            page_url = best_route.path
            nav_lines.append("۲. مستقیماً می‌توانید به آدرس `" + page_url + "` مراجعه فرمایید.")
        else:
            nav_lines.append("۲. به بخش مربوطه در منوی کاربری مراجعه نمایید.")

        nav_section = "\n".join(nav_lines)

        req_fields = []
        opt_fields = []
        all_fields = []

        for f in state.discovered_forms:
            for field in f.fields:
                all_fields.append(field)
                fname = field.label or field.name or "فیلد ورودی"
                ftype = f"({field.field_type})" if field.field_type else ""
                val_note = f" - *اعتبارسنجی: {field.validation_message}*" if field.validation_message else ""
                item_str = f"- **{fname}** {ftype}{val_note}"

                if field.required:
                    req_fields.append(item_str)
                else:
                    opt_fields.append(item_str)

        fields_lines = []
        if req_fields:
            fields_lines.append("#### فیلدهای الزامی (*):")
            fields_lines.extend(req_fields)
        if opt_fields:
            fields_lines.append("\n#### فیلدهای اختیاری:")
            fields_lines.extend(opt_fields)

        if not all_fields:
            fields_lines.append("- اطلاعات پایه مورد نیاز را مطابق فرم در دسترس وارد فرمایید.")

        if state.validation_notes:
            fields_lines.append("\n#### قیود اعتبارسنجی کشف‌شده از اسکیما/فرم:")
            for note in state.validation_notes[:12]:
                fields_lines.append(f"- {note}")

        fields_section = "\n".join(fields_lines)

        rbac_notes = ""
        if state.required_roles:
            roles_str = "، ".join(state.required_roles)
            rbac_notes = (
                f"\n> **توجه به دسترسی‌ها (RBAC):** برای انجام این عملیات، حساب کاربری شما "
                f"باید دارای نقش/مجوزهای: `{roles_str}` باشد.\n"
            )

        action_button = None
        for f in state.discovered_forms:
            for b in f.buttons:
                if b.is_submit:
                    action_button = b
                    break
            if action_button:
                break

        if not action_button and state.discovered_forms and state.discovered_forms[0].buttons:
            action_button = state.discovered_forms[0].buttons[0]

        if action_button:
            btn_name = action_button.label or "ثبت"
            dis_status = "در صورت عدم تکمیل فیلدهای اجباری غیرفعال (Disabled) می‌باشد." if action_button.disabled else "پس از تکمیل اطلاعات فعال می‌گردد."
            action_section = (
                f"- **نام دکمه:** دکمه «**{btn_name}**» در پایین فرم.\n"
                f"- **وضعیت:** {dis_status}\n"
                f"- **رفتار:** با کلیک بر روی این دکمه، اعتبارسنجی داده‌ها بررسی شده و فرم جهت ثبت نهایی به سامانه ارسال می‌گردد."
            )
        else:
            action_section = (
                "- **نام دکمه:** دکمه «**ثبت نهایی**» یا «**ذخیره**».\n"
                "- **رفتار:** پس از پر کردن فیلدهای ضروری، با فشردن دکمه اقدام، فرآیند ثبت تکمیل و پیام تایید نمایش داده می‌شود."
            )

        task_title = state.query.replace("چگونه", "").replace("کنم؟", "").replace("کنیم؟", "").strip() or "عملیات"

        backend_md = self.toolbox.format_backend_markdown(state.backend_hits or [])

        # Pure backend Q&A: answer from indexed graph with citations (skip UX template noise)
        if state.is_backend_query and backend_md and (
            not state.discovered_forms or len(state.backend_hits) > 0
        ):
            guide = (
                f"## پاسخ بر اساس ایندکس بک‌اند\n\n"
                f"**پرسش:** {state.query}\n\n"
                f"{backend_md}\n"
            )
            state.final_persian_guide = normalize_guide_markdown(guide)
            state.status = "completed"
            state.steps_taken.append(
                f"Synthesized backend answer from {len(state.backend_hits)} indexed symbols"
            )
            return dump_model(state)

        # 2. Attempt Real LLM Synthesis if API key is provided (OpenRouter preferred)
        api_key = (
            settings.openrouter_api_key
            or os.getenv("OPENROUTER_API_KEY")
            or settings.openai_api_key
            or os.getenv("OPENAI_API_KEY")
        )
        if api_key:
            try:
                model_name = settings.openrouter_model or settings.default_model
                llm_output = self._call_real_llm(
                    state=state,
                    task_title=task_title,
                    nav_section=nav_section,
                    page_url=page_url,
                    fields_section=fields_section,
                    action_section=action_section,
                    api_key=api_key,
                    model_name=model_name,
                    rbac_notes=rbac_notes,
                )
                if llm_output and "مسیر دسترسی" in llm_output:
                    state.final_persian_guide = normalize_guide_markdown(llm_output)
                    state.status = "completed"
                    state.steps_taken.append(
                        f"Synthesized intelligent Persian guide using LLM ({model_name})"
                    )
                    return dump_model(state)
            except Exception as e:
                # Log error and continue to deterministic template fallback
                state.steps_taken.append(f"LLM synthesis fallback due to: {str(e)}")

        # 3. Deterministic Template Fallback
        guide = UX_GUIDE_TEMPLATE.format(
            task_title=task_title,
            navigation_steps=nav_section,
            rbac_notes=rbac_notes,
            page_url=page_url,
            fields_breakdown=fields_section,
            action_description=action_section
        )
        if backend_md:
            guide = guide.rstrip() + "\n\n" + backend_md + "\n"

        state.final_persian_guide = normalize_guide_markdown(guide)
        state.status = "completed"
        state.steps_taken.append("Synthesized structured Persian guide via template engine")
        return dump_model(state)

    def _call_real_llm(
        self,
        state: AgentState,
        task_title: str,
        nav_section: str,
        page_url: str,
        fields_section: str,
        action_section: str,
        api_key: str,
        model_name: Optional[str] = None,
        rbac_notes: str = "",
    ) -> Optional[str]:
        """Invokes ChatOpenAI or OpenAI client (OpenRouter-compatible) for UX guidance."""
        model = model_name or settings.openrouter_model or settings.default_model
        base_url = settings.openrouter_base_url or os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        api_bits = ""
        if state.api_endpoints:
            api_bits = "\n".join(
                f"- {ep.method} {ep.path}"
                + (f" roles={ep.roles_required}" if ep.roles_required else "")
                for ep in state.api_endpoints[:6]
            )
        user_prompt = f"""پرسش کاربر: {state.query}
عنوان عملیات استخراج‌شده: {task_title}

داده‌های فنی استخراج‌شده از تحلیل AST و روت‌های سورس‌کد:
۱. اطلاعات مسیر و روتینگ:
- مسیرهای منو (Breadcrumbs): {" > ".join(state.extracted_breadcrumbs) if state.extracted_breadcrumbs else "صفحه اصلی"}
- آدرس URL صفحه هدف: {page_url}
- فایل‌های بازرسی‌شده: {[c.file_path for c in state.inspected_components]}
{rbac_notes}
۲. اطلاعات فیلدها و فرم‌های صفحه:
{fields_section}

۳. دکمه اقدام نهایی:
{action_section}

۴. قراردادهای API مرتبط (در صورت وجود):
{api_bits or "- موردی یافت نشد"}

لطفاً به عنوان دستیار هوشمند، بر اساس داده‌های قطعی استخراج‌شده بالا، یک راهنمای بسیار سلیس، دقیق، گام‌به‌گام و کاربردی به زبان فارسی و با حفظ کامل ساختار سه بخشی زیر ارائه دهید:
### ۱. مسیر دسترسی (Navigation)
### ۲. اطلاعات لازم و فیلدهای فرم (Form Fields)
### ۳. دکمه اقدام نهایی (Action)
اگر محدودیت RBAC وجود دارد، آن را در بخش مسیر دسترسی ذکر کنید.
"""
        # Try LangChain ChatOpenAI first (OpenRouter-compatible)
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            llm = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0.1,
            )
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ])
            return str(response.content)
        except ImportError:
            pass

        # Try official OpenAI SDK client against OpenRouter
        try:
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            return completion.choices[0].message.content
        except ImportError:
            pass

        return None

    def run(self, query: str, workspace_path: Optional[str] = None) -> AgentState:
        ws_path = workspace_path or self.workspace_path
        initial_state = AgentState(
            query=query,
            workspace_path=ws_path
        )

        if self.compiled_graph is not None:
            output = self.compiled_graph.invoke(initial_state)
            if isinstance(output, dict):
                return AgentState(**output)
            return output
        else:
            s = initial_state
            self.node_discover_routes(s)
            self.node_search_labels(s)
            self.node_inspect_ast(s)
            self.node_synthesize_guide(s)
            return s


class Code2GuideAgent:
    """Public wrapper for Code2Guide Agent."""

    def __init__(
        self,
        workspace_path: Optional[str] = None,
        toolbox: Optional[Code2GuideToolbox] = None,
    ):
        self.workflow = Code2GuideWorkflow(workspace_path, toolbox=toolbox)

    def ask(self, query: str, workspace_path: Optional[str] = None) -> AgentState:
        return self.workflow.run(query=query, workspace_path=workspace_path)
