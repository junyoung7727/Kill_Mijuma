import json
import os
from typing import Dict, List, Optional
import openai
from datetime import datetime
import traceback
import os
from dotenv import load_dotenv
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re

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
            client = OpenAI()

            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ]
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1
            )
            content = response.choices[0].message.content

            # <json> 태그로 감싸진 부분을 추출합니다.
            match = re.search(r'<json>\s*(.*?)\s*</json>', content, re.DOTALL)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            return {}
        except Exception as e:
            print(f"LLM 호출 중 오류: {str(e)}")
            return {}

    def _translate_tags(self, tags: list) -> dict:
        """태그들을 배치 처리하여 번역합니다."""
        uncached_tags = [tag for tag in tags if tag not in self.tag_translations_cache]
        if uncached_tags:
            prompt = (
                "다음 재무제표 태그들을 한국어로 번역해주세요.\n"
                "응답은 반드시 아래 JSON 형식으로 작성해주세요:\n\n"
                "<json>\n"
                '{ "translations": { "tag1": {"translation": "번역1", "importance_score": 5} } }\n'
                "</json>\n\n"
                f"태그들:\n{json.dumps(uncached_tags, ensure_ascii=False, indent=2)}"
            )
            system_msg = "재무제표 태그를 번역하는 전문가입니다."
            result = self._call_llm(prompt, system_msg)
            new_translations = result.get('translations', {})
            self.tag_translations_cache.update(new_translations)
            print(f"태그 번역 완료: {len(uncached_tags)}개 처리 (배치 처리)")
        return {tag: self.tag_translations_cache.get(tag, {}) for tag in tags}

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
                    "다음 재무제표 멤버 이름들을 한국어로 번역해주세요.\n"
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

    def _translate_batch(self, items: list) -> list:
        """단위 항목들을 배치 처리하여 번역합니다."""
        try:
            # 1. 태그 번역
            tags = [item['concept'] for item in items]
            tag_translations = self._translate_tags(tags)

            # 2. 태그별 멤버 수집 (최신 컨텍스트 데이터만)
            tag_members_map = {}
            all_members = []
            for item in items:
                tag = item['concept']
                if 'data' in item:
                    members_lists = []
                    for data_point in item['data']:
                        members = data_point.get('멤버', [])
                        if members:
                            members_lists.append(members)
                            all_members.extend(members)
                    if members_lists:
                        tag_members_map[tag] = members_lists

            # 3. 멤버 번역
            member_translations = self._translate_member_names_batch(all_members)

            # 4. 맥락 분석
            context_categories = self._analyze_data_contexts_batch(tag_members_map)

            # 5. 최종 결과 조합
            translated_items = []
            for item in items:
                tag = item['concept']
                new_item = {
                    'section': item['section'],
                    'subsection': item['subsection'],
                    'tag': tag,
                    'translation': tag_translations.get(tag, {}),
                    'importance_score': tag_translations.get(tag, {}).get('importance_score', 5),
                    'data': []
                }

                if 'data' in item:
                    for data_point in item['data']:
                        new_dp = data_point.copy()
                        members = data_point.get('멤버', [])
                        new_dp['원본_멤버'] = members
                        new_dp['번역된_멤버'] = [member_translations.get(m, m) for m in members]
                        new_dp['맥락_분류'] = context_categories.get(tag, "")
                        new_item['data'].append(new_dp)

                translated_items.append(new_item)

            return translated_items
        except Exception as e:
            print(f"배치 번역 중 오류: {str(e)}")
            return []

    def _translate_section_names_batch(self, sections: list) -> dict:
        """섹션 이름을 배치 처리하여 번역합니다.
        
        동일한 섹션 이름은 캐시된 결과를 사용하며, 새로운 섹션은 한 번의 LLM 호출로 번역합니다.
        """
        result = {}
        unique_sections_to_translate = set()
        # 표준 재무제표 용어 매핑 (해당하는 섹션은 미리 정해진 번역 사용)
        standard_statements = {
            "balance sheet": "재무상태표",
            "income statement": "포괄손익계산서",
            "cash flow": "현금흐름표",
            "statement of cash flows": "현금흐름표"
        }

        for section in sections:
            # cover나 first page는 번역하지 않음
            if any(keyword in section.lower() for keyword in ["cover", "first page"]):
                result[section] = section
                continue
            lower_sec = section.lower()
            standard_found = False
            for eng, kor in standard_statements.items():
                if eng in lower_sec:
                    result[section] = kor
                    standard_found = True
                    break
            if standard_found:
                continue
            # 이미 캐시되어 있다면 재사용
            if section in self.section_translations_cache:
                result[section] = self.section_translations_cache[section]
            else:
                unique_sections_to_translate.add(section)

        if unique_sections_to_translate:
            prompt = (
                "다음 재무제표 섹션 이름들을 한 번에 한국어로 번역해주세요.\n"
                "응답은 반드시 아래 JSON 형식으로 작성해주세요:\n\n"
                "<json>\n"
                "{\n"
                '  "translations": {\n'
                '    "Section1": "번역된 이름1",\n'
                '    "Section2": "번역된 이름2"\n'
                "  }\n"
                "}\n"
                "</json>\n\n"
                "섹션 이름들:\n" + json.dumps(list(unique_sections_to_translate), ensure_ascii=False, indent=2)
            )
            system_msg = "재무제표 섹션 이름을 한국어로 번역하는 전문가입니다."
            response = self._call_llm(prompt, system_msg)
            translations = response.get("translations", {})
            for sec in unique_sections_to_translate:
                translated = translations.get(sec, sec)
                self.section_translations_cache[sec] = translated
                result[sec] = translated
            print(f"섹션 이름 번역 완료: {len(unique_sections_to_translate)}개 처리 (배치 처리)")
        return {section: result.get(section, section) for section in sections}

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
        """
        최신 컨텍스트 ID를 가진 태그와, 해당 태그 내에서 데이터의 값들 중 최신 컨텍스트에 해당하는
        데이터 포인트만을 대상으로 번역을 진행합니다.
        또한, 번역 시 해당 데이터 포인트의 "멤버" 값도 번역 대상에 포함됩니다.
        
        hierarchy.json의 구조:
          - 최상위 키: ex) "dei_CoverAbstract"
          - 값: 리스트 또는 딕셔너리(딕셔너리인 경우 첫번째 요소에 실제 리스트가 있는 구조)
          - 각 리스트 항목: { "concept": "태그명", "data": [ { "컨텍스트": "c-문자열", ... }, ... ] }
        """
        filtered_data = {}
        if not self.hierarchy_data:
            print("계층 데이터가 없습니다.")
            return filtered_data

        # 최신 컨텍스트 추출 (ID 정규화 포함)
        latest_contexts = self._extract_latest_context()
        latest_context_ids = {ctx['id'].strip().lower() for ctx in latest_contexts}
        print(f"최신 컨텍스트 ID: {latest_context_ids}")

        items_to_translate = []
        
        # 각 섹션을 순회 (section_key는 ex) 'dei_CoverAbstract')
        for section_key, section_value in self.hierarchy_data.items():
            # 만약 section_value가 리스트가 아니라면, 첫번째 딕셔너리의 원소(리스트)를 선택
            if not isinstance(section_value, list):
                # 딕셔너리 형태: 예) { "어떤키": [ ... ] }
                section_items = list(section_value.values())[0] if section_value else []
            else:
                section_items = section_value
            
            # section_items는 리스트라고 가정
            for item in section_items:
                tag = item.get('concept')
                # tag가 없거나 Abstract 관련 태그는 건너뜁니다.
                if not tag or 'Abstract' in tag:
                    continue

                filtered_data_points = []
                # 해당 아이템의 data 배열 순회
                for data_point in item.get('data', []):
                    # hierarchy.json에서는 '컨텍스트' 키에 컨텍스트 ID가 있음.
                    context_ref = data_point.get('컨텍스트', '').strip().lower()
                    # 디버깅: 매칭 여부 출력
                    if context_ref in latest_context_ids:
                        print(f"매칭 성공: data_point 컨텍스트 '{context_ref}' ∈ 최신 컨텍스트")
                        filtered_data_points.append(data_point)
                    else:
                        print(f"매칭 실패: data_point 컨텍스트 '{context_ref}' NOT ∈ 최신 컨텍스트")
                
                # 만약 하나라도 최신 컨텍스트를 가진 데이터 포인트가 있다면,
                # 이 컨셉(태그)는 번역 대상에 포함.
                if filtered_data_points:
                    items_to_translate.append({
                        'section': section_key,
                        'subsection': "",  # 하위 섹션 정보가 없으면 빈 문자열 사용
                        'concept': tag,
                        'data': filtered_data_points  # 최신 컨텍스트에 해당하는 데이터 포인트만 포함
                    })

        print(f"번역 대상 태그 수: {len(items_to_translate)}")
        if not items_to_translate:
            print("현재 조건에 맞는 번역 대상이 없습니다. 최신 컨텍스트 조건이나 hierarchy.json 데이터를 확인하세요.")
            return filtered_data

        # 섹션 이름 번역 처리 (필요한 경우)
        sections = list({item['section'] for item in items_to_translate})
        section_translations = self._translate_section_names_batch(sections)

        batch_size = 200
        for i in range(0, len(items_to_translate), batch_size):
            batch = items_to_translate[i:i + batch_size]
            translated_batch = self._translate_batch(batch)
            
            for item in translated_batch:
                section = section_translations.get(item['section'], item['section'])
                subsection = item.get('subsection', "")
                if section not in filtered_data:
                    filtered_data[section] = {}
                if subsection not in filtered_data[section]:
                    filtered_data[section][subsection] = []
                filtered_data[section][subsection].append({
                    'tag': item['tag'],
                    'translation': item['translation'],
                    'importance_score': item.get('importance_score', 5),
                    'data': item['data']  # 이 data 안에는 최신 컨텍스트에 해당하는 데이터 포인트들만 들어있음
                })
            
            print(f"번역 완료: {len(batch)}개 항목 배치 처리")

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
        context.json에서 최신 분기 컨텍스트와 관련 instant 컨텍스트를 추출합니다.
        
        조건:
        1. period 타입 중 기간이 85~93일 사이인 컨텍스트를 찾음
        2. 그 중 가장 최근 end_date를 가진 컨텍스트들을 선택
        3. 선택된 컨텍스트들과 start_date가 최대 10일 차이 나는 컨텍스트도 포함
        4. 최신 분기의 end_date와 최대 10일 차이 나는 instant 타입 컨텍스트도 포함
        """
        try:
            file_path = os.path.join(self.data_dir, context_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                contexts = json.load(f)
        except Exception as e:
            print(f"컨텍스트 파일 로드 오류: {str(e)}")
            return []

        quarter_contexts = []
        instant_contexts = []
        
        # 모든 컨텍스트를 타입별로 분류하고 날짜 파싱
        for ctx_id, ctx_data in contexts.items():
            try:
                if ctx_data["type"] == "period":
                    start_date = datetime.strptime(ctx_data["start_date"], "%Y-%m-%d")
                    end_date = datetime.strptime(ctx_data["end_date"], "%Y-%m-%d")
                    duration = (end_date - start_date).days + 1
                    
                    if 85 <= duration <= 93:  # 분기 기간 조건 확인
                        quarter_contexts.append({
                            "id": ctx_id,
                            **ctx_data,
                            "_parsed_start": start_date,
                            "_parsed_end": end_date
                        })
                elif ctx_data["type"] == "instant":
                    instant_date = datetime.strptime(ctx_data["date"], "%Y-%m-%d")
                    instant_contexts.append({
                        "id": ctx_id,
                        **ctx_data,
                        "_parsed_date": instant_date
                    })
            except Exception as e:
                print(f"날짜 파싱 오류 (컨텍스트 {ctx_id}): {str(e)}")
                continue
        
        if not quarter_contexts:
            print("적절한 분기 기간을 가진 컨텍스트를 찾을 수 없습니다.")
            return []
        
        # 가장 최근 end_date 찾기
        latest_end_date = max(ctx["_parsed_end"] for ctx in quarter_contexts)
        
        # 최신 분기 컨텍스트와 관련된 모든 컨텍스트 선택
        latest_contexts = []
        
        # 1. 최신 분기의 start_date들 수집
        latest_start_dates = {
            ctx["_parsed_start"] 
            for ctx in quarter_contexts 
            if ctx["_parsed_end"] == latest_end_date
        }
        
        # 2. period 타입 컨텍스트 선택 (start_date 기준)
        for ctx in quarter_contexts:
            for latest_start in latest_start_dates:
                date_diff = abs((ctx["_parsed_start"] - latest_start).days)
                if date_diff <= 10:
                    clean_ctx = {k: v for k, v in ctx.items() if not k.startswith('_')}
                    if clean_ctx not in latest_contexts:
                        latest_contexts.append(clean_ctx)
        
        # 3. instant 타입 컨텍스트 선택 (end_date와의 차이 기준)
        for ctx in instant_contexts:
            date_diff = abs((ctx["_parsed_date"] - latest_end_date).days)
            if date_diff <= 10:
                clean_ctx = {k: v for k, v in ctx.items() if not k.startswith('_')}
                if clean_ctx not in latest_contexts:
                    latest_contexts.append(clean_ctx)
        
        print(f"선택된 컨텍스트 수: {len(latest_contexts)}")
        print("최신 컨텍스트 (분기 + instant):", latest_contexts)
        
        return latest_contexts

if __name__ == "__main__":
    translator = FinancialTranslator(data_dir="path_to_your_data_directory")
    translator.translate_recent_statements() 