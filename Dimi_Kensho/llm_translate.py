import json
from openai import OpenAI
from dotenv import load_dotenv
import os
from time import sleep
from typing import Optional
import time

load_dotenv()

def get_latest_context_data(data_list):
    """데이터 리스트에서 가장 최근 컨텍스트의 데이터만 반환"""
    if not data_list or not isinstance(data_list, list):
        return None
    
    # 먼저 'c-1' context 찾기
    c1_data = next((item for item in data_list 
                   if item.get('attributes', {}).get('contextref') == 'c-1'), None)
    if c1_data:
        return c1_data
    
    # 'c-1'이 없으면 가장 작은 숫자의 context 선택
    sorted_data = sorted(data_list, 
                       key=lambda x: int(x.get('attributes', {}).get('contextref', '').split('-')[-1]) 
                       if x.get('attributes', {}).get('contextref', '').split('-')[-1].isdigit() 
                       else float('inf'))
    
    return sorted_data[0] if sorted_data else None

def extract_all_tags(data_dir):
    """hierarchy.json에서 모든 태그를 순서대로 추출"""
    try:
        hierarchy_path = os.path.join(data_dir, 'hierarchy.json')
        print(f"\nJSON 파일 읽기: {hierarchy_path}")
        with open(hierarchy_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("\n데이터 구조:")
        for section in data.keys():
            print(f"- 섹션: {section}")
        
        tags_list = []
        filtered_hierarchy = {}
        
        for section, section_data in data.items():
            print(f"\n섹션 처리 중: {section}")
            filtered_hierarchy[section] = {
                "roots": section_data.get("roots", []),
                "tree": {}
            }
            
            tree_data = section_data.get("tree", {})
            print(f"트리 데이터 키: {list(tree_data.keys())}")
            
            for parent, items in tree_data.items():
                print(f"\n부모 태그 처리 중: {parent}")
                filtered_hierarchy[section]["tree"][parent] = []
                
                if not isinstance(items, list):
                    print(f"Warning: items is not a list for parent {parent}")
                    continue
                
                for item in items:
                    if not isinstance(item, dict):
                        print(f"Warning: item is not a dict: {item}")
                        continue
                    
                    concept = parent
                    print(f"태그 처리 중: {concept}")
                    
                    # 데이터에서 가장 작은 컨텍스트 번호 선택
                    context = ""
                    if "data" in item and item["data"]:
                        contexts = []
                        for d in item["data"]:
                            if isinstance(d, dict) and "context" in d:
                                ctx = d["context"]
                                if ctx.startswith("c-"):
                                    try:
                                        num = int(ctx.split("-")[1])
                                        contexts.append((num, ctx))
                                    except ValueError:
                                        continue
                        if contexts:
                            # 가장 작은 번호의 컨텍스트 선택
                            context = min(contexts, key=lambda x: x[0])[1]
                    
                    # 태그 정보 저장
                    tag_info = {
                        "concept": concept,
                        "tag": concept,
                        "context": context,
                        "section": section,
                        "parent": parent
                    }
                    
                    # 중복 방지를 위해 태그가 없을 때만 추가
                    if not any(t["tag"] == concept for t in tags_list):
                        tags_list.append(tag_info)
                        print(f"태그 추가됨: {concept} (컨텍스트: {context})")
                    
                    # 필터링된 계층 구조에 추가
                    filtered_item = {
                        "concept": concept,
                        "order": item.get("order", 0),
                        "data": item.get("data", [])
                    }
                    filtered_hierarchy[section]["tree"][parent].append(filtered_item)
        
        print(f"\n총 {len(tags_list)}개의 태그를 추출했습니다.")
        
        # 파일 저장
        filtered_path = os.path.join(data_dir, 'hierarchy_filtered.json')
        with open(filtered_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_hierarchy, f, indent=2, ensure_ascii=False)
        
        tags_path = os.path.join(data_dir, 'tags_for_translation.json')
        with open(tags_path, 'w', encoding='utf-8') as f:
            json.dump(tags_list, f, indent=2, ensure_ascii=False)
        
        return tags_list, filtered_hierarchy
        
    except Exception as e:
        print(f"태그 추출 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return [], {}

def get_llm_translations(tags_list, data_dir):
    """태그 리스트를 LLM으로 번역 (배치 처리)"""
    translations = {}
    
    # 이전 번역 결과가 있다면 로드
    translations_path = os.path.join(data_dir, 'translated_tags.json')
    if os.path.exists(translations_path):
        try:
            with open(translations_path, 'r', encoding='utf-8') as f:
                translations = json.load(f)
            print("기존 번역 데이터를 로드했습니다.")
        except:
            print("기존 번역 파일을 로드하는데 실패했습니다. 새로 시작합니다.")
    
    # OpenAI 클라이언트 초기화
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # 번역이 필요한 태그 수집
    tags_to_translate = []
    for tag_info in tags_list:
        tag = tag_info["tag"]
        if tag not in translations:
            tags_to_translate.append(tag_info)
    
    print(f"총 {len(tags_to_translate)}개의 태그를 번역해야 합니다.")
    
    # 배치 크기 설정
    batch_size = 40
    
    # 배치 단위로 처리
    for i in range(0, len(tags_to_translate), batch_size):
        batch = tags_to_translate[i:i + batch_size]
        print(f"\n배치 처리 중: {i+1}~{min(i+batch_size, len(tags_to_translate))} / {len(tags_to_translate)}")
        
        # 배치의 모든 태그를 하나의 프롬프트로 구성
        tags_prompt = "\n".join([
            f"{idx+1}. {tag_info['tag']} (섹션: {tag_info['section']}, 컨텍스트: {tag_info.get('context', '')})"
            for idx, tag_info in enumerate(batch)
        ])
        
        prompt = f"""당신은 재무제표 전문가입니다. 
다음 US-GAAP 태그들을 분석해주세요:

{tags_prompt}

각 태그에 대해 다음 정보를 JSON 배열 형식으로 제공해주세요:
1. tag: 원본 태그명 (입력된 순서대로)
2. korean_name: 이 항목의 공식적이고 전문적인 한글 명칭
3. description: 이 항목이 재무제표에서 가지는 의미와 중요성 (2-3줄로 상세히 설명)
4. category: 이 항목의 정확한 카테고리 (자산, 부채, 자본, 수익, 비용, 기타 중 하나)

응답은 다음과 같은 JSON 형식이어야 합니다:
{{
    "translations": [
        {{
            "tag": "첫번째태그",
            "korean_name": "한글명1",
            "description": "설명1",
            "category": "카테고리1"
        }},
        {{
            "tag": "두번째태그",
            "korean_name": "한글명2",
            "description": "설명2",
            "category": "카테고리2"
        }}
    ]
}}"""

        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "당신은 한국의 재무제표 및 회계 전문가입니다. 모든 설명은 한국어로 제공해주세요."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7
                )
                
                # JSON 응답 파싱
                response_data = json.loads(response.choices[0].message.content)
                print(response_data)
                batch_translations = response_data.get("translations", [])
                
                # 번역 결과를 translations 딕셔너리에 추가
                for translation in batch_translations:
                    tag = translation["tag"]
                    translations[tag] = {
                        "korean_name": translation["korean_name"],
                        "description": translation["description"],
                        "category": translation["category"]
                    }
                
                print(f"배치 번역 완료")
                
                # 중간 저장
                with open(translations_path, 'w', encoding='utf-8') as f:
                    json.dump(translations, f, indent=2, ensure_ascii=False)
                
                # API 레이트 리밋 방지
                time.sleep(1)
                break
                
            except Exception as e:
                retry_count += 1
                print(f"배치 번역 중 오류 발생 (시도 {retry_count}/{max_retries}): {str(e)}")
                if retry_count == max_retries:
                    # 배치의 각 태그에 대해 오류 처리
                    for tag_info in batch:
                        tag = tag_info["tag"]
                        translations[tag] = {
                            "korean_name": f"{tag}",
                            "description": "번역 중 오류가 발생했습니다",
                            "category": "기타"
                        }
                time.sleep(1)
    
    print("\n번역 완료!")
    print(f"총 {len(translations)}개의 태그가 번역되었습니다.")
    
    # 최종 결과 저장
    with open(translations_path, 'w', encoding='utf-8') as f:
        json.dump(translations, f, indent=2, ensure_ascii=False)
    
    return translations

def create_structured_json(translations, filtered_hierarchy, data_dir):
    """번역 결과와 필터링된 계층 구조를 결합하여 구조화된 JSON 생성"""
    structured_data = {}
    
    for section, section_data in filtered_hierarchy.items():
        structured_data[section] = {
            "roots": [],  # 실제 데이터가 있는 루트만 포함할 예정
            "tree": {}
        }
        
        # 각 루트 항목 처리
        for root in section_data["roots"]:
            items = section_data["tree"].get(root, [])
            valid_items = []
            
            for item in items:
                concept = item["concept"]
                data_list = item.get("data", [])
                
                # 가장 작은 컨텍스트 번호를 가진 데이터 선택
                selected_data = None
                min_context_num = float('inf')
                
                for d in data_list:
                    if isinstance(d, dict):
                        context = d.get('context', '')
                        if context.startswith('c-'):
                            try:
                                num = int(context.split('-')[1])
                                if num < min_context_num:
                                    min_context_num = num
                                    selected_data = d
                            except ValueError:
                                continue
                
                # 데이터가 있는 경우만 처리
                if selected_data:
                    # 번역 정보 가져오기
                    translation = translations.get(concept, {
                        "korean_name": concept,
                        "description": "번역 정보 없음",
                        "category": "기타"
                    })
                    
                    # 숫자 값을 표시 형식으로 변환
                    value = selected_data.get('value', 0)
                    if isinstance(value, (int, float)):
                        display_value = f"${value:,.2f}"
                    else:
                        display_value = str(value)
                    
                    processed_data = {
                        "value": value,
                        "display_value": display_value,
                        "context": selected_data.get('context', ''),
                        "unit": selected_data.get('unit', '')
                    }
                    
                    valid_items.append({
                        "concept": concept,
                        "korean_name": translation["korean_name"],
                        "description": translation["description"],
                        "category": translation["category"],
                        "order": item.get("order", 0),
                        "data": processed_data
                    })
            
            # 유효한 항목이 있는 경우만 트리에 추가
            if valid_items:
                structured_data[section]["tree"][root] = valid_items
                if root not in structured_data[section]["roots"]:
                    structured_data[section]["roots"].append(root)
        
        # 데이터가 없는 섹션 제거
        if not structured_data[section]["roots"]:
            del structured_data[section]
    
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