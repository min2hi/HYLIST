## 📋 Mô Tả

<!-- Mô tả ngắn gọn PR này làm gì và tại sao -->

## 🔗 Liên Kết Issue

<!-- Closes #<issue-number> hoặc Refs #<issue-number> -->
Closes #

## 📦 Loại Thay Đổi

<!-- Đánh dấu X vào ô phù hợp -->
- [ ] 🐛 Bug fix (fix lỗi, không break existing behavior)
- [ ] ✨ Feature mới (thêm tính năng, không break existing behavior)
- [ ] 💥 Breaking change (thay đổi làm break existing behavior)
- [ ] 🔧 Refactor (không thêm feature, không fix bug)
- [ ] 📝 Docs / Comments
- [ ] 🧪 Tests
- [ ] 🏗️ Infrastructure / CI / Config

## ✅ Checklist Trước Khi Merge

### Code Quality
- [ ] Đã chạy `ruff check src/` — không có lỗi
- [ ] Đã chạy `ruff format src/` — code đã format
- [ ] Không có `print()` / `console.log()` debug còn sót
- [ ] Không có hardcoded secrets hay credentials

### Tests
- [ ] Đã chạy `pytest tests/ --cov=src --cov-fail-under=65` — xanh
- [ ] Đã viết test cho code mới (nếu có logic mới)
- [ ] Coverage không giảm so với trước PR

### Backend (nếu có thay đổi Python)
- [ ] Response format đúng chuẩn `{success, data?, message?, error_code?}`
- [ ] Mọi query có filter `org_id` (multi-tenancy)
- [ ] Mọi query có filter `user.id` (IDOR prevention)
- [ ] Nếu thêm model/column → đã tạo Alembic migration

### Self-Review
- [ ] Đã tự đọc lại diff một lần trước khi submit
- [ ] Tên branch đúng convention: `feat/`, `fix/`, `refactor/`, `chore/`
- [ ] Commit message đúng Conventional Commits

## 📸 Screenshots (nếu có thay đổi UI)

<!-- Thêm screenshots trước/sau nếu có -->

## 📝 Ghi Chú Cho Reviewer

<!-- Những điểm cần reviewer chú ý đặc biệt, trade-offs, quyết định thiết kế -->
