import json
import os

output_file = os.path.join('structured_kr_data.json')

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump({}, f, ensure_ascii=False, indent=2)