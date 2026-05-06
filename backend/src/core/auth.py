"""
RBAC (Role-Based Access Control) — Kiểm soát quyền truy cập.

Cách dùng trong Router:
    from ...core.auth import require_role, Role, CurrentUser, get_current_user

    # Chỉ ADMIN mới xóa được:
    @router.delete("/{id}", dependencies=[Depends(require_role(Role.ADMIN))])

    # Lấy thông tin user hiện tại:
    @router.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return user.id
"""

from enum import Enum

from fastapi import Depends, HTTPException, status

from .security import CurrentUser, get_current_user


class Role(str, Enum):  # noqa: UP042
    # Keep str+Enum for Pydantic v2 serialization compatibility
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"


# Thứ tự quyền từ cao xuống thấp
_ROLE_HIERARCHY = {
    Role.ADMIN: 4,
    Role.MANAGER: 3,
    Role.MEMBER: 2,
    Role.VIEWER: 1,
}


def require_role(*roles: Role):
    """
    Dependency — Chặn request nếu user không có đủ quyền.

    Ví dụ: require_role(Role.MANAGER) cho phép MANAGER và ADMIN vào.
    Logic: User có thể dùng endpoint nếu role của họ >= role yêu cầu thấp nhất.
    """
    min_level = min(_ROLE_HIERARCHY[r] for r in roles)

    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_level = _ROLE_HIERARCHY.get(Role(user.role), 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Hành động này yêu cầu quyền: {[r.value for r in roles]}",
            )
        return user

    return checker
