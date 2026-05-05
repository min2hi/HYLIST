# AI Harness Template 🚀

Template chuyên nghiệp để khởi động dự án mới với đầy đủ:
- **AI Context Layer** (AGENTS.md + Skills + Templates)
- **Pre-commit Guardrails** (Husky + Commitlint + Lint-staged)
- **CI/CD Pipeline** (Gitleaks + npm audit + Tests)
- **Security Scanning** (Dependabot + Secret scanner)
- **Documentation** (ADR template + docs structure)
- **Branch Protection** (automated script)

---

## ⚡ Hướng Dẫn Sử Dụng

### Bước 1: Tạo project mới từ template

```
GitHub → "Use this template" → đặt tên repo → Create
```

Hoặc dùng GitHub CLI:
```bash
gh repo create <tên-project> --template min2hi/ai-harness-template --private --clone
cd <tên-project>
```

### Bước 2: Chạy setup script

**Windows:**
```powershell
.\setup.ps1
```

**Mac/Linux:**
```bash
bash setup.sh
```

Script sẽ hỏi:
- `Project Name` — tên hiển thị (VD: ShopEase)
- `Project Slug` — tên package.json (VD: shopease)
- `GitHub Owner` — username hoặc org (VD: min2hi)
- `GitHub Repo` — tên repo (VD: shopease)
- `Backend Dir` — folder backend (mặc định: `backend`)
- `Frontend Dir` — folder frontend (mặc định: `frontend`)

Sau đó script **tự điền** placeholder vào tất cả file và **cài npm deps**.

### Bước 3: Cập nhật nội dung project-specific

```
[ ] .claude/skills/architecture/SKILL.md  → Điền tech stack thực tế
[ ] AGENTS.md                              → Review lại nếu cần thêm context
[ ] .github/workflows/ci.yml              → Điều chỉnh nếu cần thêm steps
```

### Bước 4: Push lên GitHub

```bash
git init
git add .
git commit -m "chore: initial project setup from ai-harness-template"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

### Bước 5: Bật Branch Protection

```bash
bash docs/setup-branch-protection.sh
```

### Bước 6: Xóa setup scripts

```bash
Remove-Item setup.ps1, setup.sh   # Windows
rm setup.ps1 setup.sh             # Mac/Linux
```

---

## 📁 Cấu Trúc Template

```
.
├── AGENTS.md                      ← AI entry point (giữ ở root)
├── setup.ps1                      ← Setup script Windows
├── setup.sh                       ← Setup script Mac/Linux
├── commitlint.config.cjs          ← Commit message rules
├── .gitleaks.toml                 ← Secret scanner config
├── package.json                   ← Root devDependencies
├── .husky/
│   ├── pre-commit                 ← Chạy lint-staged
│   └── commit-msg                 ← Chạy commitlint
├── .claude/
│   ├── skills/                    ← AI domain knowledge
│   │   ├── architecture/SKILL.md  ← ⚠️  CẦN ĐIỀN THÔNG TIN DỰ ÁN
│   │   ├── backend/SKILL.md       ← Express+TS rules (portable)
│   │   ├── frontend/SKILL.md      ← Next.js rules (portable)
│   │   ├── testing/SKILL.md       ← Test hygiene rules
│   │   └── git-workflow/SKILL.md  ← Git + ADR workflow
│   └── templates/                 ← Code templates
│       ├── service.template.ts
│       ├── controller.template.ts
│       └── routes.template.ts
├── .github/
│   ├── workflows/ci.yml           ← Gitleaks + Build + Test + Audit
│   ├── dependabot.yml             ← Auto dependency updates
│   └── pull_request_template.md
└── docs/
    ├── adr/ADR-000-template.md    ← Template tạo ADR mới
    └── setup-branch-protection.sh ← Script bật Branch Protection
```

---

## 🔧 Placeholders

Script sẽ thay thế các placeholder sau:

| Placeholder | Ví dụ |
|-------------|-------|
| `{{PROJECT_NAME}}` | ShopEase |
| `{{PROJECT_SLUG}}` | shopease |
| `{{GITHUB_OWNER}}` | min2hi |
| `{{GITHUB_REPO}}` | shopease |
| `{{BACKEND_DIR}}` | backend |
| `{{FRONTEND_DIR}}` | frontend |

---

Made with ❤️ — based on [MediChain](https://github.com/min2hi/medi_chain) AI Harness
