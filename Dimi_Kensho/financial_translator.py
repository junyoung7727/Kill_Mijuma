import json
import os
from typing import Dict, List, Optional
import openai
from datetime import datetime, timedelta
import traceback
import os
from dotenv import load_dotenv
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from collections import Counter

load_dotenv()

class FinancialTranslator:
    def __init__(self, data_dir: str, model: str = "gpt-4o-mini"):
        self.data_dir = data_dir
        self.model = model
        self.hierarchy_data = None
        self.translated_data = {}
        self.tag_translations_cache = {}
        self.member_translations_cache = {}
        self.context_categories_cache = {}
        self.section_translations_cache = {}
    
    def remove_namespace(self, tag):
        """태그에서 네임스페이스 제거 및 정제
        
        Args:
            tag (str): 원본 태그
            
        Returns:
            str: 정제된 태그 이름
        """
        # 네임스페이스 패턴 정의
        ns_patterns = {
            'standard': ['us-gaap', 'usgaap', 'us', 'gaap', 'dei', 'srt'],
            'international': ['ifrs', 'country', 'currency'],
            'other': ['invest', 'risk', 'ref', 'ecd']
        }
        
        # 1. 콜론(:)으로 분리된 네임스페이스 처리
        if ':' in tag:
            ns, name = tag.split(':', 1)
            return name.lower()
        
        # 2. 언더스코어(_)로 분리된 네임스페이스 처리
        if '_' in tag:
            parts = tag.split('_', 1)
            for category, patterns in ns_patterns.items():
                if parts[0].lower() in patterns:
                    return parts[1].lower()
        
        # 3. 하이픈(-)으로 분리된 네임스페이스 처리
        if '-' in tag:
            parts = tag.split('-', 1)
            if parts[0].lower() in ns_patterns['standard']:
                return parts[1].lower()
        
        return tag.lower()

    def _load_hierarchy(self) -> dict:
        """계층 구조 데이터를 로드합니다."""
        try:
            file_path = f"{self.data_dir}\hierarchy.json"
            print(f"데이터 파일 경로: {file_path}")
            if not os.path.exists(file_path):

                print(f"파일이 존재하지 않습니다: {file_path}")
                return {}
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"데이터 로드 중 오류: {str(e)}")
            traceback.print_exc()
            return {}

    def _call_llm(self, prompt: str, system_msg: str) -> dict:
        """최신 openai API 인터페이스를 사용하여 LLM을 호출합니다."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ]
            
            print(f"LLM 요청 - System: {system_msg}")  # 디버깅용
            print(f"LLM 요청 - Prompt: {prompt}")  # 디버깅용
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}  # JSON 응답 형식 강제
            )
            content = response.choices[0].message.content
            print(f"LLM 원본 응답: {content}")  # 디버깅용

            try:
                # JSON 파싱 시도
                return json.loads(content)
            except json.JSONDecodeError as e:
                print(f"JSON 파싱 오류: {str(e)}")
                # JSON 형식이 아닌 경우, <json> 태그 찾기 시도
                match = re.search(r'<json>\s*(.*?)\s*</json>', content, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        print("JSON 태그 내용 파싱 실패")
                
                print("기본 번역으로 대체됩니다.")
                return {}
            
        except Exception as e:
            print(f"LLM 호출 중 오류: {str(e)}")
            traceback.print_exc()
            return {}

    def _translate_member_names_batch(self, all_members: list) -> dict:
        """멤버 이름들을 배치 처리하여 번역합니다."""
        seen = set()
        unique_members = []
        for m in all_members:
            if m and m not in seen:
                seen.add(m)
                unique_members.append(m)
        if unique_members:
            batch_size = 100
            for i in range(0, len(unique_members), batch_size):
                batch = unique_members[i:i+batch_size]
                prompt = (
                    "다음 재무제표 멤버 이름들을 한국어로 번역해주세요. 한국 K-IFRS 기준의 직관적인 용어를 사용합니다. 뒤에 멤버라는 것은 제외하고 앞의 이름만 한국어로 쉽게 바꿔주세요.\n"
                    "응답은 반드시 아래 JSON 형식으로 작성해주세요:\n\n"
                    "<json>\n"
                    '{ "translations": { "member1": "번역1" } }\n'
                    "</json>\n\n"
                    f"멤버 이름들:\n{json.dumps(batch, ensure_ascii=False, indent=2)}"
                )
                system_msg = "재무제표 멤버 이름을 번역하는 전문가입니다."
                result = self._call_llm(prompt, system_msg)
                new_translations = result.get('translations', {})
                self.member_translations_cache.update(new_translations)
                print(f"멤버 번역 완료: {len(batch)}개 처리 (배치 처리)")
        return {m: self.member_translations_cache.get(m, m) for m in all_members}

    def _analyze_data_contexts_batch(self, tag_members_map: dict) -> dict:
        """태그별 멤버 정보를 기반으로 맥락(카테고리)을 분석합니다."""
        if not tag_members_map:
            return {}
        uncached_tags = {tag: members for tag, members in tag_members_map.items()
                         if tag not in self.context_categories_cache}
        if uncached_tags:
            prompt = (
                "다음 재무제표 태그들과 관련 멤버 리스트를 분석하여, 각 태그에 대해 일관된 맥락(카테고리)를 결정해주세요.\n"
                "응답은 아래 JSON 형식으로 작성해주세요:\n\n"
                "<json>\n"
                '{ "contexts": [ {"tag": "tag1", "category": "맥락 분류1"} ] }\n'
                "</json>\n"
                "분석할 태그와 멤버 리스트 정보:\n"

            )
            items = []
            for tag, members_lists in uncached_tags.items():
                items.append({"tag": tag, "members_lists": members_lists})
            prompt += json.dumps(items, ensure_ascii=False, indent=2)
            system_msg = "재무제표 데이터의 맥락을 분석하는 전문가입니다."
            result = self._call_llm(prompt, system_msg)
            for context in result.get("contexts", []):
                tag = context.get("tag")
                category = context.get("category", "")
                if tag:
                    self.context_categories_cache[tag] = category
            print(f"맥락 분석 완료: {len(uncached_tags)}개 태그 (배치 처리)")
        return {tag: self.context_categories_cache.get(tag, "") for tag in tag_members_map.keys()}

    def _translate_members(self, members: list, tag_name: str, tag_translation: str) -> dict:
        """
        멤버 리스트를 번역합니다.
        태그 이름과 번역을 컨텍스트로 제공하여 더 자연스러운 번역을 유도합니다.
        """
        if not members:
            return {}

        members_prompt = f"""다음 재무제표 항목의 멤버들을 한국어로 번역해주세요.
        
        항목 정보:
        - 태그 이름: {tag_name}
        - 태그 번역: {tag_translation}
        
        다음 규칙을 반드시 따라주세요:
        1. 위 태그의 맥락을 고려하여 자연스러운 한국어 용어로 번역
        2. 한국 재무제표에서 일반적으로 사용되는 용어를 사용
        3. 직관적이고 이해하기 쉬운 용어로 번역
        4. 불필요한 설명이나 수식어는 제외
        5. 기술적인 용어는 한국 투자자들이 이해하기 쉬운 용어로 번역
        
        번역할 멤버:
        {members}
        """
        
        translations = self._translate_text_batch(members_prompt)
        return dict(zip(members, translations))

    def _translate_members_batch(self, members_info: list) -> dict:
        """멤버 이름들을 배치로 번역합니다."""
        translations = {}
        
        # 입력이 딕셔너리인 경우 처리
        if isinstance(members_info, dict):
            members_info = [members_info]
        
        # 배치 크기 설정
        BATCH_SIZE = 50
        
        # 멤버와 태그 정보를 함께 모음
        all_members_with_context = []
        for member_dict in members_info:
            try:
                if not isinstance(member_dict, dict):
                    print(f"잘못된 입력 형식 무시: {member_dict}")
                    continue
                    
                tag_name = member_dict.get('tag_name', '')
                tag_translation = member_dict.get('tag_translation', '')
                members = member_dict.get('members', [])
                
                if not isinstance(members, list):
                    print(f"잘못된 members 형식 무시: {members}")
                    continue

                for member in members:
                    if isinstance(member, str):
                        all_members_with_context.append({
                            'member': member,
                            'tag': tag_name,
                            'tag_translation': tag_translation
                        })
                    else:
                        print(f"잘못된 멤버 형식 무시: {member}")
            
            except Exception as e:
                print(f"멤버 정보 수집 중 오류: {str(e)}")
                continue
        
        # 배치 단위로 처리
        for i in range(0, len(all_members_with_context), BATCH_SIZE):
            batch = all_members_with_context[i:i + BATCH_SIZE]
            
            members_prompt = """다음 재무제표의 세그먼트(부문) 및 멤버 이름들을 한국어로 번역해주세요.

