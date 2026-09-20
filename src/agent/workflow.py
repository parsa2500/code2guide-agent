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
from src.agent.abstain import apply_abstain_to_state, explicit_route_or_label_hit
from src.agent.tools import Code2GuideToolbox, dump_model
from src.agent.prompts import (
    SYSTEM_PROMPT,
    UX_GUIDE_TEMPLATE,
    END_USER_SYSTEM_PROMPT,
    END_USER_GUIDE_TEMPLATE,
)
from src.agent.planner import QueryPlanner
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
        *,
        workspace_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ):
        self.workspace_path = workspace_path or settings.target_workspace_path
        self.workspace_id = workspace_id
        self.revision_id = revision_id
        self.toolbox = toolbox or Code2GuideToolbox(
            self.workspace_path,
            workspace_id=workspace_id,
            revision_id=revision_id,
        )
        self.normalizer = default_normalizer
        self.planner = QueryPlanner()
        self.compiled_graph = self._build_graph()

    def _build_graph(self):
        """Constructs and compiles StateGraph if langgraph is available."""
        if not _has_langgraph:
            return None

        workflow = StateGraph(AgentState)

        workflow.add_node("plan_query", self.node_plan_query)
        workflow.add_node("discover_routes", self.node_discover_routes)
        workflow.add_node("search_labels", self.node_search_labels)
        workflow.add_node("inspect_ast", self.node_inspect_ast)
        workflow.add_node("gather_evidence", self.node_gather_evidence)
        workflow.add_node("synthesize_guide", self.node_synthesize_guide)

        workflow.set_entry_point("plan_query")
        workflow.add_edge("plan_query", "discover_routes")
        workflow.add_edge("discover_routes", "search_labels")
        workflow.add_edge("search_labels", "inspect_ast")
        workflow.add_edge("inspect_ast", "gather_evidence")
        workflow.add_edge("gather_evidence", "synthesize_guide")
        workflow.add_edge("synthesize_guide", END)

        return workflow.compile()

    def node_plan_query(self, state: AgentState) -> Dict[str, Any]:
        plan = self.planner.plan(state.query)
        if getattr(state, "audience", "technical") == "end_user":
            # End-user mode: always UX-only; never backend/flow synthesis
            plan.intent = "ux"
            plan.skip_ux_template = False
            state.is_backend_query = False
            state.is_flow_query = False
        else:
            state.is_backend_query = plan.intent in ("api", "data", "mixed") or Code2GuideToolbox.is_backend_query(
                state.query
            )
            state.is_flow_query = plan.intent in ("flow", "mixed") or Code2GuideToolbox.is_flow_query(state.query)
        state.query_plan = plan.model_dump()
        state.steps_taken.append(
            f"Planned intent={plan.intent} tools={plan.tools} skip_ast={plan.skip_ast}"
            + (f" audience={state.audience}" if state.audience != "technical" else "")
        )
        return dump_model(state)

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

        plan = state.query_plan or {}
        if not plan:
            state.is_backend_query = self.toolbox.is_backend_query(query)
            state.is_flow_query = self.toolbox.is_flow_query(query)
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

        if state.is_flow_query or (state.is_backend_query and matching_routes) or (
            (state.query_plan or {}).get("intent") in ("flow", "mixed")
        ):
            ref = (state.query_plan or {}).get("trace_ref") or "/"
            if matching_routes:
                ref = matching_routes[0].path or matching_routes[0].file_path or ref
            elif ref == "/":
                ref = self.toolbox.infer_trace_ref_from_query(query)
            state.flow_trace = self.toolbox.trace_flow(ref)

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
        
        # Evidence-rescue: unknown intent + strong route/form hits → ux
        plan = state.query_plan or {}
        if isinstance(plan, dict) and plan.get("intent") == "unknown":
            from src.agent.planner import QueryPlan

            qp = QueryPlan(**plan) if not isinstance(plan, QueryPlan) else plan
            try:
                qp = self.planner.rescue_from_evidence(
                    qp,
                    route_hit=explicit_route_or_label_hit(state),
                    label_hit=explicit_route_or_label_hit(state),
                )
                state.query_plan = qp.model_dump() if hasattr(qp, "model_dump") else qp.dict()
                if qp.intent == "ux":
                    state.steps_taken.append("Rescued intent unknown→ux via route/form evidence")
            except Exception:
                pass

        return dump_model(state)

    def node_search_labels(self, state: AgentState) -> Dict[str, Any]:
        plan = state.query_plan or {}
        if plan.get("skip_ast") or plan.get("skip_ux_template"):
            state.steps_taken.append("Skipped label search (intent does not need UX labels)")
            return dump_model(state)

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
        plan = state.query_plan or {}
        if plan.get("skip_ast"):
            state.steps_taken.append("Skipped AST inspect (flow/api/data intent)")
            return dump_model(state)

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

        # Evidence-rescue after forms/labels discovered
        plan = state.query_plan or {}
        if isinstance(plan, dict) and plan.get("intent") == "unknown":
            from src.agent.planner import QueryPlan

            qp = QueryPlan(**plan) if not isinstance(plan, QueryPlan) else plan
            try:
                qp = self.planner.rescue_from_evidence(
                    qp,
                    route_hit=explicit_route_or_label_hit(state),
                    label_hit=explicit_route_or_label_hit(state),
                )
                state.query_plan = qp.model_dump() if hasattr(qp, "model_dump") else qp.dict()
                if qp.intent == "ux":
                    state.steps_taken.append("Rescued intent unknown→ux via form/label evidence")
            except Exception:
                pass

        return dump_model(state)

    def node_gather_evidence(self, state: AgentState) -> Dict[str, Any]:
        plan = state.query_plan or {}
        tools = list(plan.get("tools") or ["search_code"])
        intent = plan.get("intent") or "ux"
        if intent in ("flow", "api", "data", "mixed") and "trace_flow" not in tools and intent in (
            "flow",
            "mixed",
        ):
            tools.append("trace_flow")

        trace_ref = plan.get("trace_ref")
        if state.identified_routes:
            trace_ref = state.identified_routes[0].path or trace_ref

        evidence = self.toolbox.gather_tool_evidence(
            state.query,
            tools=tools,
            trace_ref=trace_ref,
        )
        # Enrich from already-discovered UX forms (cited)
        for f in state.discovered_forms:
            for field in f.fields:
                label = field.label or field.name or ""
                if not label or not f.file_path:
                    continue
                ev = self.toolbox._as_evidence(
                    tool="inspect_form",
                    file_path=f.file_path,
                    symbol=label,
                    id=f"field:{f.file_path}:{field.name or label}",
                    evidence=f"field {label} type={field.field_type} required={field.required}",
                )
                if ev:
                    evidence.append(ev)
        for r in state.identified_routes:
            if not r.file_path and not r.path:
                continue
            ev = self.toolbox._as_evidence(
                tool="get_route",
                file_path=r.file_path or "src/routes.tsx",
                symbol=r.path or r.title,
                id=f"route:{r.path}",
                evidence=f"route {r.path}; breadcrumbs={' > '.join(r.breadcrumbs or [])}",
                extra={"breadcrumbs": list(r.breadcrumbs or []), "path": r.path},
            )
            if ev and not any(e.get("id") == ev.get("id") for e in evidence):
                evidence.append(ev)

        state.tool_evidence = evidence
        state.steps_taken.append(f"Gathered {len(evidence)} cited tool evidence items")
        return dump_model(state)

    def _format_evidence_markdown(self, evidence: List[Dict[str, Any]], tools_filter: Optional[Set[str]] = None) -> str:
        lines: List[str] = []
        for e in evidence:
            if tools_filter and e.get("tool") not in tools_filter:
                continue
            fpath = e.get("file_path") or ""
            symbol = e.get("symbol") or e.get("id") or ""
            text = e.get("evidence") or symbol
            lines.append(f"- **{symbol}** — `{fpath}` — {text}")
        return "\n".join(lines)

    def node_synthesize_guide(self, state: AgentState) -> Dict[str, Any]:
        """Synthesizes Persian guidance from cited evidence; no guessing when empty."""
        if getattr(state, "audience", "technical") == "end_user":
            return self._synthesize_end_user_guide(state)

        plan = state.query_plan or {}
        intent = plan.get("intent") or "ux"
        evidence = state.tool_evidence or []

        # Hard rule: no evidence → refuse to invent
        has_ux = bool(state.discovered_forms or state.identified_routes or state.extracted_breadcrumbs)
        if intent == "unknown" or (
            not evidence and not has_ux and not state.backend_hits and not state.flow_trace
        ):
            state.final_persian_guide = normalize_guide_markdown(
                "## نتیجه جستجو\n\n"
                f"**پرسش:** {state.query}\n\n"
                "در ایندکس یافت نشد. هیچ شاهد استنادپذیری برای این پرسش در گراف دانش موجود نیست.\n"
            )
            state.status = "completed"
            state.steps_taken.append("No evidence — refused to invent answer")
            return dump_model(state)

        backend_md = self.toolbox.format_backend_markdown(state.backend_hits or [])
        flow_md = ""
        if state.flow_trace:
            from src.knowledge.flow_tracer import FlowTracer

            flow_md = FlowTracer(self.toolbox.graph_store).format_markdown(state.flow_trace)
        elif state.is_flow_query:
            ref = (plan.get("trace_ref") or self.toolbox.infer_trace_ref_from_query(state.query))
            if state.identified_routes:
                ref = state.identified_routes[0].path or ref
            flow_md = self.toolbox.format_flow_markdown(ref)

        api_ev = self._format_evidence_markdown(evidence, {"get_api", "search_code"})
        entity_ev = self._format_evidence_markdown(evidence, {"get_entity", "get_table"})
        route_ev = self._format_evidence_markdown(evidence, {"get_route", "inspect_form"})
        flow_ev = self._format_evidence_markdown(evidence, {"trace_flow"})

        # Intent-specialized answers
        if intent == "flow" and (flow_md or flow_ev):
            guide = (
                f"## جریان کامل سیستم\n\n"
                f"**پرسش:** {state.query}\n\n"
                f"{flow_md or flow_ev}\n"
            )
            if backend_md:
                guide += "\n" + backend_md + "\n"
            if route_ev:
                guide += "\n### مسیر UI (با استناد)\n\n" + route_ev + "\n"
            state.final_persian_guide = normalize_guide_markdown(guide)
            state.status = "completed"
            state.steps_taken.append("Synthesized flow answer with citations")
            return dump_model(state)

        if intent in ("api", "data") and (backend_md or api_ev or entity_ev):
            title = "API" if intent == "api" else "داده / Entity / Table"
            guide = (
                f"## پاسخ بر اساس ایندکس ({title})\n\n"
                f"**پرسش:** {state.query}\n\n"
            )
            if intent == "api" and api_ev:
                guide += "### نقاط پایانی API\n\n" + api_ev + "\n\n"
            if intent == "data" and entity_ev:
                guide += "### Entity / Table\n\n" + entity_ev + "\n\n"
            if backend_md:
                guide += backend_md + "\n"
            if flow_md and intent != "api":
                guide += "\n" + flow_md + "\n"
            state.final_persian_guide = normalize_guide_markdown(guide)
            state.status = "completed"
            state.steps_taken.append(f"Synthesized {intent} answer from cited tools")
            return dump_model(state)

        if intent == "mixed":
            parts = [f"## پاسخ ترکیبی\n\n**پرسش:** {state.query}\n"]
            if has_ux or route_ev:
                parts.append("\n### بخش UX\n")
                if state.extracted_breadcrumbs:
                    parts.append("> مسیر: **" + " > ".join(state.extracted_breadcrumbs) + "**\n")
                if route_ev:
                    parts.append(route_ev + "\n")
            if backend_md or api_ev or entity_ev:
                parts.append("\n### بخش بک‌اند\n")
                if api_ev:
                    parts.append(api_ev + "\n")
                if entity_ev:
                    parts.append(entity_ev + "\n")
                if backend_md:
                    parts.append(backend_md + "\n")
            if flow_md or flow_ev:
                parts.append("\n### بخش جریان\n")
                parts.append((flow_md or flow_ev) + "\n")
            if len(parts) == 1:
                parts.append("\nدر ایندکس یافت نشد.\n")
            state.final_persian_guide = normalize_guide_markdown("\n".join(parts))
            state.status = "completed"
            state.steps_taken.append("Synthesized mixed UX+backend+flow answer")
            return dump_model(state)

        # Legacy flow / backend shortcuts when plan says ux but flags set
        if state.is_flow_query and flow_md:
            guide = (
                f"## جریان کامل سیستم\n\n"
                f"**پرسش:** {state.query}\n\n"
                f"{flow_md}\n"
            )
            if backend_md:
                guide += "\n" + backend_md + "\n"
            state.final_persian_guide = normalize_guide_markdown(guide)
            state.status = "completed"
            state.steps_taken.append("Synthesized end-to-end flow trace with citations")
            return dump_model(state)

        if state.is_backend_query and backend_md and (
            not state.discovered_forms or len(state.backend_hits) > 0
        ):
            guide = (
                f"## پاسخ بر اساس ایندکس بک‌اند\n\n"
                f"**پرسش:** {state.query}\n\n"
                f"{backend_md}\n"
            )
            if flow_md:
                guide += "\n" + flow_md + "\n"
            state.final_persian_guide = normalize_guide_markdown(guide)
            state.status = "completed"
            state.steps_taken.append(
                f"Synthesized backend answer from {len(state.backend_hits)} indexed symbols"
            )
            return dump_model(state)

        # UX template path
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
                cite = f" — `{f.file_path}`" if f.file_path else ""
                item_str = f"- **{fname}** {ftype}{val_note}{cite}"

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
            if evidence:
                fields_lines.append(self._format_evidence_markdown(evidence) or "- شاهد مرتبط در ایندکس یافت شد ولی فرم UI استخراج نشد.")
            else:
                fields_lines.append("- در ایندکس یافت نشد.")

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

        api_key = (
            settings.openrouter_api_key
            or os.getenv("OPENROUTER_API_KEY")
            or settings.openai_api_key
            or os.getenv("OPENAI_API_KEY")
        )
        if api_key and not plan.get("skip_ux_template"):
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
                state.steps_taken.append(f"LLM synthesis fallback due to: {str(e)}")

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
        if flow_md:
            guide = guide.rstrip() + "\n\n" + flow_md + "\n"
        if route_ev and "عنوان مناقصه" not in guide:
            guide = guide.rstrip() + "\n\n### استناد مسیر/فیلد\n\n" + route_ev + "\n"

        state.final_persian_guide = normalize_guide_markdown(guide)
        state.status = "completed"
        state.steps_taken.append("Synthesized structured Persian guide via template engine")
        return dump_model(state)

    def _synthesize_end_user_guide(self, state: AgentState) -> Dict[str, Any]:
        """Simple non-technical guide: menu → fields → button. No files/API/citations."""
        has_ux = bool(state.discovered_forms or state.identified_routes or state.extracted_breadcrumbs)
        if not has_ux:
            state.final_persian_guide = normalize_guide_markdown(
                "## چطور این کار را انجام دهید\n\n"
                "در راهنمای سامانه چیزی پیدا نشد. لطفاً سؤال را با نام صفحه یا کار موردنظر دوباره بپرسید.\n"
            )
            state.status = "completed"
            state.steps_taken.append("End-user: no UX evidence — simple refusal")
            return dump_model(state)

        # Navigation in everyday language
        if state.extracted_breadcrumbs:
            steps = state.extracted_breadcrumbs
            nav_lines = ["از منوی اصلی سامانه این مسیر را دنبال کنید:"]
            for i, step in enumerate(steps, 1):
                nav_lines.append(f"{i}. وارد «{step}» شوید.")
            nav_section = "\n".join(nav_lines)
        elif state.identified_routes and state.identified_routes[0].title:
            title = state.identified_routes[0].title
            nav_section = f"از منوی اصلی وارد صفحهٔ «{title}» شوید."
        else:
            nav_section = "از منوی اصلی وارد بخش مربوط به این کار شوید."

        rbac_notes = ""
        if state.required_roles:
            roles_str = "، ".join(state.required_roles)
            rbac_notes = (
                f"\n> برای انجام این کار، حساب کاربری شما باید دسترسی لازم "
                f"({roles_str}) داشته باشد.\n"
            )

        req_labels: List[str] = []
        opt_labels: List[str] = []
        for form in state.discovered_forms:
            for field in form.fields:
                label = (field.label or field.name or "").strip()
                if not label:
                    continue
                # Skip English-only technical names if Persian label missing and looks like camelCase
                if field.required:
                    req_labels.append(label)
                else:
                    opt_labels.append(label)

        fields_lines: List[str] = []
        if req_labels:
            fields_lines.append("این موارد را حتماً پر کنید:")
            for lab in req_labels:
                fields_lines.append(f"- {lab}")
        if opt_labels:
            fields_lines.append("در صورت نیاز می‌توانید این موارد را هم پر کنید:")
            for lab in opt_labels:
                fields_lines.append(f"- {lab}")
        if not fields_lines:
            fields_lines.append("فیلدهای صفحه را طبق برچسب‌های روی فرم پر کنید.")
        fields_section = "\n".join(fields_lines)

        action_button = None
        for form in state.discovered_forms:
            for b in form.buttons:
                if b.is_submit:
                    action_button = b
                    break
            if action_button:
                break
        if not action_button and state.discovered_forms and state.discovered_forms[0].buttons:
            action_button = state.discovered_forms[0].buttons[0]

        if action_button:
            btn_name = action_button.label or "ثبت"
            action_section = (
                f"روی دکمهٔ «{btn_name}» کلیک کنید. "
                "اگر همهٔ موارد لازم را پر کرده باشید، کار ثبت می‌شود و پیام تأیید می‌بینید."
            )
        else:
            action_section = (
                "در پایان روی دکمهٔ ثبت یا ذخیره کلیک کنید تا کار انجام شود."
            )

        task_title = (
            state.query.replace("چگونه", "")
            .replace("چطور", "")
            .replace("کنم؟", "")
            .replace("کنیم؟", "")
            .strip()
            or "این کار"
        )

        plan = state.query_plan or {}
        api_key = (
            settings.openrouter_api_key
            or os.getenv("OPENROUTER_API_KEY")
            or settings.openai_api_key
            or os.getenv("OPENAI_API_KEY")
        )
        if api_key and not plan.get("skip_ux_template"):
            try:
                model_name = settings.openrouter_model or settings.default_model
                llm_output = self._call_real_llm(
                    state=state,
                    task_title=task_title,
                    nav_section=nav_section,
                    page_url="",
                    fields_section=fields_section,
                    action_section=action_section,
                    api_key=api_key,
                    model_name=model_name,
                    rbac_notes=rbac_notes,
                )
                if llm_output and (
                    "از کجا شروع کنید" in llm_output or "چطور این کار را انجام دهید" in llm_output
                ):
                    state.final_persian_guide = normalize_guide_markdown(llm_output)
                    state.status = "completed"
                    state.steps_taken.append(
                        f"Synthesized end-user guide using LLM ({model_name})"
                    )
                    return dump_model(state)
            except Exception as e:
                state.steps_taken.append(f"End-user LLM fallback due to: {str(e)}")

        guide = END_USER_GUIDE_TEMPLATE.format(
            navigation_steps=nav_section,
            rbac_notes=rbac_notes,
            fields_breakdown=fields_section,
            action_description=action_section,
        )
        state.final_persian_guide = normalize_guide_markdown(guide)
        state.status = "completed"
        state.steps_taken.append("Synthesized end-user guide via simple template")
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
        end_user = getattr(state, "audience", "technical") == "end_user"
        if end_user:
            system_prompt = END_USER_SYSTEM_PROMPT
            user_prompt = f"""پرسش کاربر: {state.query}
عنوان کار: {task_title}

داده‌های سادهٔ صفحه (فقط برای راهنمایی کاربر عادی):
۱. مسیر منو:
{nav_section}
{rbac_notes}
۲. فیلدها:
{fields_section}

۳. دکمهٔ نهایی:
{action_section}

فقط یک راهنمای خیلی ساده و کوتاه به فارسی بنویسید با همین سه بخش:
### از کجا شروع کنید
### چه چیزهایی را وارد کنید
### در پایان چه کنید
بدون نام فایل، API، کد، یا URL.
"""
        else:
            system_prompt = SYSTEM_PROMPT
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
                SystemMessage(content=system_prompt),
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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            return completion.choices[0].message.content
        except ImportError:
            pass

        return None

    def run(
        self,
        query: str,
        workspace_path: Optional[str] = None,
        audience: str = "technical",
    ) -> AgentState:
        ws_path = workspace_path or self.workspace_path
        initial_state = AgentState(
            query=query,
            workspace_path=ws_path,
            audience=audience if audience in ("technical", "end_user") else "technical",
        )

        if self.compiled_graph is not None:
            output = self.compiled_graph.invoke(initial_state)
            if isinstance(output, dict):
                state = AgentState(**output)
            else:
                state = output
            store = getattr(self.toolbox, "_graph_store", None)
            apply_abstain_to_state(state, store=store)
            return state
        else:
            s = initial_state
            self.node_plan_query(s)
            self.node_discover_routes(s)
            self.node_search_labels(s)
            self.node_inspect_ast(s)
            self.node_gather_evidence(s)
            self.node_synthesize_guide(s)
            store = getattr(self.toolbox, "_graph_store", None)
            apply_abstain_to_state(s, store=store)
            return s


class Code2GuideAgent:
    """Public wrapper for Code2Guide Agent."""

    def __init__(
        self,
        workspace_path: Optional[str] = None,
        toolbox: Optional[Code2GuideToolbox] = None,
        *,
        workspace_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ):
        self.workspace_id = workspace_id
        self.revision_id = revision_id
        self.workflow = Code2GuideWorkflow(
            workspace_path,
            toolbox=toolbox,
            workspace_id=workspace_id,
            revision_id=revision_id,
        )

    def ask(
        self,
        query: str,
        workspace_path: Optional[str] = None,
        audience: str = "technical",
    ) -> AgentState:
        return self.workflow.run(
            query=query,
            workspace_path=workspace_path,
            audience=audience,
        )
