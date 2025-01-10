import json
import os

def create_kr_html(data_dir):
    """한글 XBRL 시각화 HTML 생성"""
    
    # JSON 데이터 로드
    json_path = os.path.join(data_dir, 'structured_kr_data.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # HTML 템플릿 시작
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>XBRL 재무제표 시각화</title>
        <style>
            body {
                font-family: 'Noto Sans KR', sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f8fafc;
                color: #1a202c;
                line-height: 1.6;
            }
            
            .section {
                background-color: white;
                border-radius: 12px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                margin-bottom: 24px;
                padding: 24px;
            }
            
            .section-title {
                font-size: 28px;
                font-weight: 700;
                color: #2d3748;
                margin-bottom: 20px;
                padding-bottom: 12px;
                border-bottom: 2px solid #e2e8f0;
            }
            
            .item {
                margin: 16px 0;
                padding-left: 20px;
            }
            
            .item-header {
                font-weight: 600;
                cursor: pointer;
                padding: 12px;
                background-color: #f7fafc;
                border-radius: 8px;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
            }
            
            .item-header:hover {
                background-color: #edf2f7;
            }
            
            .item-content {
                display: none;
                margin: 12px 0;
                padding: 16px;
                background-color: #fff;
                border-radius: 8px;
                border-left: 3px solid #4299e1;
            }
            
            .toggle-btn {
                display: inline-block;
                width: 24px;
                height: 24px;
                line-height: 24px;
                text-align: center;
                margin-right: 8px;
                color: #4299e1;
                font-weight: bold;
            }
            
            .value {
                color: #2b6cb0;
                background-color: #ebf8ff;
                padding: 12px;
                border-radius: 6px;
                margin: 8px 0;
                font-family: 'Courier New', monospace;
            }
            
            .description {
                color: #4a5568;
                font-style: italic;
                margin: 8px 0;
                padding: 8px;
                background-color: #f7fafc;
                border-radius: 6px;
            }
            
            .category {
                display: inline-block;
                color: #718096;
                font-size: 0.9em;
                padding: 4px 8px;
                background-color: #edf2f7;
                border-radius: 4px;
                margin: 8px 0;
            }
            
            strong {
                color: #2d3748;
                font-size: 1.1em;
                display: block;
                margin-bottom: 8px;
            }
            
            /* 스크롤바 스타일링 */
            ::-webkit-scrollbar {
                width: 8px;
                height: 8px;
            }
            
            ::-webkit-scrollbar-track {
                background: #f1f1f1;
                border-radius: 4px;
            }
            
            ::-webkit-scrollbar-thumb {
                background: #cbd5e0;
                border-radius: 4px;
            }
            
            ::-webkit-scrollbar-thumb:hover {
                background: #a0aec0;
            }
            
            /* 반응형 디자인 */
            @media (max-width: 768px) {
                body {
                    padding: 12px;
                }
                
                .section {
                    padding: 16px;
                }
                
                .section-title {
                    font-size: 24px;
                }
                
                .item {
                    padding-left: 12px;
                }
            }
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
        <script>
            function toggleContent(elementId) {
                var content = document.getElementById(elementId);
                var btn = document.getElementById('btn-' + elementId);
                if (content.style.display === 'none') {
                    content.style.display = 'block';
                    btn.textContent = '▼';
                } else {
                    content.style.display = 'none';
                    btn.textContent = '▶';
                }
            }
        </script>
    </head>
    <body>
    """
    
    # 각 섹션에 대해 HTML 생성
    for section, section_data in data.items():
        html += f'<div class="section">\n'
        html += f'<div class="section-title">{section}</div>\n'
        
        # roots 순서대로 처리
        for root in section_data.get('roots', []):
            items = section_data['tree'].get(root, [])
            if items:
                # 루트 항목 생성
                html += f'<div class="item">\n'
                html += f'<div class="item-header" onclick="toggleContent(\'{root}\')">'
                html += f'<span id="btn-{root}" class="toggle-btn">▶</span>{root}</div>\n'
                html += f'<div id="{root}" class="item-content">\n'
                
                # 하위 항목들 처리
                for item in sorted(items, key=lambda x: x.get('order', 0)):
                    korean_name = item.get('korean_name', '')
                    description = item.get('description', '')
                    category = item.get('category', '')
                    data_list = item.get('data', [])
                    
                    if data_list:
                        values_html = '<br>'.join([
                            f"값: {d.get('display_value', '')}, "
                            f"컨텍스트: {d.get('context', '')}, "
                            f"단위: {d.get('unit', '')}"
                            for d in data_list
                        ])
                    else:
                        values_html = "데이터 없음"
                    
                    html += f'<div class="item">\n'
                    html += f'<div><strong>{korean_name}</strong></div>\n'
                    html += f'<div class="description">{description}</div>\n'
                    html += f'<div class="category">카테고리: {category}</div>\n'
                    html += f'<div class="value">{values_html}</div>\n'
                    html += '</div>\n'
                
                html += '</div>\n'
                html += '</div>\n'
        
        html += '</div>\n'
    
    # HTML 템플릿 종료
    html += """
    </body>
    </html>
    """
    
    # HTML 파일 저장
    html_path = os.path.join(data_dir, 'xbrl_visualization_kr.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML 파일이 생성되었습니다: {html_path}")

if __name__ == "__main__":
    create_kr_html() 