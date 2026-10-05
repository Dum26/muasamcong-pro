"""Account directory and reversible suspension for administrators."""
from sqlalchemy import delete, func, select, update

from server.database import get_db, now, sessions, users


def require_admin(conn, actor_id):
    actor = conn.execute(select(users.c.role, users.c.is_active)
                         .where(users.c.id == actor_id)).first()
    if not actor or actor.role != "admin" or not actor.is_active:
        raise PermissionError("Không có quyền quản trị.")


def list_accounts(actor_id, query="", status="", role="", page=1):
    if status not in {"", "active", "locked"} or role not in {"", "user", "admin"}:
        raise ValueError("Bộ lọc không hợp lệ.")
    page = max(1, int(page))
    filters = []
    if query:
        filters.append(users.c.email.icontains(str(query).strip()[:320], autoescape=True))
    if status:
        filters.append(users.c.is_active.is_(status == "active"))
    if role:
        filters.append(users.c.role == role)
    with get_db().engine.connect() as conn:
        require_admin(conn, actor_id)
        count = lambda *where: conn.scalar(select(func.count()).select_from(users).where(*where))
        total = count(*filters)
        page = min(page, max(1, (total + 19) // 20))
        rows = conn.execute(select(users.c.id, users.c.email, users.c.role,
            users.c.is_active, users.c.created_at, users.c.last_login_at)
            .where(*filters).order_by(users.c.created_at.desc(), users.c.id)
            .offset((page - 1) * 20).limit(20)).mappings().all()
        return {"items": [dict(row) for row in rows], "total": total, "page": page,
                "page_size": 20, "summary": {"total": count(),
                "active": count(users.c.is_active.is_(True)),
                "locked": count(users.c.is_active.is_(False)),
                "admins": count(users.c.role == "admin")}}


def set_account_active(actor_id, target_id, active):
    if type(active) is not bool:
        raise ValueError("Trạng thái tài khoản phải là true hoặc false.")
    with get_db().engine.begin() as conn:
        require_admin(conn, actor_id)
        # Administrator accounts are protected from suspension through this UI.
        result = conn.execute(update(users).where(users.c.id == target_id,
            users.c.id != actor_id, users.c.role == "user")
            .values(is_active=active, updated_at=now()))
        if not result.rowcount:
            raise ValueError("Không tìm thấy người dùng hoặc đây là tài khoản quản trị được bảo vệ.")
        if not active:
            conn.execute(delete(sessions).where(sessions.c.user_id == target_id))
    return {"ok": True}
