from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any, Dict, Optional

GGUF_MAGIC = b"GGUF"

# GGUF metadata value types
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12

SCALAR_FORMATS = {
    GGUF_TYPE_UINT8: ("<B", 1),
    GGUF_TYPE_INT8: ("<b", 1),
    GGUF_TYPE_UINT16: ("<H", 2),
    GGUF_TYPE_INT16: ("<h", 2),
    GGUF_TYPE_UINT32: ("<I", 4),
    GGUF_TYPE_INT32: ("<i", 4),
    GGUF_TYPE_FLOAT32: ("<f", 4),
    GGUF_TYPE_BOOL: ("<?", 1),
    GGUF_TYPE_UINT64: ("<Q", 8),
    GGUF_TYPE_INT64: ("<q", 8),
    GGUF_TYPE_FLOAT64: ("<d", 8),
}

FILE_TYPE_NAMES = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
    19: "IQ2_XXS",
    20: "IQ2_XS",
    21: "IQ3_XXS",
    22: "IQ1_S",
    23: "IQ4_NL",
    24: "IQ3_S",
    25: "IQ2_S",
    26: "IQ4_XS",
    27: "IQ1_M",
    28: "BF16",
    29: "Q4_0_4_4",
    30: "Q4_0_4_8",
    31: "Q4_0_8_8",
    32: "TQ1_0",
    33: "TQ2_0",
}

QUANT_REGEX = re.compile(
    r"(UD-Q[0-9]_[A-Z0-9_]+|IQ[0-9]_[A-Z0-9_]+|Q[0-9]_[A-Z0-9_]+|BF16|F16|F32|FP8[A-Z0-9_]*)",
    re.IGNORECASE,
)

INTERESTING_KEYS = {
    "general.architecture",
    "general.name",
    "general.basename",
    "general.size_label",
    "general.file_type",
    "general.quantization_version",
    "general.type",
    "clip.has_vision_encoder",
    "clip.projector_type",
}

INTERESTING_SUFFIXES = (
    ".block_count",
    ".context_length",
    ".embedding_length",
    ".feed_forward_length",
    ".expert_count",
    ".expert_used_count",
    ".attention.head_count",
    ".attention.head_count_kv",
    ".attention.key_length",
    ".attention.value_length",
)


def _read_string(f) -> str:
    raw_len = f.read(8)
    if len(raw_len) < 8:
        raise EOFError("Unexpected EOF reading string length")
    length = struct.unpack("<Q", raw_len)[0]
    if length > 10_000_000:
        raise ValueError(f"Unreasonable GGUF string length: {length}")
    data = f.read(length)
    return data.decode("utf-8", errors="replace")


def _skip_value(f, vtype: int) -> None:
    if vtype in SCALAR_FORMATS:
        _, size = SCALAR_FORMATS[vtype]
        f.seek(size, 1)
    elif vtype == GGUF_TYPE_STRING:
        raw_len = f.read(8)
        if len(raw_len) < 8:
            raise EOFError()
        length = struct.unpack("<Q", raw_len)[0]
        f.seek(length, 1)
    elif vtype == GGUF_TYPE_ARRAY:
        header = f.read(12)
        if len(header) < 12:
            raise EOFError()
        elem_type, count = struct.unpack("<IQ", header)
        if elem_type in SCALAR_FORMATS:
            _, size = SCALAR_FORMATS[elem_type]
            f.seek(size * count, 1)
        else:
            for _ in range(count):
                _skip_value(f, elem_type)
    else:
        raise ValueError(f"Unknown GGUF value type: {vtype}")


def _read_value(f, vtype: int) -> Any:
    if vtype in SCALAR_FORMATS:
        fmt, size = SCALAR_FORMATS[vtype]
        raw = f.read(size)
        if len(raw) < size:
            raise EOFError()
        return struct.unpack(fmt, raw)[0]
    if vtype == GGUF_TYPE_STRING:
        return _read_string(f)
    _skip_value(f, vtype)
    return None


def infer_quant_from_name(name: str) -> str:
    match = QUANT_REGEX.search(name)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def parse_gguf_metadata(path: Path) -> Dict[str, Any]:
    """Read key architectural metadata from a GGUF header without loading weights."""
    result: Dict[str, Any] = {
        "valid_gguf": False,
        "architecture": "",
        "model_name": path.stem,
        "size_label": "",
        "quantization": infer_quant_from_name(path.name),
        "block_count": 0,
        "context_length": 0,
        "embedding_length": 0,
        "expert_count": 0,
        "expert_used_count": 0,
        "head_count": 0,
        "head_count_kv": 0,
        "is_mmproj": False,
        "tensor_count": 0,
    }
    try:
        with path.open("rb") as f:
            magic = f.read(4)
            if magic != GGUF_MAGIC:
                return result
            version = struct.unpack("<I", f.read(4))[0]
            if version not in (2, 3):
                return result
            tensor_count, kv_count = struct.unpack("<QQ", f.read(16))
            result["valid_gguf"] = True
            result["tensor_count"] = int(tensor_count)

            meta: Dict[str, Any] = {}
            for _ in range(min(kv_count, 5000)):
                key = _read_string(f)
                vtype = struct.unpack("<I", f.read(4))[0]
                want = key in INTERESTING_KEYS or key.endswith(INTERESTING_SUFFIXES)
                if want and vtype != GGUF_TYPE_ARRAY:
                    meta[key] = _read_value(f, vtype)
                else:
                    _skip_value(f, vtype)

            arch = str(meta.get("general.architecture", "") or "")
            result["architecture"] = arch
            if meta.get("general.name"):
                result["model_name"] = str(meta["general.name"])
            if meta.get("general.size_label"):
                result["size_label"] = str(meta["general.size_label"])

            if result["quantization"] == "UNKNOWN" and "general.file_type" in meta:
                ft = int(meta["general.file_type"])
                if ft in FILE_TYPE_NAMES:
                    result["quantization"] = FILE_TYPE_NAMES[ft]

            if arch == "clip" or meta.get("clip.has_vision_encoder") or "mmproj" in path.name.lower():
                result["is_mmproj"] = True

            def _get_arch_int(suffix: str) -> int:
                if arch and f"{arch}{suffix}" in meta:
                    return int(meta[f"{arch}{suffix}"])
                for k, v in meta.items():
                    if k.endswith(suffix) and isinstance(v, (int, float)):
                        return int(v)
                return 0

            result["block_count"] = _get_arch_int(".block_count")
            result["context_length"] = _get_arch_int(".context_length")
            result["embedding_length"] = _get_arch_int(".embedding_length")
            result["expert_count"] = _get_arch_int(".expert_count")
            result["expert_used_count"] = _get_arch_int(".expert_used_count")
            result["head_count"] = _get_arch_int(".attention.head_count")
            result["head_count_kv"] = _get_arch_int(".attention.head_count_kv")
    except Exception:
        pass
    return result
