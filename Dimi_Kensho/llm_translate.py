import json
from openai import OpenAI
from dotenv import load_dotenv
import os
from time import sleep
from typing import Optional
import time
from datetime import datetime

load_dotenv()

def get_latest_context_data(data_list, data_dir):
    """데이터 리스트에서 가장 최근 3개월 기간의 데이터만 반환"""
    if not data_list or not isinstance(data_list, list):
        return None
    
    # context_data.json 파일 읽기
    context_file = os.path.join(data_dir, 'context_data.json')
    try:
        with open(context_file, 'r', encoding='utf-8') as f:
            context_data = json.load(f)
    except Exception as e:
        print(f"Error: context_data.json 파일을 읽을 수 없습니다 - {str(e)}")
        return None
    
    # 3개월(분기) 데이터만 필터링
    quarterly_data = []
    for item in data_list:
        context_id = item.get('context')
        if context_id in context_data:
            context_info = context_data[context_id]
            if context_info['type'] == 'period':
                start_date = datetime.strptime(context_info['start_date'], '%Y-%m-%d')
                end_date = datetime.strptime(context_info['end_date'], '%Y-%m-%d')
                duration = (end_date - start_date).days
                
                # 약 3개월(90일) 기간의 데이터만 선택
                if 85 <= duration <= 95 and item.get('value'):
                    quarterly_data.append({
                        'item': item,
                        'end_date': end_date
                    })
    
    # 데이터가 없으면 None 반환
    if not quarterly_data:
        return None
    
    # 가장 최근 분기 데이터 선택
    latest_data = max(quarterly_data, key=lambda x: x['end_date'])
    return latest_data['item']

def extract_all_tags(hierarchy):
    """계층 구조에서 값이 있는 태그만 추출"""
    tags = set()
    
    def extract_from_node(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "concept" in item:
                            # data가 있고, 그 중에 value가 있는 데이터가 있는 경우만 추가
                            if item.get("data") and any(d.get('value') for d in item["data"]):
                                tag = item["concept"]
                                if ':' in tag:
                                    tag = tag.split(':')[-1]
                                tags.add(tag)
                        extract_from_node(item)
                else:
                    extract_from_node(value)
        elif isinstance(node, list):
            for item in node:
                extract_from_node(item)
    
    for section_data in hierarchy.values():
        extract_from_node(section_data)
    
    return list(tags)

def get_llm_translations(tags, data_dir):
    """LLM을 사용하여 태그 번역"""
    translations_path = os.path.join(data_dir, 'translated_tags.json')
    
    # 이미 번역된 태그 불러오기
    existing_translations = {}
    if os.path.exists(translations_path):
        with open(translations_path, 'r', encoding='utf-8') as f:
            existing_translations = json.load(f)
    
    # 새로운 태그만 번역
    new_tags = [tag for tag in tags if tag not in existing_translations]
    
    if new_tags:
        print(f"\n새로운 태그 {len(new_tags)}개 번역 중...")
        
        # 태그를 50개씩 나누어 처리
        batch_size = 40
        for i in range(0, len(new_tags), batch_size):
            batch_tags = new_tags[i:i + batch_size]
            
            # 프롬프트 생성
            prompt = "다음 XBRL 태그들을 한국어로 번역해주세요. 태그의 CamelCase를 분석하여 의미를 파악하고, 금융/회계 용어에 맞게 전문적으로 번역해주세요:\n\n"
            for tag in batch_tags:
                prompt += f"- {tag}\n"
            
            try:
                # LLM API 호출
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                
                # 응답 파싱 및 저장
                translations = parse_llm_response(response.choices[0].message.content)
                existing_translations.update(translations)
                
                # 중간 저장
                with open(translations_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_translations, f, indent=2, ensure_ascii=False)
                
                print(f"배치 {i//batch_size + 1} 번역 완료")
                
            except Exception as e:
                print(f"Error: 번역 중 오류 발생 - {str(e)}")
                continue
    
    return existing_translations

def create_structured_json(translations, hierarchy, data_dir):
    """번역 결과와 계층 구조를 결합하여 구조화된 JSON 생성"""
    structured_data = {}
    
    for section, section_data in hierarchy.items():
        section_items = {}
        
        # 섹션의 각 태그 처리
        for tag, items in section_data.items():
            if isinstance(items, list):
                structured_items = []
                for item in items:
                    if isinstance(item, dict) and "concept" in item:
                        # 최신 컨텍스트 데이터만 가져오기
                        latest_data = get_latest_context_data(item.get("data", []), data_dir)
                        
                        # 값이 있는 최신 데이터만 처리
                        if latest_data and latest_data.get('value'):
                            concept = item["concept"]
                            # 네임스페이스 제거
                            if ':' in concept:
                                concept = concept.split(':')[-1]
                            
                            structured_item = {
                                "tag": concept,
                                "translation": translations.get(concept, ""),
                                "data": [latest_data]  # 최신 데이터만 포함
                            }
                            structured_items.append(structured_item)
                
                # 구조화된 아이템이 있는 경우만 추가
                if structured_items:
                    section_items[tag] = structured_items
        
        # 섹션에 데이터가 있는 경우만 추가
        if section_items:
            structured_data[section] = section_items
    
    # 구조화된 데이터를 파일로 저장
    structured_path = os.path.join(data_dir, 'structured_kr_data.json')
    with open(structured_path, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=2, ensure_ascii=False)
    
    return structured_data

if __name__ == "__main__":
    tags_list, filtered_hierarchy = extract_all_tags()
    if tags_list:
        translations = get_llm_translations(tags_list)
        structured_data = create_structured_json(translations, filtered_hierarchy) 