응답은 반드시 아래 JSON 형식으로 작성해주세요:

<json>
{
    "translations": {
        "member1": "번역1",
        "member2": "번역2"
    }
}
</json>

번역 규칙:
1. 세그먼트/부문 관련:
   - XXXSegmentMember → "XX 부문"으로 번역 (예: AsiaSegmentMember → "아시아 부문")
   - 지역 세그먼트는 일반적인 한국어 지역명 사용 (예: GreaterChina → "대중화권")
   - Product/Service는 "제품"/"서비스"로 번역

2. 일반 멤버 관련:
   - Member 접미사는 번역하지 않고 제외
   - 일반적인 재무용어는 한국 회계기준 용어 사용
   - 제품명이나 브랜드명은 한국에서 통용되는 명칭 사용

3. 맥락 고려:
   - 태그: {tag_name}
   - 태그 번역: {tag_translation}
   이 태그의 맥락을 고려하여 자연스러운 번역

번역할 멤버 목록:
"""
            
            # 각 멤버의 상세 정보 추가
            for item in batch:
                members_prompt += f"\n- {item['member']}"
                members_prompt += f"\n  (태그: {item['tag']} → {item['tag_translation']})"
            
            # LLM을 통한 번역 수행
            system_msg = "재무제표 세그먼트와 멤버 이름을 번역하는 전문가입니다. 한국 K-IFRS 기준의 용어를 사용합니다."
            result = self._call_llm(members_prompt, system_msg)
            
            # 번역 결과 처리
            if isinstance(result, dict) and 'translations' in result:
                translations.update(result['translations'])
            
            print(f"배치 처리 완료: {len(batch)}개 멤버")
        
        print(f"전체 멤버 번역 완료: {len(translations)}개")
        return translations

    def _translate_batch(self, items: list) -> list:
        try:
            # 태그 번역
            tags = [item['concept'] for item in items]
            tags_prompt = f"""다음 재무제표 항목들을 한국어로 번역하고 중요도 점수를 매겨주세요.

