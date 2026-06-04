"""OCR pass: a frame in, normalized text tokens out.

Thin wrapper over RapidOCR (ONNX, CPU). Boxes are normalized to fractions of the
frame so downstream interpretation is resolution-independent. The engine is
expensive to construct (loads ONNX models), so it is created once and reused.

Heavy deps (rapidocr_onnxruntime) are imported lazily and live behind the
[capture] extra — importing this module is cheap.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """One OCR detection, with its box normalized to [0, 1] fractions."""

    text: str
    score: float
    cx: float  # box center x (fraction of width)
    cy: float  # box center y (fraction of height)
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.cx - self.w / 2

    @property
    def right(self) -> float:
        return self.cx + self.w / 2

    @property
    def top(self) -> float:
        return self.cy - self.h / 2

    @property
    def bottom(self) -> float:
        return self.cy + self.h / 2


_ENGINE = None


def gpu_available() -> bool:
    """True if a GPU execution provider (DirectML/CUDA) is available to ORT."""
    try:
        import onnxruntime as ort
    except ImportError:  # pragma: no cover
        return False
    providers = set(ort.get_available_providers())
    return bool(providers & {"DmlExecutionProvider", "CUDAExecutionProvider"})


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            import onnxruntime as ort

            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                'OCR needs the [capture] extra + RapidOCR:\n'
                '  pip install -e ".[capture]" rapidocr-onnxruntime'
            ) from exc

        # Auto-enable a GPU execution provider when one is installed, else CPU.
        # Installing onnxruntime-directml (instead of onnxruntime) lights up
        # DirectML on any DX12 GPU; installing onnxruntime-gpu lights up CUDA.
        providers = set(ort.get_available_providers())
        kwargs = {}
        if "DmlExecutionProvider" in providers:
            kwargs = dict(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
        elif "CUDAExecutionProvider" in providers:
            kwargs = dict(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
        _ENGINE = RapidOCR(**kwargs)
    return _ENGINE


def read_tokens(frame, *, min_score: float = 0.4) -> list[Token]:
    """Run OCR on a BGR frame and return tokens with fractional boxes."""
    engine = _get_engine()
    h, w = frame.shape[:2]
    result, _ = engine(frame)
    tokens: list[Token] = []
    for box, text, score in result or []:
        score = float(score)
        if score < min_score:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        tokens.append(
            Token(
                text=str(text).strip(),
                score=score,
                cx=((x0 + x1) / 2) / w,
                cy=((y0 + y1) / 2) / h,
                w=(x1 - x0) / w,
                h=(y1 - y0) / h,
            )
        )
    return tokens
