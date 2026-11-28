from __future__ import annotations

import copy
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

_OBJ_INFO_CACHE: Dict[str, Any] = {"ts": 0.0, "url": "", "data": None}
_WF_LIST_CACHE: Dict[str, Any] = {"ts": 0.0, "url": "", "data": None}

_WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3"}
_CONTROL_AFTER_GEN = {"randomize", "fixed", "increment", "decrement"}
_SKIP_NODE_TYPES = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
_QUANT_NOISE_TOKENS = {
    "safetensors", "ckpt", "pt", "pth", "gguf", "bin",
    "fp16", "bf16", "fp32", "fp8", "e4m3fn", "e5m2", "int8", "int4", "fp4", "nvfp4",
    "awq", "gptq", "convrot", "scaled", "mixed", "pruned", "comfy", "comfyui", "emaonly",
    "fast", "default", "v1", "v10", "1", "0",
}

_VIDEO_NODE_HINTS = (
    "savevideo",
    "createvideo",
    "vhs_videocombine",
    "minimaxh3",
    "ltxv",
    "wan",
    "hunyuanvideo",
    "cogvideo",
    "mochi",
    "animatediff",
)
_IMAGE_NODE_HINTS = (
    "saveimage",
    "previewimage",
    "emptylatentimage",
    "emptysd3latentimage",
    "checkpointloadersimple",
    "ksampler",
    "cliptextencode",
)


