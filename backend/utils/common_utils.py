import re

"""
TODO: 只能匹配https://space.bilibili.com/xxxx 其他类型的url都无法匹配
"""
def extract_mid_from_space_url(space_url: str) -> int | None:
    """从 B 站主页链接中提取 upper_mid。

    Args:
        space_url: B 站空间链接，如 "https://space.bilibili.com/472954189"

    Returns:
        提取到的整数 mid，如果提取失败返回 None。
    """
    if not space_url:
        return None
    match = re.search(r"space\.bilibili\.com/(\d+)", space_url)
    if match:
        return int(match.group(1))
    return None