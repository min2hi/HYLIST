# Retro: Phase 2 - Tuần 7 & 8 (ML Engine: ONNX Serving, SHAP, Shadow Mode)

**Date**: 2026-05-07  
**Phase**: Phase 2 (ML Engine)  
**Status**: Xong 100% Phase 2 🎉

## 1. Mục Tiêu Đạt Được
- **Tuần 7 (Inference & APIs):**
  - Chuyển đổi thành công model XGBoost sang **ONNX** thông qua `onnxmltools`. Giải quyết triệt để vấn đề incompatibility bằng workaround reset tên feature thành `f0..f12` trước khi convert.
  - Implement `MLService` Singleton pattern sử dụng ONNX Runtime. Model chỉ load 1 lần khi FastAPI startup (qua lifespan event), tối ưu hóa memory và latency (trung bình `0.016ms` cho 1 lượt suy luận - đạt SLA <100ms).
  - Hoàn thiện `POST /api/v1/ml/predict/{task_id}` và Celery task `predict_task_priority` kèm exponential backoff retry.
  
- **Tuần 8 (Explainability & Shadow Mode):**
  - Implement mô hình **Shadow Mode** thông qua database table `ml_predictions`. Mọi lượt inference đều được ghi lại (lưu trữ `predicted_hours`, `confidence` và latency) để đối chiếu sau này với `actual_hours` khi task `DONE`.
  - Giữ lại format native XGBoost (`.ubj` - Universal Binary JSON - an toàn, không dính lỗ hổng bảo mật của pickle) bên cạnh model ONNX.
  - Tích hợp **SHAP (SHapley Additive exPlanations)** thông qua `shap.TreeExplainer` đọc model `.ubj`. Giờ đây, mỗi dự đoán trả về đều kèm theo `shap_values` giải thích tầm quan trọng của từng feature đối với kết quả đó.
  - Thực thi bài test Parity (`test_parity.py`): Khẳng định môi trường serving và training đồng nhất hoàn toàn (max diff `0.00000334h`).

## 2. Kiến Trúc (Architecture Update)
- **Model Storage:**
  - `priority_predictor_v1.onnx` -> Dành cho inference tốc độ cao.
  - `priority_predictor_v1.ubj` -> Dành cho phân tích SHAP và explainability.
- **Data Flow:**
  - `Task Created` -> Celery Queue -> Worker -> `MLService.predict()` -> Insert record vào bảng `ml_predictions` (Shadow Mode).
  - Endpoint `POST /api/v1/ml/predict` support prediction manual, cũng thực hiện lưu Shadow Mode.

## 3. Quyết Định Kỹ Thuật (MEMORY Update)
- Không dùng `KernelExplainer` trên ONNX model (quá chậm). Giải pháp: Lưu model format `.ubj` cùng lúc với ONNX, sử dụng thư viện `xgboost` load `.ubj` chuyên dụng chỉ cho tính năng Explainability (`TreeExplainer`). Phù hợp chuẩn bảo mật ADR-002 do UBJ không execute arbitrary code.
- Xóa index lặp: FastAPI/SQLAlchemy `index=True` kết hợp `__table_args__ Index()` gây lỗi SQLite. Quyết định xóa cấu hình Index trùng.

## 4. Kiểm Định Chất Lượng
- **Ruff**: `Clean`
- **Pytest**: 78/78 passed
- **Parity Limit**: Yêu cầu < 0.01h, thực tế đạt 0.00000334h.

## 5. Next Steps (Sang Phase 3)
- Hoàn tất lưu lượng ML mlflow tracking và pipeline.
- Triển khai **Phase 3 (NLP Auto-Tagging & Real-time)**:
  - Bắt đầu fine-tune hoặc zero-shot mô hình **SetFit** cho tính năng Auto-tagging.
  - Xây dựng kiến trúc SSE (Server-Sent Events) để đẩy dự đoán ML & NLP real-time về cho frontend.
