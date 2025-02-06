import json
import os
from typing import Dict, List, Optional
import openai
from datetime import datetime
import traceback
import os
from dotenv import load_dotenv

load_dotenv()

class FinancialTranslator:
    def __init__(self, data_dir: str, model: str = "gpt-4o"):
        self.data_dir = data_dir
        self.model = model
        self.hierarchy_data = None
        self.translated_data = {}
    
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

    def _load_hierarchy(self) -> Dict:
        """hierarchy.json 파일 로드"""
        try:
            file_path = os.path.join(self.data_dir, 'hierarchy.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"hierarchy.json 로드 중 오류: {str(e)}")
            traceback.print_exc()
            return None

    def _translate_item(self, tag: str, data_points: List[Dict]) -> Dict:
        """항목 번역 및 설명 생성"""
        try:
            # 기본 태그 정보 준비
            tag_info = self.remove_namespace(tag)
            
            # 멤버 정보가 있는 데이터 확인
            members_exist = any(data_point.get('멤버', []) for data_point in data_points)
            
            # 번역 프롬프트 구성
            prompt = (
                f"다음 XBRL 태그를 한국어로 번역하고 설명해주세요:\n"
                f"태그: {tag_info}\n"
            )
            
            # 멤버 정보가 있는 경우 추가 정보 제공
            if members_exist:
                member_info = [data_point.get('멤버', []) for data_point in data_points if data_point.get('멤버')]
                member_str = ", ".join([m for sublist in member_info for m in sublist])
                prompt += f"멤버 정보: {member_str}\n"
            
            prompt += (
                f"\n다음 형식으로 응답해주세요:\n"
                f"korean_name: [한국어 이름]\n"
                f"description: [상세 설명]\n"
                f"category: [범주: 수익/비용/자산/부채/자본/기타 중 선택]"
            )
        
            
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "재무제표 항목을 한국어로 번역하는 전문가입니다. K-IFRS 기준으로 한국인이 직관적으로 이해하기 쉬운 이름으로 심플하고 전문적으로 번역해주세요. 고객과의 계약에서 발생한 수익(RevenueFromContract)등은 매출액처럼 직관적으로 번역하세요. "},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            translation = {}
            
            for line in result.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    translation[key.strip()] = value.strip()
            
            return translation
            
        except Exception as e:
            print(f"번역 중 오류: {str(e)}")
            return {
                'korean_name': tag,
                'description': '',
                'category': '기타'
            }

    def _get_latest_contexts(self) -> List[str]:
        """가장 최근 3개월 기간의 컨텍스트 ID 리스트 반환"""
        try:
            # context.json 읽기
            context_file = os.path.join(self.data_dir, 'context_data.json')
            with open(context_file, 'r', encoding='utf-8') as f:
                context_data = json.load(f)
            
            print("\n컨텍스트 데이터 처리 시작")
            print(f"총 컨텍스트 수: {len(context_data)}")
            
            # 기간 정보가 있는 컨텍스트만 필터링
            period_contexts = []
            for context_id, context_info in context_data.items():
                try:
                    if (context_info.get('type') == 'period' and 
                        'start_date' in context_info and 
                        'end_date' in context_info):
                        
                        start_date = datetime.strptime(context_info['start_date'], '%Y-%m-%d')
                        end_date = datetime.strptime(context_info['end_date'], '%Y-%m-%d')
                        duration = (end_date - start_date).days
                        
                        print(f"\n컨텍스트 {context_id}:")
                        print(f"  시작일: {start_date}")
                        print(f"  종료일: {end_date}")
                        print(f"  기간: {duration}일")
                        
                        period_contexts.append({
                            'context_id': context_id,
                            'end_date': end_date,
                            'duration': duration
                        })
                except Exception as e:
                    print(f"컨텍스트 {context_id} 처리 중 오류: {str(e)}")
                    continue
            
            print(f"\n처리된 기간 컨텍스트 수: {len(period_contexts)}")
            if not period_contexts:
                print("경고: 처리된 컨텍스트가 없습니다!")
                return []
            
            return [ctx['context_id'] for ctx in period_contexts]
            
        except Exception as e:
            print(f"컨텍스트 파일 처리 중 오류: {str(e)}")
            traceback.print_exc()
            return []

    def _get_member_specific_name(self, base_name: str, members: List[str]) -> str:
        """멤버 정보를 기반으로 구체적인 이름 생성"""
        if not members:
            return f"총 {base_name}"
        
        member_str = ", ".join([self.remove_namespace(m) for m in members])
        prompt = (
            f"다음 멤버 정보를 기반으로 기본 XBRL 태그의 하위 항목의 이름을 생성하여 생성된 이름만 출력해주세요.:\n"
            f"기본 XBRL 태그: {base_name}\n"
            f"멤버: {member_str}\n"
            f"예시: ProductMember -> 제품 {base_name}, ServiceMember -> 서비스 {base_name}"
        )
        
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "재무제표 항목의 멤버 정보를 기반으로 구체적인 이름을 생성하는 전문가입니다. K-IFRS 기준으로 한국인이 직관적으로 이해하기 쉬운 이름으로 심플하고 전문적으로 번역해주세요. 고객과의 계약에서 발생한 수익(RevenueFromContract)등은 매출액처럼 직관적으로 번역하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()

    def _translate_section_name(self, section_name: str) -> str:
        """섹션 이름 번역"""
        try:
            prompt = (
                f"다음 재무제표 섹션 이름을 한국어로 번역해주세요:\n"
                f"{section_name}\n\n"
                f"예시:\n"
                f"CONSOLIDATED STATEMENTS OF OPERATIONS -> 연결 손익 계산서\n"
                f"CONSOLIDATED BALANCE SHEETS -> 연결 재무상태표"
            )
            
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "재무제표 섹션 이름을 한국어로 번역하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            translated_name = response.choices[0].message.content.strip()
            return translated_name
            
        except Exception as e:
            print(f"섹션 이름 번역 중 오류: {str(e)}")
            return section_name

    def _filter_and_translate(self) -> Dict:
        """데이터 필터링 및 번역"""
        filtered_data = {}
        
        try:
            # 최근 컨텍스트 리스트 가져오기
            latest_contexts = self._get_latest_contexts()
            if not latest_contexts:
                print("최근 컨텍스트를 찾을 수 없습니다.")
                return filtered_data
            
            for section_name, section_data in self.hierarchy_data.items():
                # 섹션 이름 번역
                translated_section_name = self._translate_section_name(section_name)
                print(f"\n처리 중인 섹션: {section_name}")
                print(f"번역된 섹션 이름: {translated_section_name}")
                
                section_dict = {}
                
                for subsection_name, items in section_data.items():
                    if not isinstance(items, list):
                        continue
                    
                    subsection_items = []
                    
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                            
                        concept = item.get('concept')
                        data = item.get('data', [])
                        
                        if not concept or not data:
                            continue
                        
                        # 최근 컨텍스트에 해당하는 데이터만 필터링
                        latest_data = []
                        seen_data = set()  # 중복 체크를 위한 set
                        
                        for data_point in data:
                            context_id = data_point.get('컨텍스트', '')
                            value = data_point.get('값', '')
                            
                            # 중복 체크를 위한 키 생성
                            dedup_key = f"{context_id}:{value}"
                            
                            if context_id in latest_contexts and dedup_key not in seen_data:
                                transformed_data = {
                                    "value": value,
                                    "display_value": value,
                                    "unit": data_point.get('단위', ''),
                                    "decimals": data_point.get('소수점', ''),
                                    "raw_value": value,
                                    "context": context_id,
                                    "source": "xbrl",
                                    "axis": data_point.get('축', []),
                                    "member": data_point.get('멤버', []),
                                    "explicit_members": data_point.get('Explicit Members', []),
                                    "period": data_point.get('기간', {}),
                                    "attributes": {
                                        "contextref": context_id,
                                        "id": ""
                                    }
                                }
                                latest_data.append(transformed_data)
                                seen_data.add(dedup_key)  # 중복 체크를 위해 키 추가
                        
                        if latest_data:
                            # 기본 태그 번역
                            translation = self._translate_item(concept, latest_data)
                            base_name = translation.get('korean_name', '')
                            
                            # 각 데이터 포인트에 대해 멤버 기반 이름 추가
                            for data_point in latest_data:
                                members = data_point.get('member', [])
                                specific_name = self._get_member_specific_name(base_name, members)
                                data_point['specific_name'] = specific_name
                            
                            filtered_item = {
                                'tag': concept,
                                'translation': translation,
                                'data': latest_data
                            }
                            
                            subsection_items.append(filtered_item)
                            print(f"  처리 완료: {concept}")
                            print(f"    기본 번역: {base_name}")
                            for data in latest_data:
                                print(f"    구체적 이름: {data.get('specific_name', '')}")
                            print(f"    데이터 수: {len(latest_data)}개")
                    
                    if subsection_items:
                        section_dict[subsection_name] = subsection_items
                
                if section_dict:
                    # 번역된 섹션 이름을 키로 사용
                    filtered_data[translated_section_name] = section_dict
                    print(f"섹션 처리 완료: {sum(len(items) for items in section_dict.values())}개 항목")
        
        except Exception as e:
            print(f"필터링 및 번역 중 오류: {str(e)}")
            traceback.print_exc()
        print(filtered_data)
        return filtered_data

    def translate_recent_statements(self) -> None:
        """재무제표 번역 실행"""
        try:
            print("\n재무제표 번역 시작...")
            
            # 1. hierarchy.json 로드
            self.hierarchy_data = self._load_hierarchy()
            if not self.hierarchy_data:
                print("hierarchy.json 로드 실패")
                return
            
            # 2. 필터링 및 번역
            self.translated_data = self._filter_and_translate()
            if not self.translated_data:
                print("번역할 데이터가 없습니다.")
                return
            
            # 3. 결과 저장
            output_file = os.path.join(self.data_dir, 'structured_kr_data.json')

            if os.path.exists(output_file):
                print(f"기존 파일을 찾았습니다: {output_file}")
            else:
                print(f"새로운 파일을 생성합니다: {output_file}")
            # 빈 파일 생성
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
        
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.translated_data, f, ensure_ascii=False, indent=2)
            
            print(f"\n번역 완료: {output_file}")
            
        except Exception as e:
            print(f"처리 중 오류 발생: {str(e)}")
            traceback.print_exc()

if __name__ == "__main__":
    translator = FinancialTranslator(data_dir="path_to_your_data_directory")
    translator.translate_recent_statements() 