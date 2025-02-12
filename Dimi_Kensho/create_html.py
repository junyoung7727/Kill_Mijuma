import os
import json

def create_html_report(min_importance=5, report_mode=0):
    """한글 구조 기반 HTML 리포트 생성"""
    with open('Dimi_Kensho/data/structured_kr_data.json', 'r', encoding='utf-8') as f:
        kr_data = json.load(f)

    if report_mode == 1:
        allowed_sections = ["재무상태표", "현금흐름표", "손익계산서"]
        filtered_data = {}
        for section, subsections in kr_data.items():
            for keyword in allowed_sections:
                if keyword in section:
                    filtered_data[section] = subsections
                    break
        kr_data = filtered_data

    html = '''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XBRL 구조 분석 리포트</title>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            body { font-family: Arial, sans-serif; background-color: #f5f5f5; }
            .container { margin: 0 auto; width: 90%; max-width: 1200px; }
            .header { text-align: center; margin: 20px 0; padding: 20px; background: white; border-radius: 8px; }
            .section { margin-bottom: 30px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .subsection { margin: 15px 0; padding: 15px; border: 1px solid #eee; border-radius: 4px; }
            .item { padding: 15px; margin: 10px 0; background: #f8f9fa; border-radius: 4px; }
            .importance { font-weight: bold; color: #d32f2f; }
            .value-display { margin: 10px 0; padding: 10px; background: #e3f2fd; border-radius: 4px; }
            .value { font-size: 1.1em; color: #1976d2; font-weight: bold; }
            .meta-info { color: #666; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>XBRL 구조 분석 리포트</h1>
            </div>
    '''

    for section, subsections in kr_data.items():
        html += f'<div class="section"><h2>{section}</h2>'
        for subsection, items in subsections.items():
            html += f'<div class="subsection"><h3>{subsection}</h3>'
            for item in items:
                importance = item.get('importance_score', 0)
                if importance >= min_importance:
                    concept = item.get('concept', '')
                    translation = item.get('translation', {})
                    korean_name = translation.get('korean_name', '')
                    description = translation.get('description', '')
                    
                    html += '<div class="item">'
                    html += f'<div class="meta-info">태그: {concept}</div>'
                    html += f'<div><strong>{korean_name}</strong></div>'
                    html += f'<div class="meta-info">설명: {description}</div>'
                    html += f'<div class="importance">중요도: {importance}</div>'
                    
                    # 데이터 값 표시 (한글 키값 사용)
                    if 'data' in item:
                        # 맥락별로 데이터 그룹화
                        context_groups = {}
                        for data_point in item['data']:
                            context = data_point.get('맥락_분류', '기본값')
                            if context not in context_groups:
                                context_groups[context] = []
                            context_groups[context].append(data_point)
                        
                        # 각 맥락 그룹별로 데이터 표시
                        for context, data_points in context_groups.items():
                            html += f'<div class="context-group"><h4>{context}</h4>'
                            for data_point in data_points:
                                html += '<div class="value-display">'
                                value = data_point.get('값', '')
                                unit = data_point.get('단위', '')
                                decimals = data_point.get('소수점', '')
                                members = data_point.get('멤버', [])
                                period = data_point.get('기간', {})
                                
                                # 값과 단위 표시
                                if value and unit:
                                    if decimals and decimals.startswith('-'):
                                        try:
                                            value = str(int(value) / (10 ** abs(int(decimals))))
                                        except ValueError:
                                            pass
                                    html += f'<div class="value">{value} {unit.upper()}</div>'
                                
                                # 멤버 정보 표시
                                if members:
                                    html += '<div class="meta-info">멤버: ' + ', '.join(members) + '</div>'
                                
                                # 기간 정보 표시
                                if period:
                                    date = period.get('date', '')
                                    if date:
                                        html += f'<div class="meta-info">날짜: {date}</div>'
                                
                                html += '</div>'
                            html += '</div>'
                    
                    html += '</div>'
            html += '</div>'
        html += '</div>'

    html += '''
        </div>
    </body>
    </html>
    '''

    output_file = 'Dimi_Kensho/data/xbrl_visualization_kr.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\nHTML 리포트가 생성되었습니다: {output_file}")

if __name__ == "__main__":
    create_html_report() 