"""AST Visitor for React/JSX/TSX files.

Extracts UI elements (<button>, <label>, <input>, <Select>), props (disabled, required, placeholder),
validation rules, and form structures using Tree-sitter with a robust fallback.
"""

import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.core.normalizer import PersianNormalizer, default_normalizer

try:
    import tree_sitter_languages
    from tree_sitter import Parser
    _has_tree_sitter = True
except ImportError:
    _has_tree_sitter = False


class UIField(BaseModel):
    """Represents an input field, select dropdown, or form control."""
    name: str = Field(default="", description="Input or field name attribute")
    field_type: str = Field(default="text", description="input, select, textarea, datepicker, etc.")
    label: Optional[str] = Field(default=None, description="Persian or English field label")
    placeholder: Optional[str] = Field(default=None, description="Placeholder text")
    required: bool = Field(default=False, description="Whether field is required")
    disabled: bool = Field(default=False, description="Whether field is disabled")
    validation_message: Optional[str] = Field(default=None, description="Validation error message")
    line_number: int = Field(default=1, description="Line number in source code")


class UIButton(BaseModel):
    """Represents a button or trigger element in the UI."""
    label: str = Field(default="", description="Button text or Persian caption")
    name: Optional[str] = Field(default=None, description="Button id or name attribute")
    action_type: str = Field(default="button", description="submit, reset, button")
    disabled: bool = Field(default=False, description="Disabled status")
    is_submit: bool = Field(default=False, description="Whether this is a primary submit button")
    line_number: int = Field(default=1, description="Line number in source code")


class DiscoveredForm(BaseModel):
    """A detected form component in code with its inputs and action buttons."""
    form_name: Optional[str] = Field(default=None, description="Form identifier or component name")
    file_path: str = Field(description="Relative file path")
    fields: List[UIField] = Field(default_factory=list)
    buttons: List[UIButton] = Field(default_factory=list)
    start_line: int = Field(default=1)
    end_line: int = Field(default=1)


class ComponentInspection(BaseModel):
    """Complete inspection result for a UI component file."""
    file_path: str
    component_name: Optional[str] = None
    forms: List[DiscoveredForm] = Field(default_factory=list)
    standalone_fields: List[UIField] = Field(default_factory=list)
    standalone_buttons: List[UIButton] = Field(default_factory=list)
    raw_snippet: Optional[str] = None


