"""Add ml_predictions relationship to Task model"""
from pathlib import Path

p = Path("backend/src/models/__init__.py")
content = p.read_bytes()

old = b'    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="task")'
new = (
    b'    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="task")\r\n'
    b'    ml_predictions: Mapped[list["MLPrediction"]] = relationship("MLPrediction", back_populates="task")'
)

if old in content:
    p.write_bytes(content.replace(old, new))
    print("Done - relationship added")
else:
    print("ERROR: target not found")
    # Find closest match
    idx = content.find(b"audit_logs")
    print(f"audit_logs found at byte: {idx}")
    print(repr(content[idx:idx+100]))