async def get_comfy_object_info(
    base_url: str,
    force: bool = False,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    url = base_url.strip().rstrip("/")
    now = time.monotonic()
    if (
        not force
        and _OBJ_INFO_CACHE["data"] is not None
        and _OBJ_INFO_CACHE["url"] == url
        and (now - _OBJ_INFO_CACHE["ts"]) < 60.0
    ):
        return _OBJ_INFO_CACHE["data"]
    async with httpx.AsyncClient(timeout=timeout, headers=headers or {}) as client:
        r = await client.get(f"{url}/object_info")
        r.raise_for_status()
        data = r.json()
    _OBJ_INFO_CACHE.update({"ts": now, "url": url, "data": data})
    return data


def _classify_workflow_nodes(raw_wf: Dict[str, Any]) -> Tuple[str, int, List[str]]:
    """Infer kind ('video' | 'image' | 'other'), node count, and key node types."""
    types: List[str] = []
    if isinstance(raw_wf.get("nodes"), list):
        for n in raw_wf["nodes"]:
            if isinstance(n, dict) and n.get("type"):
                types.append(str(n["type"]))
        for sg in (raw_wf.get("definitions") or {}).get("subgraphs") or []:
            for n in sg.get("nodes") or []:
                if isinstance(n, dict) and n.get("type"):
                    types.append(str(n["type"]))
    else:
        for _nid, n in raw_wf.items():
            if isinstance(n, dict) and n.get("class_type"):
                types.append(str(n["class_type"]))

    low_all = " ".join(t.lower() for t in types)
    kind = "other"
    if any(h in low_all for h in _VIDEO_NODE_HINTS):
        kind = "video"
    elif any(h in low_all for h in _IMAGE_NODE_HINTS):
        kind = "image"
    return kind, len(types), types[:8]


def _find_comfy_base_dir(sys_stats: Dict[str, Any]) -> Optional[Path]:
    argv = (sys_stats.get("system") or {}).get("argv") or []
    for i, a in enumerate(argv):
        if a == "--base-directory" and i + 1 < len(argv):
            p = Path(argv[i + 1])
            if p.exists():
                return p
    for cand in (Path("C:/ComfyUI"), Path("D:/ComfyUI")):
        if cand.exists():
            return cand
    return None


async def list_comfyui_workflows(
    base_url: str,
    installed_files: Optional[Set[str]] = None,
    force: bool = False,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 12.0,
) -> List[Dict[str, Any]]:
    """Auto-discover user-saved workflows, custom-node workflows, and installed ComfyUI templates."""
    url = base_url.strip().rstrip("/")
    now = time.monotonic()
    if (
        not force
        and _WF_LIST_CACHE["data"] is not None
        and _WF_LIST_CACHE["url"] == url
        and (now - _WF_LIST_CACHE["ts"]) < 20.0
    ):
        return _WF_LIST_CACHE["data"]

    workflows: List[Dict[str, Any]] = []
    installed_low = {f.lower().replace("\\", "/").split("/")[-1] for f in (installed_files or set())}

    async with httpx.AsyncClient(timeout=timeout, headers=headers or {}) as client:
        # 1. User-saved workflows via /api/v2/userdata?path=workflows (recursive)
        async def _scan_userdata(rel_path: str) -> None:
            try:
                r = await client.get(f"{url}/api/v2/userdata", params={"path": rel_path})
                if r.status_code != 200:
                    return
                entries = r.json()
                if not isinstance(entries, list):
                    return
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    etype = entry.get("type")
                    epath = str(entry.get("path") or "")
                    ename = str(entry.get("name") or "")
                    if etype == "directory" and epath:
                        await _scan_userdata(epath)
                    elif etype == "file" and ename.lower().endswith(".json"):
                        wf_kind = "image"
                        node_count = 0
                        try:
                            encoded = urllib.parse.quote(epath, safe="")
                            wr = await client.get(f"{url}/api/userdata/{encoded}")
                            if wr.status_code == 200:
                                wf_kind, node_count, _ = _classify_workflow_nodes(wr.json())
                        except Exception:
                            pass
                        display = epath.removeprefix("workflows/").removesuffix(".json")
                        workflows.append({
                            "id": f"user:{epath}",
                            "name": display,
                            "title": display,
                            "source": "user",
                            "source_label": "我的 ComfyUI 工作流",
                            "kind": wf_kind if wf_kind != "other" else "image",
                            "node_count": node_count,
                            "models_ready": True,
                            "description": f"來自 ComfyUI 使用者目錄 ({epath})",
                            "modified": entry.get("modified", 0),
                        })
            except Exception:
                pass

        await _scan_userdata("workflows")

        # Fallback to v1 /api/userdata?dir=workflows if v2 returned nothing
        if not workflows:
            try:
                r = await client.get(f"{url}/api/userdata", params={"dir": "workflows"})
                if r.status_code == 200 and isinstance(r.json(), list):
                    for fn in r.json():
                        if isinstance(fn, str) and fn.lower().endswith(".json"):
                            epath = f"workflows/{fn}"
                            workflows.append({
                                "id": f"user:{epath}",
                                "name": fn.removesuffix(".json"),
                                "title": fn.removesuffix(".json"),
                                "source": "user",
                                "source_label": "我的 ComfyUI 工作流",
                                "kind": "image",
                                "node_count": 0,
                                "models_ready": True,
                                "description": f"來自 ComfyUI 使用者目錄 ({epath})",
                                "modified": 0,
                            })
            except Exception:
                pass

        # 2. Custom-node installed example workflows (/api/workflow_templates)
        try:
            rt = await client.get(f"{url}/api/workflow_templates")
            if rt.status_code == 200 and isinstance(rt.json(), dict):
                for pkg, names in rt.json().items():
                    if not isinstance(names, list):
                        continue
                    for wname in names:
                        low = str(wname).lower()
                        kind = "video" if any(k in low for k in ("video", "vid", "ltx", "wan", "minimax")) else "image"
                        workflows.append({
                            "id": f"ext:{pkg}/{wname}",
                            "name": str(wname),
                            "title": f"[{pkg}] {wname}",
                            "source": "extension",
                            "source_label": f"擴充節點 ({pkg})",
                            "kind": kind,
                            "node_count": 0,
                            "models_ready": True,
                            "description": f"ComfyUI 已安裝擴充套件 {pkg} 內建工作流",
                            "modified": 0,
                        })
        except Exception:
            pass

        # 3. Official ComfyUI installed templates (/templates/index.json)
        try:
            ri = await client.get(f"{url}/templates/index.json")
            if ri.status_code == 200 and isinstance(ri.json(), list):
                ready_tpls: List[Dict[str, Any]] = []
                other_tpls: List[Dict[str, Any]] = []
                for cat in ri.json():
                    cat_title = str(cat.get("title") or "")
                    cat_low = cat_title.lower()
                    if "video" in cat_low:
                        cat_kind = "video"
                    elif "image" in cat_low:
                        cat_kind = "image"
                    else:
                        continue
                    for tpl in cat.get("templates") or []:
                        tname = str(tpl.get("name") or "")
                        if not tname or tname.startswith("api_"):
                            # Skip paid cloud API-only Comfy templates
                            continue
                        title = str(tpl.get("title") or tname)
                        desc = str(tpl.get("description") or "")
                        # Check whether template matches user's locally installed models
                        tlow = (tname + " " + title + " " + " ".join(tpl.get("models") or [])).lower()
                        is_ready = False
                        if any(
                            k in tlow
                            for k in ("z_image_turbo", "z-image-turbo", "ltx2_5", "ltx-2.5", "minimax_h3", "minimax h3")
                        ):
                            is_ready = True
                        elif "sdxl" in tlow and any("sd_xl" in f or "sdxl" in f for f in installed_low):
                            is_ready = True
                        elif "sd3.5" in tlow and any("sd3.5" in f for f in installed_low):
                            is_ready = True
                        elif ("sd1.5" in tlow or "default" == tname) and any("v1-5" in f or "chillout" in f for f in installed_low):
                            is_ready = True

                        entry = {
                            "id": f"template:{tname}",
                            "name": tname,
                            "title": title,
                            "source": "template",
                            "source_label": f"ComfyUI 官方範本 · {cat_title}",
                            "kind": cat_kind,
                            "node_count": 0,
                            "models_ready": is_ready,
                            "description": desc[:140] if desc else f"ComfyUI 內建範本 ({tname}.json)",
                            "modified": 0,
                        }
                        if is_ready:
                            ready_tpls.append(entry)
                        else:
                            other_tpls.append(entry)

                # Put model-ready templates first, followed by a clean subset of other popular templates
                workflows.extend(ready_tpls)
                workflows.extend(other_tpls[:40])
        except Exception:
            pass

    _WF_LIST_CACHE.update({"ts": now, "url": url, "data": workflows})
    return workflows


async def fetch_comfyui_workflow_raw(
    base_url: str,
    workflow_id: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 20.0,
) -> Tuple[Dict[str, Any], str]:
    """Fetch the raw JSON dict and display name for an auto-loaded ComfyUI workflow."""
    url = base_url.strip().rstrip("/")
    async with httpx.AsyncClient(timeout=timeout, headers=headers or {}) as client:
        if workflow_id.startswith("user:"):
            epath = workflow_id[5:]
            encoded = urllib.parse.quote(epath, safe="")
            r = await client.get(f"{url}/api/userdata/{encoded}")
            r.raise_for_status()
            return r.json(), epath.removeprefix("workflows/").removesuffix(".json")

        if workflow_id.startswith("template:"):
            tname = workflow_id[9:]
            r = await client.get(f"{url}/templates/{tname}.json")
            r.raise_for_status()
            return r.json(), tname

        if workflow_id.startswith("ext:"):
            rest = workflow_id[4:]
            pkg, _, wname = rest.partition("/")
            # Try ComfyUI HTTP endpoints first
            for ep in (
                f"{url}/extensions/{pkg}/example_workflows/{wname}.json",
                f"{url}/api/workflow_templates/{pkg}/{wname}.json",
            ):
                try:
                    r = await client.get(ep)
                    if r.status_code == 200:
                        return r.json(), f"{pkg}/{wname}"
                except Exception:
                    pass
            # Fallback to ComfyUI custom_nodes folder on disk
            try:
                sr = await client.get(f"{url}/system_stats")
                base_dir = _find_comfy_base_dir(sr.json() if sr.status_code == 200 else {})
                if base_dir:
                    for cand in (
                        base_dir / "custom_nodes" / pkg / "example_workflows" / f"{wname}.json",
                        base_dir / "custom_nodes" / pkg / "workflows" / f"{wname}.json",
                    ):
                        if cand.exists():
                            return json.loads(cand.read_text(encoding="utf-8")), f"{pkg}/{wname}"
            except Exception:
                pass
            raise FileNotFoundError(f"找不到擴充套件工作流：{pkg}/{wname}")

    raise ValueError(f"無效的 ComfyUI 工作流 ID：{workflow_id}")


def _is_widget_spec(spec: Any) -> bool:
    if not isinstance(spec, list) or not spec:
        return False
    first = spec[0]
    if isinstance(first, list):
        return True
    return str(first) in _WIDGET_TYPES


def _ordered_widget_inputs(node_schema: Dict[str, Any]) -> List[Tuple[str, Any]]:
    inp = node_schema.get("input") or {}
    ordered: List[Tuple[str, Any]] = []
    for section in ("required", "optional"):
        sec_dict = inp.get(section) or {}
        if isinstance(sec_dict, dict):
            for k, v in sec_dict.items():
                if _is_widget_spec(v):
                    ordered.append((k, v))
    return ordered


def _expand_subgraphs(raw_wf: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten ComfyUI v0.46+ definitions.subgraphs into a single flat LiteGraph node/link graph."""
    subgraphs_list = (raw_wf.get("definitions") or {}).get("subgraphs") or []
    if not subgraphs_list:
        return raw_wf

    sg_map = {str(sg.get("id")): sg for sg in subgraphs_list if isinstance(sg, dict) and sg.get("id")}
    if not sg_map:
        return raw_wf

    flat = copy.deepcopy(raw_wf)
    nodes = list(flat.get("nodes") or [])
    links = list(flat.get("links") or [])

    max_nid = max([int(n.get("id", 0)) for n in nodes if str(n.get("id", "")).isdigit()] + [1000])
    max_lid = max([int(l[0]) for l in links if isinstance(l, list) and l] + [10000])

    # Build quick link lookup by link_id
    link_by_id: Dict[int, List[Any]] = {int(l[0]): l for l in links if isinstance(l, list) and len(l) >= 6}

    new_nodes: List[Dict[str, Any]] = []
    removed_sg_ids: Set[int] = set()

    for node in nodes:
        ntype = str(node.get("type", ""))
        if ntype not in sg_map:
            new_nodes.append(node)
            continue

        sg = sg_map[ntype]
        outer_id = int(node["id"])
        removed_sg_ids.add(outer_id)

        # Map subgraph inner node IDs -> fresh unique outer node IDs
        inner_nodes = copy.deepcopy(sg.get("nodes") or [])
        id_remap: Dict[int, int] = {}
        for in_node in inner_nodes:
            max_nid += 1
            id_remap[int(in_node["id"])] = max_nid
            in_node["id"] = max_nid

        # Subgraph inputNode (-10) and outputNode (-20)
        sg_in_id = int((sg.get("inputNode") or {}).get("id", -10))
        sg_out_id = int((sg.get("outputNode") or {}).get("id", -20))

        # Subgraph input definitions (indexed by oslot) & outer links mapped by input NAME (not raw slot index!)
        sg_inputs = sg.get("inputs") or []
        outer_in_by_name: Dict[str, Tuple[int, int, str]] = {}
        for inp_def in node.get("inputs") or []:
            iname = str(inp_def.get("name") or "")
            lid = inp_def.get("link")
            if iname and lid is not None and int(lid) in link_by_id:
                ol = link_by_id[int(lid)]
                outer_in_by_name[iname] = (int(ol[1]), int(ol[2]), str(ol[5]))

        # Outer links leaving this subgraph instance by output slot index
        outer_out_by_slot: Dict[int, List[List[Any]]] = {}
        for ol in links:
            if isinstance(ol, list) and len(ol) >= 6 and int(ol[1]) == outer_id:
                outer_out_by_slot.setdefault(int(ol[2]), []).append(ol)

        # Subgraph inner links (may be dict objects or list tuples)
        sg_links_raw = sg.get("links") or []
        inner_link_remap: Dict[int, int] = {}
        for sl in sg_links_raw:
            if isinstance(sl, dict):
                old_lid = int(sl["id"])
                oid = int(sl["origin_id"])
                oslot = int(sl["origin_slot"])
                tid = int(sl["target_id"])
                tslot = int(sl["target_slot"])
                ltype = str(sl.get("type", "*"))
            elif isinstance(sl, list) and len(sl) >= 6:
                old_lid, oid, oslot, tid, tslot, ltype = int(sl[0]), int(sl[1]), int(sl[2]), int(sl[3]), int(sl[4]), str(sl[5])
            else:
                continue

            if oid == sg_in_id:
                # Match outer linked socket by subgraph input NAME (outer node omits unexposed widget sockets!)
                sg_inp_name = str(sg_inputs[oslot].get("name", "")) if 0 <= oslot < len(sg_inputs) else ""
                if sg_inp_name and sg_inp_name in outer_in_by_name and tid in id_remap:
                    src_nid, src_slot, src_type = outer_in_by_name[sg_inp_name]
                    max_lid += 1
                    new_link = [max_lid, src_nid, src_slot, id_remap[tid], tslot, src_type or ltype]
                    links.append(new_link)
                    link_by_id[max_lid] = new_link
                    inner_link_remap[old_lid] = max_lid
                # If not externally linked, leave inner input unlinked so inner node uses its widget value!
            elif tid == sg_out_id:
                # Rewire outer downstream consumers of outer_id:tslot to inner producer
                if oid in id_remap:
                    for ol in outer_out_by_slot.get(tslot, []):
                        ol[1] = id_remap[oid]
                        ol[2] = oslot
            elif oid in id_remap and tid in id_remap:
                max_lid += 1
                new_link = [max_lid, id_remap[oid], oslot, id_remap[tid], tslot, ltype]
                links.append(new_link)
                link_by_id[max_lid] = new_link
                inner_link_remap[old_lid] = max_lid

        # Remap link references stored inside inner nodes' inputs
        for in_node in inner_nodes:
            for inp_def in in_node.get("inputs") or []:
                old_l = inp_def.get("link")
                if old_l is not None:
                    inp_def["link"] = inner_link_remap.get(int(old_l))
            new_nodes.append(in_node)

    # Prune links still pointing to removed subgraph wrapper nodes
    clean_links = [
        l for l in links
        if isinstance(l, list) and len(l) >= 6 and int(l[1]) not in removed_sg_ids and int(l[3]) not in removed_sg_ids
    ]
    flat["nodes"] = new_nodes
    flat["links"] = clean_links
    return flat


def convert_ui_workflow_to_api(raw_wf: Dict[str, Any], object_info: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a ComfyUI LiteGraph UI workflow JSON into an executable ComfyUI API prompt dict."""
    # Already API format?
    if not isinstance(raw_wf.get("nodes"), list):
        return copy.deepcopy(raw_wf)

    wf = _expand_subgraphs(raw_wf)
    nodes = wf.get("nodes") or []
    links = wf.get("links") or []

    node_by_id: Dict[int, Dict[str, Any]] = {int(n["id"]): n for n in nodes if isinstance(n, dict) and "id" in n}
    link_by_id: Dict[int, List[Any]] = {int(l[0]): l for l in links if isinstance(l, list) and len(l) >= 6}

    def resolve_source(link_id: int, depth: int = 0) -> Optional[Tuple[int, int]]:
        if depth > 16 or link_id not in link_by_id:
            return None
        lnk = link_by_id[link_id]
        src_id, src_slot = int(lnk[1]), int(lnk[2])
        src_node = node_by_id.get(src_id)
        if not src_node:
            return None
        stype = str(src_node.get("type", ""))
        mode = int(src_node.get("mode", 0))
        if stype == "Reroute":
            inps = src_node.get("inputs") or []
            if inps and inps[0].get("link") is not None:
                return resolve_source(int(inps[0]["link"]), depth + 1)
            return None
        if mode == 4:  # Bypassed node -> pass through first matching-type linked input
            out_type = str(lnk[5])
            for inp_def in src_node.get("inputs") or []:
                if inp_def.get("link") is not None and (str(inp_def.get("type")) == out_type or out_type == "*"):
                    return resolve_source(int(inp_def["link"]), depth + 1)
            return None
        if mode == 2:  # Muted
            return None
        return src_id, src_slot

    api_prompt: Dict[str, Any] = {}

    for node in nodes:
        if not isinstance(node, dict) or "id" not in node:
            continue
        nid = int(node["id"])
        ctype = str(node.get("type", ""))
        mode = int(node.get("mode", 0))
        if mode in (2, 4) or ctype in _SKIP_NODE_TYPES:
            continue
        schema = object_info.get(ctype)
        if not schema:
            # Skip purely decorative / unknown UI nodes gracefully
            continue

        inputs_out: Dict[str, Any] = {}
        linked_input_names: Set[str] = set()

        # 1. Wire linked inputs (also resolving PrimitiveNode values directly)
        for inp_def in node.get("inputs") or []:
            iname = str(inp_def.get("name") or "")
            lid = inp_def.get("link")
            if lid is None:
                continue
            resolved = resolve_source(int(lid))
            if not resolved:
                continue
            src_id, src_slot = resolved
            src_node = node_by_id.get(src_id)
            if src_node and str(src_node.get("type")) == "PrimitiveNode":
                wvals = src_node.get("widgets_values")
                if isinstance(wvals, list) and wvals:
                    inputs_out[iname] = wvals[0]
                    linked_input_names.add(iname)
                continue
            inputs_out[iname] = [str(src_id), int(src_slot)]
            linked_input_names.add(iname)

        # 2. Populate widget inputs from widgets_values
        wvals = node.get("widgets_values")
        ordered_widgets = _ordered_widget_inputs(schema)

        if isinstance(wvals, dict):
            for wname, _spec in ordered_widgets:
                if wname not in linked_input_names and wname in wvals:
                    inputs_out[wname] = wvals[wname]
        elif isinstance(wvals, list):
            w_idx = 0

            def _consume_widgets(widget_list: List[Tuple[str, Any]], prefix: str = "") -> None:
                nonlocal w_idx
                for wname, spec in widget_list:
                    if w_idx >= len(wvals):
                        break
                    full_name = f"{prefix}.{wname}" if prefix else wname
                    val = wvals[w_idx]
                    w_idx += 1

                    # Advance past ComfyUI's virtual 'control_after_generate' widget value after seed/noise_seed
                    if wname in ("seed", "noise_seed") or (
                        isinstance(spec, list)
                        and len(spec) > 1
                        and isinstance(spec[1], dict)
                        and spec[1].get("control_after_generate")
                    ):
                        if w_idx < len(wvals) and str(wvals[w_idx]).lower() in _CONTROL_AFTER_GEN:
                            w_idx += 1

                    first = spec[0] if isinstance(spec, list) and spec else ""
                    if full_name not in linked_input_names:
                        if first == "INT" and isinstance(val, (int, float)):
                            val = int(val)
                        elif first == "FLOAT" and isinstance(val, (int, float)):
                            val = float(val)
                        inputs_out[full_name] = val

                    # ComfyUI V3 DynamicCombo stores selected option's sub-widgets immediately after the selector value
                    if first == "COMFY_DYNAMICCOMBO_V3" and len(spec) > 1 and isinstance(spec[1], dict):
                        options = spec[1].get("options") or []
                        matched_opt = next((o for o in options if isinstance(o, dict) and o.get("key") == val), None)
                        if matched_opt and isinstance(matched_opt.get("inputs"), dict):
                            sub_widgets = _ordered_widget_inputs({"input": matched_opt["inputs"]})
                            if sub_widgets:
                                _consume_widgets(sub_widgets, prefix=full_name)

            _consume_widgets(ordered_widgets)

        api_prompt[str(nid)] = {
            "class_type": ctype,
            "inputs": inputs_out,
        }

    # Prune dangling links referencing nodes that were skipped/muted
    valid_ids = set(api_prompt.keys())
    for node_obj in api_prompt.values():
        inp = node_obj["inputs"]
        for k in list(inp.keys()):
            v = inp[k]
            if isinstance(v, list) and len(v) == 2 and str(v[0]) not in valid_ids:
                del inp[k]

    # Prune orphan/disconnected nodes not reachable backwards from any output node (e.g. unused optional last_frame branches)
    output_ids = [
        nid
        for nid, n in api_prompt.items()
        if bool((object_info.get(n["class_type"]) or {}).get("output_node"))
    ]
    if output_ids:
        reachable: Set[str] = set()
        stack = list(output_ids)
        while stack:
            cur = stack.pop()
            if cur in reachable or cur not in api_prompt:
                continue
            reachable.add(cur)
            for v in (api_prompt[cur].get("inputs") or {}).values():
                if isinstance(v, list) and len(v) == 2:
                    src_id = str(v[0])
                    if src_id in api_prompt and src_id not in reachable:
                        stack.append(src_id)
        api_prompt = {nid: n for nid, n in api_prompt.items() if nid in reachable}

    return api_prompt


def inject_workflow_params(
    api_wf: Dict[str, Any],
    prompt: str = "",
    neg_prompt: str = "",
    width: Optional[int] = None,
    height: Optional[int] = None,
    batch_size: Optional[int] = None,
    steps: Optional[int] = None,
    seed: Optional[int] = None,
    first_frame_name: Optional[str] = None,
    last_frame_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Graph-aware injection of prompt, negative prompt, size, seed, steps & input images."""
    wf = copy.deepcopy(api_wf)

    # 1. Explicit placeholder substitution if user used {{PROMPT}} etc.
    serialized = json.dumps(wf, ensure_ascii=False)
    had_placeholder = False
    for token, val in (
        ("{{PROMPT}}", prompt),
        ("{{NEGATIVE_PROMPT}}", neg_prompt),
        ("{{FIRST_FRAME}}", first_frame_name or ""),
        ("{{LAST_FRAME}}", last_frame_name or ""),
    ):
        if token in serialized:
            had_placeholder = True
            serialized = serialized.replace(token, val.replace('"', '\\"'))
    wf = json.loads(serialized)

    # Trace which text-encoder / primitive nodes feed positive vs negative slots on samplers/guiders
    pos_nodes: Set[str] = set()
    neg_nodes: Set[str] = set()

    def _trace_text_sources(start_nid: str, bucket: Set[str], depth: int = 0) -> None:
        if depth > 6 or start_nid not in wf:
            return
        node = wf[start_nid]
        ctype = str(node.get("class_type", ""))
        inputs = node.get("inputs") or {}
        if ctype in ("CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeSDXLRefiner", "MiniMaxH3ImageToVideo", "PrimitiveString"):
            bucket.add(start_nid)
            # Also follow linked `text` / `text_g` / `text_l` inputs (e.g. PrimitiveString -> CLIPTextEncodeSDXL)
            for tk in ("text", "text_g", "text_l", "prompt"):
                tv = inputs.get(tk)
                if isinstance(tv, list) and len(tv) == 2:
                    _trace_text_sources(str(tv[0]), bucket, depth + 1)
            return
        for k in ("conditioning", "positive", "negative", "conditioning_1", "conditioning_2"):
            v = inputs.get(k)
            if isinstance(v, list) and len(v) == 2:
                _trace_text_sources(str(v[0]), bucket, depth + 1)

    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if isinstance(inputs.get("positive"), list) and len(inputs["positive"]) == 2:
            _trace_text_sources(str(inputs["positive"][0]), pos_nodes)
        if isinstance(inputs.get("negative"), list) and len(inputs["negative"]) == 2:
            _trace_text_sources(str(inputs["negative"][0]), neg_nodes)

    if not had_placeholder:
        # Inject positive & negative prompts smartly
        injected_pos = False
        for nid in pos_nodes:
            node = wf[nid]
            inputs = node.get("inputs") or {}
            ctype = str(node.get("class_type", ""))
            if ctype == "PrimitiveString" and isinstance(inputs.get("value"), str) and prompt:
                inputs["value"] = prompt
                injected_pos = True
            for tk in ("text", "text_g", "text_l", "prompt"):
                if tk in inputs and isinstance(inputs[tk], str) and prompt:
                    inputs[tk] = prompt
                    injected_pos = True

        if neg_prompt:
            for nid in neg_nodes - pos_nodes:
                node = wf[nid]
                inputs = node.get("inputs") or {}
                ctype = str(node.get("class_type", ""))
                if ctype == "PrimitiveString" and isinstance(inputs.get("value"), str):
                    inputs["value"] = neg_prompt
                for tk in ("text", "text_g", "text_l"):
                    if tk in inputs and isinstance(inputs[tk], str):
                        inputs[tk] = neg_prompt

        # Fallback if graph had no standard KSampler positive wiring (e.g., MiniMaxH3ImageToVideo)
        if not injected_pos and prompt:
            for nid, node in wf.items():
                if not isinstance(node, dict):
                    continue
                ctype = str(node.get("class_type", ""))
                inputs = node.get("inputs") or {}
                if ctype in ("MiniMaxH3ImageToVideo", "CLIPTextEncode", "CLIPTextEncodeSDXL"):
                    for tk in ("prompt", "text", "text_g", "text_l"):
                        if tk in inputs and isinstance(inputs[tk], str):
                            inputs[tk] = prompt
                            injected_pos = True
                    if injected_pos:
                        break

    # Inject seed, steps, dimensions, batch_size, and LoadImage frames
    load_img_nodes: List[str] = []
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type", ""))
        inputs = node.get("inputs") or {}
        if ctype == "LoadImage":
            load_img_nodes.append(nid)
        if seed is not None:
            if "noise_seed" in inputs and isinstance(inputs["noise_seed"], int):
                inputs["noise_seed"] = int(seed)
            elif "seed" in inputs and isinstance(inputs["seed"], int):
                inputs["seed"] = int(seed)
        if steps is not None and steps > 0:
            if ctype in ("KSampler", "KSamplerAdvanced", "BasicScheduler") and isinstance(inputs.get("steps"), int):
                inputs["steps"] = int(steps)
        if ctype in ("EmptyLatentImage", "EmptySD3LatentImage", "MiniMaxH3ImageToVideo"):
            if width and isinstance(inputs.get("width"), int):
                inputs["width"] = int(width)
            if height and isinstance(inputs.get("height"), int):
                inputs["height"] = int(height)
            if batch_size and isinstance(inputs.get("batch_size"), int):
                inputs["batch_size"] = int(batch_size)

    if first_frame_name and len(load_img_nodes) >= 1:
        wf[load_img_nodes[0]]["inputs"]["image"] = first_frame_name
    if last_frame_name and len(load_img_nodes) >= 2:
        wf[load_img_nodes[1]]["inputs"]["image"] = last_frame_name

    return wf


def _core_tokens(name: str) -> Set[str]:
    base = name.replace("\\", "/").split("/")[-1].lower()
    raw = [t for t in re.split(r"[^a-z0-9]+", base) if t]
    core = {t for t in raw if t not in _QUANT_NOISE_TOKENS}
    return core or set(raw)


def _extract_allowed_options(spec: Any) -> Optional[List[str]]:
    if not isinstance(spec, list) or not spec:
        return None
    first = spec[0]
    if isinstance(first, list):
        return [str(x) for x in first]
    if first == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        opts = spec[1].get("options")
        if isinstance(opts, list):
            return [str(x) for x in opts]
    return None


def reconcile_workflow_models(api_wf: Dict[str, Any], object_info: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Auto-remap template/workflow model filenames (e.g. int8_convrot -> fp16) to matching installed ComfyUI files."""
    wf = copy.deepcopy(api_wf)
    remaps: List[str] = []

    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type", ""))
        schema = object_info.get(ctype)
        if not schema:
            continue
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue

        all_specs: Dict[str, Any] = {}
        inp_schema = schema.get("input") or {}
        for sec in ("required", "optional"):
            s = inp_schema.get(sec)
            if isinstance(s, dict):
                all_specs.update(s)

        for iname, val in list(inputs.items()):
            if not isinstance(val, str):
                continue
            # Never silently replace a missing LoadImage with a random user photo
            if ctype == "LoadImage" and iname == "image":
                continue
            allowed = _extract_allowed_options(all_specs.get(iname))
            if not allowed or val in allowed:
                continue

            # 1. Exact basename match (handles subfolder differences like SDXL\sd_xl_base_1.0)
            want_base = val.replace("\\", "/").split("/")[-1].lower()
            exact_base = next(
                (opt for opt in allowed if opt.replace("\\", "/").split("/")[-1].lower() == want_base),
                None,
            )
            if exact_base:
                inputs[iname] = exact_base
                remaps.append(f"{val} -> {exact_base}")
                continue

            # 2. Core token similarity match (handles fp16 vs int8_convrot vs bf16 vs fp8 variants)
            want_toks = _core_tokens(val)
            best_opt: Optional[str] = None
            best_score = 0.0
            for opt in allowed:
                opt_toks = _core_tokens(opt)
                inter = want_toks & opt_toks
                if not inter:
                    continue
                # Prevent video/audio VAE cross-matching
                if ("video" in want_toks and "audio" in opt_toks) or ("audio" in want_toks and "video" in opt_toks):
                    continue
                jaccard = len(inter) / max(1, len(want_toks | opt_toks))
                recall = len(inter) / max(1, len(want_toks))
                score = 0.6 * jaccard + 0.4 * recall
                if score > best_score and (len(inter) >= 2 or jaccard >= 0.6):
                    best_score = score
                    best_opt = opt

            if best_opt and best_score >= 0.55:
                inputs[iname] = best_opt
                remaps.append(f"{val} -> {best_opt}")

    return wf, remaps

