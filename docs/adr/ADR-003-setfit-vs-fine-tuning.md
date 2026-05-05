# ADR-003: SetFit thay vì Full Fine-tuning cho NLP Auto-tagging

**Ngày:** 2026-05-05
**Trạng thái:** Accepted
**Người quyết định:** Team HYLIST

---

## Vấn đề (Context)

Phase 3 cần classify task descriptions thành tags: `[Bug, Feature, Urgent, Research]`. Cần chọn NLP approach phù hợp với lượng data có sẵn (ít labeled data ban đầu).

## Đã xem xét (Options)

### A: SetFit (Sentence Transformers + Few-shot Fine-tuning)
- **Ưu:** Chỉ cần 8–64 labeled samples/class để đạt accuracy tốt, training nhanh (vài phút trên CPU), không cần GPU đắt tiền, HuggingFace native support, inference nhanh
- **Nhược:** Accuracy không bằng full fine-tune khi có nhiều data, giới hạn ở sentence-level classification

### B: Full BERT/RoBERTa Fine-tuning
- **Ưu:** Accuracy cao hơn khi có nhiều labeled data (1000+ samples/class)
- **Nhược:** Cần nhiều labeled data, cần GPU để train trong thời gian hợp lý, phức tạp hơn, slow inference nếu không optimize

### C: Prompt-based LLM (GPT-4o-mini)
- **Ưu:** Zero-shot, không cần labeled data
- **Nhược:** Latency cao (>1s per request), cost per inference, không thể self-host

## Quyết định (Decision)
**Chọn A (SetFit)** vì HYLIST bắt đầu với ít labeled data (có thể generate synthetic labels từ GPT-4o-mini cho bootstrap). Accuracy 85-90% đủ dùng cho MVP. Sau này nếu có đủ data và cần accuracy cao hơn, có thể migrate sang full fine-tune.

## Trade-off chấp nhận (Consequences)
Accuracy ~85-90% thay vì ~95%+ của full fine-tune. NLP Worker cần container riêng vì PyTorch dependency nặng (~1.5GB). Chấp nhận vì iteration speed quan trọng hơn ở giai đoạn đầu.

---
> Xem implementation: `workers/nlp_worker.py`
> NLP Worker chạy container riêng — xem `workers/Dockerfile`
