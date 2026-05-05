# ADR-002: ONNX Runtime thay vì pickle để Serve ML Model

**Ngày:** 2026-05-05
**Trạng thái:** Accepted
**Người quyết định:** Team HYLIST

---

## Vấn đề (Context)

Sau khi train XGBoost model (Phase 2), cần chọn format để serialize và serve model trong production FastAPI endpoint `/api/v1/predict`.

## Đã xem xét (Options)

### A: ONNX Runtime
- **Ưu:** Cross-platform (Python/Java/C++/JS), inference nhanh hơn (tối ưu hóa graph), không có arbitrary code execution risk, MLflow hỗ trợ `mlflow.onnx.log_model()`, industry standard
- **Nhược:** Cần bước convert (`skl2onnx`), không phải mọi model đều convert được 100%

### B: pickle / joblib
- **Ưu:** Đơn giản, native Python, không cần convert
- **Nhược:** **Security risk nghiêm trọng** — `pickle.load()` có thể execute arbitrary code nếu file bị tamper. Không cross-platform. Không có graph optimization.

## Quyết định (Decision)
**Chọn A (ONNX Runtime)** vì security risk của pickle là không chấp nhận được trong production. XGBoost → ONNX conversion được hỗ trợ đầy đủ qua `skl2onnx`.

## Trade-off chấp nhận (Consequences)
Phải thêm bước convert trong training pipeline. Nếu gặp op không support → phải implement custom converter. Chấp nhận vì security quan trọng hơn.

---
> Rule: `# ❌ model = pickle.load(f)` / `# ✅ model = onnxruntime.InferenceSession("model.onnx")`
> Xem implementation: `ml/training/train_predictor.py` và `backend/src/services/prediction.service.py`