class JSXASTVisitor:
    """Enterprise parser for extracting Persian UX controls from JSX/TSX/Vue."""

    BUTTON_TAGS = {"button", "Button", "IconButton", "SubmitButton", "ActionButton", "LoadingButton"}
    INPUT_TAGS = {"input", "Input", "TextField", "TextInput", "FormItem", "CustomInput"}
    SELECT_TAGS = {"select", "Select", "Dropdown", "MultiSelect", "Autocomplete", "Combobox"}
    TEXTAREA_TAGS = {"textarea", "TextArea", "Textarea"}
    LABEL_TAGS = {"label", "Label", "FormLabel", "InputLabel"}

    SUBMIT_KEYWORDS = ["ثبت", "ارسال", "ذخیره", "تایید", "ایجاد", "افزودن", "submit", "save", "confirm", "create"]

    def __init__(self, normalizer: Optional[PersianNormalizer] = None):
        self.normalizer = normalizer or default_normalizer
        self.parser = None
        if _has_tree_sitter:
            try:
                self.parser = tree_sitter_languages.get_parser("tsx")
            except Exception:
                self.parser = None

    def parse_source(self, code: str, file_path: str = "") -> ComponentInspection:
        """Parses source code into structured UX models."""
        if not code.strip():
            return ComponentInspection(file_path=file_path)

        if self.parser:
            try:
                return self._parse_with_tree_sitter(code, file_path)
            except Exception:
                return self._parse_with_fallback(code, file_path)
        else:
            return self._parse_with_fallback(code, file_path)

    def _parse_with_tree_sitter(self, code: str, file_path: str) -> ComponentInspection:
        """Tree-sitter based AST traversal."""
        tree = self.parser.parse(bytes(code, "utf-8"))
        root = tree.root_node

        fields: List[UIField] = []
        buttons: List[UIButton] = []

        def traverse(node):
            if node.type in ("jsx_element", "jsx_self_closing_element"):
                opening = node if node.type == "jsx_self_closing_element" else node.child_by_field_name("open_tag")
                tag_node = opening.child_by_field_name("name") if opening else None
                tag_name = tag_node.text.decode("utf-8") if tag_node else ""

                # Extract attributes
                props = self._extract_node_props(opening or node)
                line_num = node.start_point[0] + 1

                # Check element type
                if tag_name in self.BUTTON_TAGS:
                    # Inner text
                    inner_text = self._extract_inner_text(node) or props.get("children", "") or props.get("title", "")
                    normalized_label = self.normalizer.normalize(inner_text)
                    is_sub = (
                        props.get("type") == "submit"
                        or any(k in normalized_label.lower() for k in self.SUBMIT_KEYWORDS)
                    )
                    buttons.append(
                        UIButton(
                            label=normalized_label or tag_name,
                            name=props.get("name") or props.get("id"),
                            action_type=props.get("type", "button"),
                            disabled=props.get("disabled", False) is True or "disabled" in props,
                            is_submit=is_sub,
                            line_number=line_num
                        )
                    )
                elif tag_name in self.INPUT_TAGS or tag_name in self.TEXTAREA_TAGS:
                    req = props.get("required", False) is True or "required" in props
                    fields.append(
                        UIField(
                            name=props.get("name") or props.get("id") or "",
                            field_type="textarea" if tag_name in self.TEXTAREA_TAGS else props.get("type", "text"),
                            label=props.get("label"),
                            placeholder=props.get("placeholder"),
                            required=req,
                            disabled=props.get("disabled", False) is True or "disabled" in props,
                            validation_message=props.get("helperText") or props.get("errorMessage"),
                            line_number=line_num
                        )
                    )
                elif tag_name in self.SELECT_TAGS:
                    req = props.get("required", False) is True or "required" in props
                    fields.append(
                        UIField(
                            name=props.get("name") or props.get("id") or "",
                            field_type="select",
                            label=props.get("label"),
                            placeholder=props.get("placeholder"),
                            required=req,
                            disabled=props.get("disabled", False) is True or "disabled" in props,
                            line_number=line_num
                        )
                    )

            for child in node.children:
                traverse(child)

        traverse(root)

        # Build form container
        form = DiscoveredForm(
            form_name=self._guess_component_name(code, file_path),
            file_path=file_path,
            fields=fields,
            buttons=buttons,
            start_line=1,
            end_line=len(code.splitlines())
        )

        return ComponentInspection(
            file_path=file_path,
            component_name=form.form_name,
            forms=[form] if (fields or buttons) else [],
            standalone_fields=fields,
            standalone_buttons=buttons,
            raw_snippet=code[:1000]
        )

    def _extract_node_props(self, node) -> Dict[str, Any]:
        """Extracts attributes from JSX AST node."""
        props = {}
        for child in node.children:
            if child.type == "jsx_attribute":
                prop_name_node = child.child_by_field_name("name")
                prop_val_node = child.child_by_field_name("value")
                if prop_name_node:
                    pname = prop_name_node.text.decode("utf-8")
                    pval = True
                    if prop_val_node:
                        val_text = prop_val_node.text.decode("utf-8")
                        pval = val_text.strip("\"'")
                    props[pname] = pval
        return props

    def _extract_inner_text(self, node) -> str:
        """Extracts text content inside JSX tags."""
        text_parts = []
        for child in node.children:
            if child.type == "jsx_text":
                text_parts.append(child.text.decode("utf-8").strip())
        return " ".join(filter(None, text_parts))

    def _parse_with_fallback(self, code: str, file_path: str) -> ComponentInspection:
        """High-precision regex/lexical AST scanner for JSX/TSX."""
        lines = code.splitlines()
        fields: List[UIField] = []
        buttons: List[UIButton] = []

        # Tag regex for buttons
        # e.g., <button ...>...</button> or <Button ...>...</Button>
        btn_pattern = re.compile(
            r'<(?P<tag>button|Button|IconButton|SubmitButton|ActionButton)\b(?P<attrs>[^>]*)>(?P<content>.*?)</(?P=tag)>',
            re.IGNORECASE | re.DOTALL
        )
        # Self closing buttons
        btn_self_pattern = re.compile(
            r'<(?P<tag>button|Button|IconButton|SubmitButton|ActionButton)\b(?P<attrs>[^>]*?)(?:/>|>)',
            re.IGNORECASE
        )

        # Input regex
        input_pattern = re.compile(
            r'<(?P<tag>input|Input|TextField|FormItem|textarea|TextArea|select|Select|Dropdown)\b(?P<attrs>[^>]*?)(?:/>|>)',
            re.IGNORECASE
        )

        # Helper to extract attributes dictionary
        def parse_attrs(attr_str: str) -> Dict[str, Any]:
            attrs = {}
            # Match name="value" or name={'value'} or boolean name
            attr_matches = re.finditer(
                r'(?P<key>[\w\-\.\:]+)(?:\s*=\s*(?:["\'](?P<str_val>[^"\']*)["\']|\{(?P<expr_val>[^}]*)\}))?',
                attr_str
            )
            for m in attr_matches:
                k = m.group("key")
                s_val = m.group("str_val")
                e_val = m.group("expr_val")
                if s_val is not None:
                    attrs[k] = s_val
                elif e_val is not None:
                    attrs[k] = e_val.strip()
                else:
                    attrs[k] = True
            return attrs

        # Find line number helper
        def get_line_number(pos: int) -> int:
            return code[:pos].count('\n') + 1

        # Match regular buttons with children
        for m in btn_pattern.finditer(code):
            attrs = parse_attrs(m.group("attrs"))
            raw_content = m.group("content")
            # Strip nested JSX tags from text
            clean_text = re.sub(r'<[^>]+>', '', raw_content).strip()
            if not clean_text:
                clean_text = str(attrs.get("title") or attrs.get("label") or attrs.get("aria-label") or "")

            label = self.normalizer.normalize(clean_text)
            action_type = str(attrs.get("type", "button")).lower()
            is_sub = (
                action_type == "submit"
                or any(k in label.lower() for k in self.SUBMIT_KEYWORDS)
                or "submit" in str(attrs.get("onClick", "")).lower()
            )
            dis = (
                attrs.get("disabled") is True
                or str(attrs.get("disabled", "")).lower() == "true"
                or "disabled" in attrs
            )

            buttons.append(
                UIButton(
                    label=label or m.group("tag"),
                    name=str(attrs.get("name") or attrs.get("id") or ""),
                    action_type=action_type,
                    disabled=dis,
                    is_submit=is_sub,
                    line_number=get_line_number(m.start())
                )
            )

        # Match inputs and selects
        for m in input_pattern.finditer(code):
            tag = m.group("tag").lower()
            attrs = parse_attrs(m.group("attrs"))

            # Determine field type
            if "select" in tag or "dropdown" in tag:
                ftype = "select"
            elif "textarea" in tag:
                ftype = "textarea"
            else:
                ftype = str(attrs.get("type", "text"))

            req = (
                attrs.get("required") is True
                or str(attrs.get("required", "")).lower() == "true"
                or "required" in attrs
                or "rules" in attrs and "required" in str(attrs["rules"])
            )
            dis = (
                attrs.get("disabled") is True
                or str(attrs.get("disabled", "")).lower() == "true"
                or "disabled" in attrs
            )

            lbl = attrs.get("label") or attrs.get("title")
            if lbl:
                lbl = self.normalizer.normalize(str(lbl))

            placeholder = attrs.get("placeholder")
            if placeholder:
                placeholder = self.normalizer.normalize(str(placeholder))

            val_msg = attrs.get("helperText") or attrs.get("errorMessage")
            if val_msg:
                val_msg = self.normalizer.normalize(str(val_msg))

            fields.append(
                UIField(
                    name=str(attrs.get("name") or attrs.get("id") or ""),
                    field_type=ftype,
                    label=lbl,
                    placeholder=placeholder,
                    required=req,
                    disabled=dis,
                    validation_message=val_msg,
                    line_number=get_line_number(m.start())
                )
            )

        comp_name = self._guess_component_name(code, file_path)

        form = DiscoveredForm(
            form_name=comp_name,
            file_path=file_path,
            fields=fields,
            buttons=buttons,
            start_line=1,
            end_line=len(lines)
        )

        return ComponentInspection(
            file_path=file_path,
            component_name=comp_name,
            forms=[form] if (fields or buttons) else [],
            standalone_fields=fields,
            standalone_buttons=buttons,
            raw_snippet=code[:1000]
        )

    def _guess_component_name(self, code: str, file_path: str) -> str:
        """Infers component name from export default or filename."""
        m = re.search(r'export\s+default\s+function\s+([A-Za-z0-9_]+)', code)
        if m:
            return m.group(1)
        m = re.search(r'export\s+(?:default\s+)?(?:const|let)\s+([A-Za-z0-9_]+)\s*=', code)
        if m:
            return m.group(1)
        if file_path:
            import os
            base = os.path.basename(file_path)
            return os.path.splitext(base)[0]
        return "UnknownComponent"
