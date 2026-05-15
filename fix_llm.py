import re

with open('backend/agent/batch_planner/llm.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换所有 'if val is not None:' 为 'if val not in [None, ""]:'
# 但在samples部分
old_pattern = '''        for key in ("nickname", "platform", "link_type", "upper_mid", "bvid", "avid", "short_code", "sec_uid", "aweme_id", "uid", "user_id", "note_id"):
            val = c.get(key)
            if val is not None:
                fields.append(f"{key}={val!r}")'''

new_pattern = '''        for key in ("nickname", "platform", "link_type", "upper_mid", "bvid", "avid", "short_code", "sec_uid", "aweme_id", "uid", "user_id", "note_id"):
            val = c.get(key)
            if val not in [None, ""]:
                fields.append(f"{key}={val!r}")'''

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print('Replaced successfully!')
else:
    print('Pattern not found')

with open('backend/agent/batch_planner/llm.py', 'w', encoding='utf-8') as f:
    f.write(content)