응답은 반드시 아래 JSON 형식으로 작성해주세요:

<json>
{{
    "translations": {{
        "tag1": {{
            "korean_name": "번역1",
            "importance": 5  // 1-5 점수
        }},
        "tag2": {{
            "korean_name": "번역2",
            "importance": 3
        }}
    }}
}}
</json>
투자자에게 중요한 정보가 될수록 높은 점수를 매겨겨 1~5점까지 중요도 점수를 메겨주세요.


다음 규칙을 반드시 따라주세요:
1. 한국 K-IFRS 기준의 공식 용어를 우선적으로 사용
2. 공식 용어가 없는 경우, 한국 재무제표에서 일반적으로 사용되는 직관적인 용어로 번역
3. 번역시 다음 용어들은 일관되게 사용:
   - Revenue → 매출액
   - Cost of Revenue/Sales → 매출원가
   - Gross Profit → 매출총이익
   - Operating Income/Loss → 영업이익/손실
   - Net Income/Loss → 당기순이익/손실
4. 번역문은 간단명료하게, 불필요한 설명이나 수식어 제외
5. 기술적인 용어는 한국 투자자들이 이해하기 쉬운 용어로 번역

번역할 태그:
{', '.join(tags)}
"""
            
            system_msg = "재무제표 용어를 번역하는 전문가입니다."
            tag_translations_result = self._call_llm(tags_prompt, system_msg)
            
            # 응답 형식 검증 및 처리
            tag_translations_dict = {}
            if isinstance(tag_translations_result, dict):
                translations = tag_translations_result.get('translations', {})
                if isinstance(translations, dict):
                    tag_translations_dict = translations
            
            # 태그별로 멤버 정보 수집
            members_info = []
            for item in items:
                tag_name = item['concept']
                tag_translation = tag_translations_dict.get(tag_name, '')
                
                # 해당 태그의 모든 멤버 수집
                members_set = set()
                for data_point in item['data']:
                    if data_point.get('멤버'):
                        members_set.update(data_point['멤버'])
                
                if members_set:
                    members_info.append({
                        'tag_name': tag_name,
                        'tag_translation': tag_translation,
                        'members': list(members_set)
                    })
            
            # 멤버 배치 번역 수행
            member_translations = {}
            if members_info:
                member_translations = self._translate_members_batch(members_info)
                print(f"멤버 번역 완료: {len(member_translations)}개")
            
            # 번역 결과 적용
            translated_items = []
            for item in items:
                tag_name = item['concept']
                translation_info = tag_translations_dict.get(tag_name, {})
                
                translated_item = {
                    'section': item['section'],
                    'subsection': item.get('subsection', ''),
                    'tag': tag_name,
                    'translation': {
                        'korean_name': translation_info.get('korean_name', ''),
                        'importance': translation_info.get('importance', 1)  # 기본값 1
                    },
                    'data': []
                }
                
                # 데이터 포인트 복사 및 멤버 번역 적용
                for data_point in item['data']:
                    translated_point = data_point.copy()
                    if data_point.get('멤버'):
                        translated_point['멤버_번역'] = [
                            member_translations.get(member, member)
                            for member in data_point['멤버']
                        ]
                    translated_item['data'].append(translated_point)
                
                translated_items.append(translated_item)
            
            return translated_items
        
        except Exception as e:
            print(f"배치 번역 중 오류: {str(e)}")
            traceback.print_exc()
            return []

    def _translate_section_names_batch(self, sections: list) -> dict:
        """섹션 이름을 배치로 번역합니다."""
        if not sections:
            return {}
        
        # 표준 섹션 매핑 (소문자로 통일)
        standard_sections = {
            'balance sheet': '재무상태표',
            'statement of financial position': '재무상태표',
            'income statement': '포괄손익계산서',
            'statement of comprehensive income': '포괄손익계산서',
            'profit and loss': '포괄손익계산서',
            'cash flow': '현금흐름표',
            'statement of cash flows': '현금흐름표'
        }
        
        # 먼저 표준 섹션 매핑 확인
        result = {}
        sections_to_translate = []
        for section in sections:
            section_lower = section.lower()
            if section_lower in standard_sections:
                result[section] = {'korean_name': standard_sections[section_lower]}
            else:
                sections_to_translate.append(section)
        
        # 나머지 섹션만 LLM으로 번역
        if sections_to_translate:
            prompt = f"""재무제표 섹션 이름을 한국어로 번역해주세요. 
            응답은 반드시 아래 JSON 형식으로 작성해주세요:
            
            <json>
            {{
                "translations": {{
                    "section1": "번역1",
                    "section2": "번역2"
                }}
            }}
            </json>
            
            다음 규칙을 반드시 따라주세요:
            1. 한국 재무제표에서 일반적으로 사용되는 용어를 사용하여 번역
            2. 번역문은 간단명료하게 작성
            3. 불필요한 설명이나 수식어는 제외

            번역할 섹션 이름:
            {', '.join(sections_to_translate)}
            """
            
            system_msg = "재무제표 섹션 이름을 한국어로 번역하는 전문가입니다."
            response = self._call_llm(prompt, system_msg)
            
            # 응답 형식 검증 및 처리
            if isinstance(response, dict):
                translations = response.get('translations', {})
                if isinstance(translations, dict):
                    for section in sections_to_translate:
                        result[section] = {
                            'korean_name': translations.get(section, section)
                        }
        
        return result

    def _translate_section_name(self, section: str) -> str:
        """섹션 이름 번역
        첫 페이지는 번역하지 않고, 주요 재무제표는 표준 용어를 사용합니다.
        """
        # 첫 페이지 번역 제외
        if "cover" in section.lower() or "first page" in section.lower():
            return section
        
        # 주요 재무제표 표준 용어 매핑
        standard_statements = {
            "balance sheet": "재무상태표",
            "statement of financial position": "재무상태표",
            "income statement": "포괄손익계산서",
            "statement of comprehensive income": "포괄손익계산서",
            "profit and loss": "포괄손익계산서",
            "cash flow": "현금흐름표",
            "statement of cash flows": "현금흐름표"
        }
        
        # 섹션 이름을 소문자로 변환하여 비교
        section_lower = section.lower()
        for eng, kor in standard_statements.items():
            if eng in section_lower:
                return kor
            
        # 그 외의 경우 LLM을 통한 번역
        prompt = (
            "다음 재무제표 섹션 이름을 한국어로 번역해주세요.\n"
            "응답은 반드시 아래 JSON 형식으로 작성해주세요:\n\n"
            "<json>\n"
            "{\n"
            '  "translation 섹션션": "번역된 이름"\n'
            "}\n"
            "</json>\n\n"
            f"섹션 이름: {section}"
        )
        
        system_msg = "재무제표 섹션 이름을 한국어로 번역하는 전문가입니다."
        result = self._call_llm(prompt, system_msg)
        
        return result.get('translation', section)

    def _filter_and_translate(self) -> dict:
        filtered_data = {}
        if not self.hierarchy_data:
            print("계층 데이터가 없습니다.")
            return filtered_data

        # 최신 컨텍스트 추출
        latest_contexts = self._extract_latest_context()
        latest_context_ids = {ctx['id'].strip().lower() for ctx in latest_contexts}
        print(f"최신 컨텍스트 ID: {latest_context_ids}")

        items_to_translate = []
        
        # 각 섹션을 순회
        for section_key, section_value in self.hierarchy_data.items():
            section_lists = list(section_value.values())
            if not section_lists:
                continue
            
            for section_list in section_lists:
                for item in section_list:
                    tag = item.get('concept')
                    if not tag or 'Abstract' in tag:
                        continue

                    # 중복 제거를 위한 데이터 포인트 해시 세트
                    unique_data_points = set()
                    filtered_data_points = []
                    
                    for data_point in item.get('data', []):
                        context_ref = data_point.get('컨텍스트', '').strip().lower()
                        if context_ref in latest_context_ids:
                            # 데이터 포인트를 해시 가능한 형태로 변환
                            data_point_key = (
                                data_point.get('값'),
                                data_point.get('단위'),
                                data_point.get('소수점'),
                                data_point.get('컨텍스트'),
                                tuple(data_point.get('축', [])),
                                tuple(data_point.get('멤버', [])),
                                data_point.get('기간', {}).get('start_date'),
                                data_point.get('기간', {}).get('end_date')
                            )
                            
                            # 중복되지 않은 데이터 포인트만 추가
                            if data_point_key not in unique_data_points:
                                unique_data_points.add(data_point_key)
                                filtered_data_points.append(data_point)

                    if filtered_data_points:
                        items_to_translate.append({
                            'section': section_key,
                            'subsection': "",
                            'concept': tag,
                            'data': filtered_data_points
                        })

        print(f"번역 대상 태그 수: {len(items_to_translate)}")
        if not items_to_translate:
            print("현재 조건에 맞는 번역 대상이 없습니다.")
            return filtered_data

        # 섹션 이름 번역
        sections = list({item['section'] for item in items_to_translate})
        section_translations = self._translate_section_names_batch(sections)
        
        # 배치 처리로 번역 수행
        batch_size = 200
        for i in range(0, len(items_to_translate), batch_size):
            batch = items_to_translate[i:i + batch_size]
            translated_batch = self._translate_batch(batch)
            
            for item in translated_batch:
                # 섹션 이름 번역 적용
                original_section = item['section']
                translated_section = section_translations.get(original_section, {
                    'korean_name': original_section
                })
                
                section_key = translated_section['korean_name']
                
                if section_key not in filtered_data:
                    filtered_data[section_key] = {}
                    
                subsection = item.get('subsection', "")
                if subsection not in filtered_data[section_key]:
                    filtered_data[section_key][subsection] = []
                    
                filtered_data[section_key][subsection].append({
                    'tag': item['tag'],
                    'translation': item['translation'],
                    'data': item['data']
                })
        
        return filtered_data

    def translate_recent_statements(self) -> None:
        """전체 재무제표 번역을 실행합니다."""
        try:
            print("\n재무제표 번역 시작...")
            # 캐시 초기화
            self.tag_translations_cache = {}
            self.member_translations_cache = {}
            self.context_categories_cache = {}
            self.section_translations_cache = {}
            
            self.hierarchy_data = self._load_hierarchy()
            if not self.hierarchy_data:
                print("hierarchy 데이터 로드 실패")
                output_file = f"{self.data_dir}/structured_kr_data.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                return
            
            self.translated_data = self._filter_and_translate()
            output_file = f"{self.data_dir}/structured_kr_data.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.translated_data, f, ensure_ascii=False, indent=2)
            print(f"\n번역 완료: {output_file}")
            print("\n번역 통계:")
            print(f"- 태그 번역 캐시: {len(self.tag_translations_cache)}개")
            print(f"- 멤버 번역 캐시: {len(self.member_translations_cache)}개")
            print(f"- 맥락 분석 캐시: {len(self.context_categories_cache)}개")
            print(f"- 섹션 번역 캐시: {len(self.section_translations_cache)}개")
        except Exception as e:
            print(f"번역 실행 중 오류: {str(e)}")

    def _extract_latest_context(self, context_file: str = "context_data.json") -> list:
        """
        context.json에서 '최신' 컨텍스트를 추출합니다.
        
        새로운 규칙:
          1) period 타입의 start_date를 전부 집계하여, 등장 횟수가 10번 이상인 start_date만 후보로 삼습니다.
          2) 해당 후보 중 가장 늦은 날짜(최대값)를 가진 start_date를 '기준 start_date'로 선택합니다.
          3) 이 '기준 start_date'를 가진 period 컨텍스트들 중에서 (가장 end_date가 늦은) 하나를 '기준 컨텍스트'로 삼습니다.
          4) 기준 컨텍스트의 start_date부터 end_date + 10일까지를 '기준 구간'으로 잡습니다.
          5) 기준 구간에 포함되는 instant 타입(date가 [start_date, end_date+10일] 범위)에 해당하면 함께 포함합니다.
          6) 또한, 기준 구간 안에 start_date나 end_date가 걸치는 다른 period 컨텍스트도 포함합니다.
          
        반환값: 위 규칙에 따라 선정된 컨텍스트들의 목록(딕셔너리 형태)입니다.
        """
        try:
            file_path = os.path.join(self.data_dir, context_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                contexts = json.load(f)
        except Exception as e:
            print(f"컨텍스트 파일 로드 오류: {str(e)}")
            return []

        # period와 instant를 분류
        period_contexts = {}
        instant_contexts = {}
        for ctx_id, ctx_data in contexts.items():
            ctype = ctx_data.get("type", "")
            if ctype == "period":
                period_contexts[ctx_id] = ctx_data
            elif ctype == "instant":
                instant_contexts[ctx_id] = ctx_data

        # 1) period 컨텍스트에서 start_date 집계
        start_date_counter = Counter()
        for ctx_id, data in period_contexts.items():
            start_date_str = data.get("start_date")
            if start_date_str:
                start_date_counter[start_date_str] += 1

        # 10번 이상 등장한 start_date만 추출
        candidate_dates = [sd for sd, count in start_date_counter.items() if count >= 10]
        if not candidate_dates:
            print("start_date가 10번 이상 반복되는 케이스가 없습니다.")
            return []

        # 2) 가장 늦은 날짜(가장 뒤) start_date를 선택
        candidate_dates_dt = [datetime.strptime(sd, "%Y-%m-%d") for sd in candidate_dates]
        baseline_start_date_dt = max(candidate_dates_dt)  # 가장 늦은 start_date
        baseline_start_date_str = baseline_start_date_dt.strftime("%Y-%m-%d")

        # 3) 이 날짜를 가진 period 중 end_date가 가장 늦은 컨텍스트 찾기
        baseline_periods = []
        for ctx_id, data in period_contexts.items():
            if data.get("start_date") == baseline_start_date_str:
                baseline_periods.append((ctx_id, data))

        if not baseline_periods:
            print("해당 기준 start_date를 가진 period 컨텍스트가 없습니다.")
            return []

        # 여러 개일 경우 end_date가 가장 늦은 것을 기준으로 선택
        def parse_end_date(ctx_data):
            return datetime.strptime(ctx_data.get("end_date"), "%Y-%m-%d")
        
        baseline_period_id, baseline_period_data = max(
            baseline_periods,
            key=lambda x: parse_end_date(x[1])
        )

        # 기준 구간 설정: [base_start, base_end + 10일]
        base_start_dt = datetime.strptime(baseline_period_data["start_date"], "%Y-%m-%d")
        base_end_dt = datetime.strptime(baseline_period_data["end_date"], "%Y-%m-%d")
        extended_end_dt = base_end_dt + timedelta(days=10)

        # 4) instant 타입 중 날짜가 위 구간 [base_start_dt, base_end_dt+10]에 포함되는 것 추출
        included_instants = []
        for ctx_id, data in instant_contexts.items():
            try:
                inst_dt = datetime.strptime(data["date"], "%Y-%m-%d")
                if base_start_dt <= inst_dt <= extended_end_dt:
                    included_instants.append(ctx_id)
            except Exception as e:
                print(f"instant 날짜 파싱 오류(컨텍스트 {ctx_id}): {str(e)}")
                continue

        # 5) 기준 구간 안에 start_date 혹은 end_date가 걸치는 period 컨텍스트도 포함
        included_periods = []
        for ctx_id, data in period_contexts.items():
            try:
                sd_dt = datetime.strptime(data["start_date"], "%Y-%m-%d")
                ed_dt = datetime.strptime(data["end_date"], "%Y-%m-%d")
                # start_date나 end_date 중 하나라도 [base_start_dt, extended_end_dt]에 걸치면 포함
                if (base_start_dt <= sd_dt <= extended_end_dt) or (base_start_dt <= ed_dt <= extended_end_dt):
                    included_periods.append(ctx_id)
            except Exception as e:
                print(f"period 날짜 파싱 오류(컨텍스트 {ctx_id}): {str(e)}")
                continue

        # 6) 최종 결과(중복 제거) -> dict 형태로 반환
        final_ids = set()
        # 기준 period 컨텍스트
        final_ids.add(baseline_period_id)
        # 포함된 instant
        final_ids.update(included_instants)
        # 포함된 period
        final_ids.update(included_periods)

        latest_contexts = []
        for cid in final_ids:
            # 원본 딕셔너리에서 그대로 가져오되, 필요한 필드만 정리 가능
            ctx_copy = contexts[cid].copy()
            ctx_copy["id"] = cid
            latest_contexts.append(ctx_copy)

        print(f"[새로운 알고리즘] 선택된 컨텍스트 수: {len(latest_contexts)}")
        print(f"기준 start_date: {baseline_start_date_str} (id: {baseline_period_id})")
        print(f"기준 end_date: {baseline_period_data['end_date']} (+10일 확장)")
        print(f"포함된 instant {len(included_instants)}개, period {len(included_periods)}개")
        print(f"최종 포함된 ID들: {[c['id'] for c in latest_contexts]}")

        return latest_contexts

if __name__ == "__main__":
    translator = FinancialTranslator(data_dir="path_to_your_data_directory")
    translator.translate_recent_statements() 