import config

def is_admin(user_id: int) -> bool:
    return True if user_id == config.ADMIN_ID else False