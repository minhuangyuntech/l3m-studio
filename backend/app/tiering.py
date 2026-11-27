from __future__ import annotations

import math
from typing import Any, Dict, List


def resolve_context_length(requested: str, model_max_ctx: int, free_vram_gb: float, is_moe: bool) -> int:
    if requested != "auto":
        try:
            val = int(requested)
            return min(val, model_max_ctx) if model_max_ctx > 0 else val
        except ValueError:
            pass

    # Auto context sizing based on VRAM
    if free_vram_gb >= 20:
        target = 32768
    elif free_vram_gb >= 12:
        target = 16384
    elif free_vram_gb >= 7:
        target = 16384 if is_moe else 8192
    else:
        target = 8192

    if model_max_ctx > 0:
        return min(target, model_max_ctx)
    return target


def estimate_kv_cache_gb(
    block_count: int,
    head_count_kv: int,
    embedding_length: int,
    head_count: int,
    context_length: int,
    kv_q8: bool,
) -> float:
    layers = block_count if block_count > 0 else 32
    kv_heads = head_count_kv if head_count_kv > 0 else 8
    head_dim = (embedding_length // head_count) if (embedding_length > 0 and head_count > 0) else 128
    # 2 (K + V) * layers * kv_heads * head_dim * ctx * bytes_per_element
    bytes_per_elem = 1.06 if kv_q8 else 2.0
    total_bytes = 2 * layers * kv_heads * head_dim * context_length * bytes_per_elem
    return round(total_bytes / (1024**3), 2)


def plan_auto_tiering(
    model: Dict[str, Any],
    hardware: Dict[str, Any],
    context_setting: str = "auto",
    kv_cache_q8: bool = True,
    flash_attn: bool = True,
    reserve_ram_gb: float = 4.0,
    no_mmap: bool = False,
) -> Dict[str, Any]:
    """Compute LocModel-style VRAM / RAM / Disk auto-tiering plan and llama-server CLI flags."""
    size_gb = float(model.get("size_gb", 0.0))
    mmproj_gb = float(model.get("mmproj_size_gb", 0.0))
    block_count = int(model.get("block_count", 0) or 32)
    expert_count = int(model.get("expert_count", 0) or 0)
    expert_used = int(model.get("expert_used_count", 0) or 0)
    is_moe = expert_count > 1

    total_vram = float(hardware.get("total_vram_gb", 0.0))
    # Keep a small safety buffer (~0.9 GB) for CUDA runtime & desktop compositor
    usable_vram = max(0.0, total_vram - 0.9) if total_vram > 1.5 else 0.0
    ram_total = float(hardware.get("memory", {}).get("total_gb", 16.0))
    ram_avail = float(hardware.get("memory", {}).get("available_gb", 8.0))
    usable_ram = max(0.0, min(ram_total - reserve_ram_gb, ram_avail + 2.0))

    ctx = resolve_context_length(
        context_setting,
        int(model.get("context_length", 0) or 0),
        usable_vram,
        is_moe,
    )
    kv_gb = estimate_kv_cache_gb(
        block_count=block_count,
        head_count_kv=int(model.get("head_count_kv", 0) or 0),
        embedding_length=int(model.get("embedding_length", 0) or 0),
        head_count=int(model.get("head_count", 0) or 0),
        context_length=ctx,
        kv_q8=kv_cache_q8,
    )

    total_required_gb = round(size_gb + mmproj_gb + kv_gb, 2)
    extra_args: List[str] = []
    tier_mode = "full_gpu"
    summary_zh = ""
    gpu_layers = 999
    offload_experts_cpu = False

    if usable_vram <= 0.5:
        # Pure CPU mode
        vram_alloc = 0.0
        ram_alloc = min(total_required_gb, usable_ram)
        disk_alloc = max(0.0, round(total_required_gb - ram_alloc, 2))
        gpu_layers = 0
        tier_mode = "cpu_only"
        summary_zh = "純 CPU + 系統記憶體推理（未偵測到獨立 GPU 加速）"
    elif total_required_gb <= usable_vram:
        # Everything fits in VRAM!
        vram_alloc = total_required_gb
        ram_alloc = 0.0
        disk_alloc = 0.0
        gpu_layers = 999
        tier_mode = "full_gpu"
        summary_zh = "全部權重與 KV 快取常駐顯卡 VRAM，可獲得最高生成速度"
    elif is_moe:
        # MoE smart tiering: Attention + Shared layers + KV Cache in VRAM, MoE Experts in RAM (or Disk mmap)
        # In MoE models like Qwen3.6-35B-A3B, attention + shared weights are roughly 14-18% of file size
        shared_and_attn_gb = round(size_gb * 0.16 + mmproj_gb * 0.6, 2)
        vram_needed_core = shared_and_attn_gb + kv_gb
        vram_alloc = round(min(usable_vram, max(vram_needed_core, usable_vram * 0.85)), 2)
        remaining = max(0.0, round(total_required_gb - vram_alloc, 2))
        ram_alloc = round(min(remaining, usable_ram), 2)
        disk_alloc = round(max(0.0, remaining - ram_alloc), 2)
        offload_experts_cpu = True
        gpu_layers = 999
        tier_mode = "moe_hybrid" if disk_alloc <= 0.2 else "moe_three_tier"
        # Use llama.cpp's --override-tensor to place MoE experts on CPU while keeping attention + KV on GPU!
        extra_args.extend(["-ot", ".ffn_.*_exps.=CPU"])
        if disk_alloc > 0.2:
            summary_zh = (
                f"三層自動分層（MoE）：注意力層與 KV 快取優先駐留顯卡 VRAM，"
                f"專家權重分配至系統記憶體（保留 {reserve_ram_gb:.0f} GB 給系統）與硬碟 mmap 按需讀取"
            )
        else:
            summary_zh = (
                f"雙層自動分層（MoE）：注意力層、共享層與 KV 快取駐留顯卡 VRAM，"
                f"MoE 專家層分層至系統記憶體高速執行"
            )
    else:
        # Dense hybrid offloading
        weight_vram_budget = max(0.0, usable_vram - kv_gb - mmproj_gb * 0.5)
        ratio = min(1.0, max(0.0, weight_vram_budget / max(size_gb, 0.1)))
        gpu_layers = int(math.floor(block_count * ratio))
        vram_alloc = round(min(usable_vram, size_gb * ratio + kv_gb + mmproj_gb * 0.5), 2)
        remaining = max(0.0, round(total_required_gb - vram_alloc, 2))
        ram_alloc = round(min(remaining, usable_ram), 2)
        disk_alloc = round(max(0.0, remaining - ram_alloc), 2)
        tier_mode = "dense_hybrid" if disk_alloc <= 0.2 else "dense_three_tier"
        summary_zh = (
            f"混合分層：將 {gpu_layers}/{block_count} 層與 KV 快取放入顯卡 VRAM，"
            f"其餘權重自動卸載至系統記憶體" + ("與硬碟按需讀取" if disk_alloc > 0.2 else "")
        )

    # Estimate tok/s and cold load time
    # Bandwidth rough heuristic: GPU ~250-450 GB/s, DDR5/DDR4 RAM ~35-55 GB/s, NVMe ~3 GB/s
    active_ratio = (expert_used / expert_count) if (is_moe and expert_used > 0 and expert_count > 0) else 1.0
    effective_active_gb = max(1.2, size_gb * (0.16 + 0.84 * active_ratio))

    if tier_mode == "full_gpu":
        est_tok_s = min(180.0, max(12.0, 260.0 / effective_active_gb))
    elif tier_mode in ("moe_hybrid", "moe_three_tier"):
        # MoE active weights are small (~2.5-3.5 GB), mostly read from RAM
        ram_read_gb = effective_active_gb * 0.82
        base_tok_s = 42.0 / max(ram_read_gb, 1.0)
        if disk_alloc > 1.0:
            penalty = max(0.35, 1.0 - (disk_alloc / max(size_gb, 1.0)) * 0.7)
            base_tok_s *= penalty
        est_tok_s = min(65.0, max(4.0, base_tok_s))
    elif tier_mode in ("dense_hybrid", "dense_three_tier"):
        gpu_frac = vram_alloc / max(total_required_gb, 0.1)
        ram_gb_read = size_gb * (1.0 - gpu_frac)
        gpu_gb_read = size_gb * gpu_frac
        time_per_tok = (gpu_gb_read / 260.0) + (ram_gb_read / 38.0) + (disk_alloc / 3.0)
        est_tok_s = min(90.0, max(2.0, 1.0 / max(time_per_tok, 0.01)))
    else:
        est_tok_s = max(1.5, 28.0 / max(effective_active_gb, 1.0))

    est_load_sec = max(3, int(round((vram_alloc / 1.8) + (ram_alloc / 1.4) + 2)))

    # Compatibility badge
    if est_tok_s >= 25:
        compatibility = "optimal"
        compatibility_label = "極速流暢"
    elif est_tok_s >= 10:
        compatibility = "good"
        compatibility_label = "自動分層流暢"
    elif est_tok_s >= 5:
        compatibility = "playable"
        compatibility_label = "可用（分層運行）"
    else:
        compatibility = "heavy"
        compatibility_label = "資源吃緊"

    return {
        "tier_mode": tier_mode,
        "summary_zh": summary_zh,
        "is_moe": is_moe,
        "context_length": ctx,
        "kv_cache_gb": kv_gb,
        "total_required_gb": total_required_gb,
        "vram_gb": vram_alloc,
        "ram_gb": ram_alloc,
        "disk_gb": disk_alloc,
        "vram_total_gb": total_vram,
        "ram_total_gb": ram_total,
        "reserve_ram_gb": reserve_ram_gb,
        "gpu_layers": gpu_layers,
        "block_count": block_count,
        "offload_experts_cpu": offload_experts_cpu,
        "estimated_tok_s": round(est_tok_s, 1),
        "estimated_load_seconds": est_load_sec,
        "compatibility": compatibility,
        "compatibility_label": compatibility_label,
        "recommended_args": {
            "ngl": gpu_layers,
            "ctx": ctx,
            "flash_attn": flash_attn,
            "kv_cache_q8": kv_cache_q8,
            "no_mmap": no_mmap,
            "extra_args": extra_args,
        },
    }
