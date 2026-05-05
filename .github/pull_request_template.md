## 📝 Mô tả thay đổi
<!-- Giải quyết vấn đề gì? Link issue (Closes #123) -->

## 🏷️ Loại thay đổi
- [ ] ✨ `feat` — Tính năng mới
- [ ] 🐛 `fix` — Sửa lỗi
- [ ] ♻️ `refactor` — Không thêm feature, không fix bug
- [ ] 📝 `docs` — Tài liệu
- [ ] 🔧 CI/CD / Cấu hình

## ✅ Checklist Kỹ Thuật
- [ ] Code chạy được ở local
- [ ] Không có `console.log` debug trong production code
- [ ] Không có hardcoded secrets/API keys
- [ ] CI pipeline pass ✅
- [ ] Đã kiểm tra blast radius nếu sửa code cũ

## 🔐 Security
- [ ] Không thay đổi ảnh hưởng authentication/authorization
- [ ] Dữ liệu user không bị leak qua API response mới
- [ ] Database migration có thể rollback không? `[ ] Có` `[ ] Không cần`
