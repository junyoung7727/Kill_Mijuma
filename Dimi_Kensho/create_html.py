import os
import json

def create_html_report():
    """한글 구조 기반 HTML 리포트 생성"""
    # kr_structure.json 읽기
    with open('Dimi_Kensho/data/structured_kr_data.json', 'r', encoding='utf-8') as f:
        kr_data = json.load(f)

    html = '''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XBRL 구조 분석</title>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            .header {
                background-color: #fff;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }
            .section {
                background-color: #fff;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            .section-title {
                font-size: 1.2em;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 2px solid #e9ecef;
            }
            .concept-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
                gap: 20px;
            }
            .concept-card {
                background-color: #fff;
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                border: 1px solid #e9ecef;
                transition: transform 0.2s;
            }
            .concept-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            .concept-header {
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 1px solid #e9ecef;
            }
            .korean-name {
                font-weight: bold;
                color: #1976d2;
                font-size: 1.1em;
                margin-bottom: 5px;
            }
            .tag-name {
                color: #757575;
                font-size: 0.9em;
                font-family: monospace;
            }
            .description {
                color: #666;
                font-size: 0.9em;
                margin-bottom: 15px;
                line-height: 1.4;
            }
            .data-value {
                background-color: #f8f9fa;
                padding: 10px;
                border-radius: 5px;
                margin-top: 10px;
            }
            .value {
                color: #2196f3;
                font-weight: bold;
                font-size: 1.1em;
            }
            .context {
                color: #757575;
                font-size: 0.9em;
                margin-top: 5px;
            }
            .category-badge {
                display: inline-block;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                margin-left: 10px;
                background-color: #e3f2fd;
                color: #1976d2;
            }
            .icon {
                margin-right: 8px;
                color: #1976d2;
            }
            .group-title {
                color: #666;
                font-size: 0.9em;
                margin: 10px 0;
                padding: 5px 0;
                border-bottom: 1px dashed #e9ecef;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><i class="fas fa-project-diagram icon"></i> XBRL 구조 분석</h1>
                <p>총 섹션 수: ''' + str(len(kr_data)) + '''</p>
            </div>
    '''
    
    for section_name, section_data in kr_data.items():
        html += f'''
            <div class="section">
                <div class="section-title">
                    <i class="fas fa-folder icon"></i>
                    {section_name}
                </div>
                <div class="concept-grid">
        '''
        
        for group_name, items in section_data.items():
            for item in items:
                html += f'''
                    <div class="concept-card">
                        <div class="concept-header">
                            <div class="korean-name">
                                {item.get('translation', {}).get('korean_name', '')}
                                <span class="category-badge">{item.get('translation', {}).get('category', '')}</span>
                            </div>
                            <div class="tag-name">{item.get('tag', '')}</div>
                        </div>
                        <div class="description">
                            {item.get('translation', {}).get('description', '')}
                        </div>
                '''
                
                if item.get('data'):
                    for data in item['data']:
                        html += f'''
                            <div class="data-value">
                                <div class="value">
                                    {data.get('display_value', '')} {data.get('unit', '')}
                                </div>
                                <div class="context">
                                    Context: {data.get('context', '')}<br>
                                    Decimals: {data.get('decimals', '')}
                                </div>
                            </div>
                        '''
                
                html += '''
                    </div>
                '''
        
        html += '''
                </div>
            </div>
        '''
    
    html += '''
        </div>
    </body>
    </html>
    '''
    
    # HTML 파일 저장
    with open('Dimi_Kensho/data/xbrl_visualization_kr.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("\nHTML 리포트가 생성되었습니다: Dimi_Kensho/data/xbrl_visualization_kr.html")

if __name__ == "__main__":
    create_html_report() 