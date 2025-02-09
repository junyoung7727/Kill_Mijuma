import requests
from bs4 import BeautifulSoup
import re
import traceback
import json
from collections import defaultdict
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import time
import openai

class SECFetcher:
    def __init__(self, user_agent, data_dir):
        self.headers = {
            'User-Agent': user_agent
        }
        self.data_dir = data_dir
        self.xbrl_data = {}
        self.custom_tags = {}
        self.integrated_data = {}
        self.current_url = None
        self.base_url = "https://www.sec.gov"
        self.last_request_time = 0
        self.last_llm_request = 0

    def _get(self, url: str) -> Optional[requests.Response]:
        """SEC 서버에 요청을 보내는 메서드 (rate limiting 적용)
        
        Args:
            url (str): 요청할 URL
            
        Returns:
            Optional[requests.Response]: 응답 객체 또는 None (에러 발생 시)
        """
        # SEC rate limit (10 requests per second) 준수
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < 0.1:  # 100ms 대기
            time.sleep(0.1 - time_since_last_request)
        
        try:
            response = requests.get(url, headers=self.headers)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                return response
            else:
                print(f"Error: HTTP {response.status_code} - {url}")
                return None
                
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None

    def get_latest_10q_url(self, cik):
        """특정 기업의 최신 10-Q 보고서 URL 찾기"""
        try:
            # CIK 번호 형식 맞추기 (10자리)
            cik = str(cik).zfill(10)
            
            # 회사의 제출 이력 가져오기
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            print(f"\n=== 제출 이력 가져오기: {submissions_url} ===")
            
            response = requests.get(submissions_url, headers=self.headers)
            if response.status_code != 200:
                print(f"Error: 제출 이력 접근 실패 (Status: {response.status_code})")
                return None
                
            data = response.json()
            recent_filings = data.get('filings', {}).get('recent', {})
            
            if not recent_filings:
                print("Error: 최근 제출 이력을 찾을 수 없습니다.")
                return None
                
            # 제출 양식 목록
            form_types = recent_filings.get('form', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            primary_documents = recent_filings.get('primaryDocument', [])
            
            # 최신 10-Q 보고서 찾기
            for i, form_type in enumerate(form_types):
                if form_type == '10-Q':
                    accession_number = accession_numbers[i].replace('-', '')
                    primary_doc = primary_documents[i]
                    url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{accession_number}/{primary_doc}"
                    print(f"10-Q URL 찾음: {url}")
                    return url
                    
            print("Error: 10-Q 보고서를 찾을 수 없습니다.")
            return None
            
        except Exception as e:
            print(f"최신 10-Q URL 찾기 실패: {str(e)}")
            traceback.print_exc()
            return None

    def get_xbrl_data(self, url):
        """URL에서 XBRL 데이터 가져오기"""
        try:
            # URL에서 파일명 추출
            base_url = url.split('ix?doc=/')[1]
            xml_url = f"https://www.sec.gov/{base_url.replace('.htm', '_htm.xml')}"
            
            print(f"\nXML 파일 다운로드 중: {xml_url}")
            response = requests.get(xml_url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error: XML 파일 접근 실패 (Status: {response.status_code})")
                return None
            
            # 두 가지 파서로 파싱
            soup = BeautifulSoup(response.content, 'lxml')  # 기본 데이터용
            xml_soup = BeautifulSoup(response.content, 'xml')  # 축/멤버 정보용
            
            # context 정보 수집 (xml_soup 사용)
            context_data = {}
            for context in xml_soup.find_all('context'):
                context_id = context.get('id', '')
                period = context.find('period')
                segment = context.find('segment')
                
                context_info = {
                    'period': {},
                    'axis': [],
                    'members': [],
                    'explicit_members': []
                }
                
                # 기간 정보 파싱
                if period:
                    instant = period.find('instant')
                    if instant:
                        context_info['period'] = {
                            "type": "instant",
                            "date": instant.text
                        }
                    else:
                        start_date = period.find('startDate')
                        end_date = period.find('endDate')
                        if start_date and end_date:
                            context_info['period'] = {
                                "type": "period",
                                "start_date": start_date.text,
                                "end_date": end_date.text
                            }
                
                # 세그먼트 정보 파싱
                if segment:
                    for member in segment.find_all(True):
                        if 'explicitMember' in member.name:
                            dimension = member.get('dimension', '')
                            member_value = member.text.strip()
                            
                            if ':' in dimension:
                                prefix, axis = dimension.split(':')
                                context_info['axis'].append(axis)
                            else:
                                context_info['axis'].append(dimension)
                            
                            if ':' in member_value:
                                prefix, member_name = member_value.split(':')
                                context_info['members'].append(member_name)
                                if member_name.endswith('Member'):
                                    context_info['explicit_members'].append(member_name)
                            else:
                                context_info['members'].append(member_value)
                                if member_value.endswith('Member'):
                                    context_info['explicit_members'].append(member_value)
                
                context_data[context_id] = context_info
            
            # XBRL 데이터 수집 (soup 사용)
            self.xbrl_data = defaultdict(list)
            
            # us-gaap: 태그 찾기
            for element in soup.find_all(lambda tag: isinstance(tag.name, str) and tag.name.startswith('us-gaap:')):
                tag_name = element.name.split(':')[1].lower()
                context_ref = element.get('contextref', '')
                unit_ref = element.get('unitref', '')
                decimals = element.get('decimals', '0')
                value = element.text.strip()
                
                # 데이터 포인트 정보 구성
                data_point = {
                    'value': value,
                    'display_value': value,
                    'context': context_ref,
                    'unit': unit_ref,
                    'decimals': decimals,
                    'raw_value': value,
                    'source': 'xbrl'
                }
                
                # context 정보 추가 (xml_soup에서 파싱한 정보 사용)
                if context_ref in context_data:
                    ctx_info = context_data[context_ref]
                    data_point.update({
                        'axis': ctx_info['axis'],
                        'members': ctx_info['members'],
                        'explicit_members': ctx_info['explicit_members'],
                        'period': ctx_info['period']
                    })
                
                self.xbrl_data[tag_name].append(data_point)
            
            # 파일로 저장
            output_file = os.path.join(self.data_dir, 'xbrl_data.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self.xbrl_data), f, indent=2, ensure_ascii=False)
            
            return dict(self.xbrl_data), xml_soup
            
        except Exception as e:
            print(f"Error: XBRL 데이터 처리 중 오류 발생 - {str(e)}")
            return None, None

    def get_custom_tags(self, url):
        """URL에서 커스텀 태그 정보 가져오기"""
        try:
            base_url = url.split('ix?doc=/')[1]
            def_url = f"https://www.sec.gov/{base_url.replace('.htm', '_def.xml')}"
            
            print(f"\nDefinition 파일 다운로드 중: {def_url}")
            response = requests.get(def_url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error: Definition 파일 접근 실패 (Status: {response.status_code})")
                return None
            
            # xml 파서 사용
            soup = BeautifulSoup(response.content, 'xml')
            
            # 커스텀 태그 수집
            self.custom_tags = {}
            for loc in soup.find_all('loc'):
                href = loc.get('xlink:href', '')
                if 'aapl-' in href:  # 기업별 prefix 처리
                    tag_name = href.split('#aapl_')[1]
                    if tag_name not in self.custom_tags:
                        self.custom_tags[tag_name] = {
                            'label': loc.get('xlink:label', ''),
                            'type': 'custom',
                            'source': 'definition',
                            'axis': [],
                            'members': [],
                            'explicit_members': []
                        }
            
            # 축과 멤버 정보 추가
            for arc in soup.find_all('definitionArc'):
                from_label = arc.get('xlink:from', '')
                to_label = arc.get('xlink:to', '')
                arcrole = arc.get('xlink:arcrole', '')
                
                if 'dimension-domain' in arcrole or 'domain-member' in arcrole:
                    for tag in self.custom_tags.values():
                        if tag['label'] == from_label:
                            # 축/멤버 관계 정보 저장
                            for loc in soup.find_all('loc'):
                                if loc.get('xlink:label') == to_label:
                                    member_href = loc.get('xlink:href', '')
                                    if ':' in member_href:
                                        ns, member = member_href.split('#')[1].split('_')
                                        tag['members'].append(member)
                                        if member.endswith('Member'):
                                            tag['explicit_members'].append(member)
            
            return self.custom_tags
            
        except Exception as e:
            print(f"커스텀 태그 가져오기 실패: {str(e)}")
            traceback.print_exc()
            return None

    def integrate_data(self):
        """XBRL 데이터와 커스텀 태그 통합"""
        try:
            self.integrated_data = defaultdict(list)
            
            # XBRL 데이터 복사
            for tag_name, values in self.xbrl_data.items():
                for value in values:
                    integrated_point = {
                        "값": value.get('value', ''),
                        "단위": value.get('unit', ''),
                        "소수점": value.get('decimals', '0'),
                        "축": value.get('axis', []),
                        "멤버": value.get('members', []),
                        "Explicit Members": value.get('explicit_members', []),
                        "기간": value.get('period', {}),
                        "출처": "xbrl"
                    }
                    self.integrated_data[tag_name].append(integrated_point)
            
            # 커스텀 태그 추가
            for tag_name, tag_info in self.custom_tags.items():
                if tag_name not in self.integrated_data:
                    self.integrated_data[tag_name] = []
                
                # 커스텀 태그 정보를 통합 데이터 형식에 맞춰 변환
                custom_point = {
                    "값": "",  # 커스텀 태그는 값이 없을 수 있음
                    "단위": "",
                    "소수점": "0",
                    "축": tag_info.get('axis', []),
                    "멤버": tag_info.get('members', []),
                    "Explicit Members": tag_info.get('explicit_members', []),
                    "기간": {},
                    "출처": "custom",
                    "레이블": tag_info.get('label', ''),
                    "타입": tag_info.get('type', '')
                }
                self.integrated_data[tag_name].append(custom_point)
            
            return dict(self.integrated_data)
            
        except Exception as e:
            print(f"데이터 통합 중 오류 발생: {str(e)}")
            traceback.print_exc()
            return None

    def print_hierarchy(self, section_data, xbrl_data):
        """계층 구조 출력"""
        def print_node(node, depth=0):
            indent = "  " * depth
            
            if isinstance(node, dict):
                for key, value in node.items():
                    # 태그 처리 개선
                    tag_name = self.remove_namespace(key)
                    print(f"{indent}{tag_name}:")
                    
                    # 데이터 포인트 정보 출력
                    if isinstance(value, list) and value and 'data' in value[0]:
                        for item in value:
                            data = item.get('data', [])
                            if data:
                                for point in data:
                                    print(f"{indent}  값: {point.get('값', '')}")
                                    print(f"{indent}  단위: {point.get('단위', '')}")
                                    if point.get('축'):
                                        print(f"{indent}  축: {', '.join(point['축'])}")
                                    if point.get('멤버'):
                                        print(f"{indent}  멤버: {', '.join(point['멤버'])}")
                                    if point.get('기간'):
                                        period = point['기간']
                                        if period.get('type') == 'instant':
                                            print(f"{indent}  날짜: {period.get('date', '')}")
                                        else:
                                            print(f"{indent}  시작일: {period.get('start_date', '')}")
                                            print(f"{indent}  종료일: {period.get('end_date', '')}")
                    else:
                        print_node(value, depth + 1)
                        
            elif isinstance(node, list):
                for item in node:
                    print_node(item, depth)
            else:
                print(f"{indent}{node}")
        
        print("\n=== 계층 구조 출력 ===\n")
        print_node(section_data)

    def add_dimension_info(self, soup, data_point):
        """데이터 포인트에 축과 멤버 정보 추가"""
        context_ref = data_point.get('context')
        if not context_ref:
            return data_point
        
        # XML 네임스페이스 정의
        namespaces = {
            'xbrli': 'http://www.xbrl.org/2003/instance',
            'xbrldi': 'http://xbrl.org/2006/xbrldi',
            'srt': 'http://fasb.org/srt/2021-01-31',
            'us-gaap': 'http://fasb.org/us-gaap/2021-01-31',
            'aapl': 'http://apple.com/20240127'
        }
        
        # context 찾기 (네임스페이스 고려)
        context = soup.find('context', id=context_ref)
        if not context:
            return data_point
        
        # 기본 정보 초기화
        data_point['축'] = []
        data_point['멤버'] = []
        data_point['Explicit Members'] = []
        
        # segment 정보 찾기
        segment = context.find('segment')
        if segment:
            # explicitMember 태그에서 축과 멤버 정보 추출
            for member in segment.find_all('explicitMember'):
                dimension = member.get('dimension', '')
                member_value = member.text.strip()
                
                # 네임스페이스 처리
                if ':' in dimension:
                    prefix, axis = dimension.split(':')
                    data_point['축'].append(axis)
                else:
                    data_point['축'].append(dimension)
                
                # 멤버 값 처리
                if ':' in member_value:
                    prefix, member_name = member_value.split(':')
                    data_point['멤버'].append(member_name)
                    if member_name.endswith('Member'):
                        data_point['Explicit Members'].append(member_name)
                else:
                    data_point['멤버'].append(member_value)
                    if member_value.endswith('Member'):
                        data_point['Explicit Members'].append(member_value)
        
        # 기간 정보 추가
        period = context.find('period')
        if period:
            instant = period.find('instant')
            if instant:
                data_point['기간'] = {
                    'type': 'instant',
                    'date': instant.text.strip()
                }
            else:
                start_date = period.find('startDate')
                end_date = period.find('endDate')
                if start_date and end_date:
                    data_point['기간'] = {
                        'type': 'duration',
                        'start_date': start_date.text.strip(),
                        'end_date': end_date.text.strip()
                    }
        
        return data_point

    def create_hierarchy_json(self, xbrl_data, integrated_data, xml_soup, url):
        """계층 구조 JSON 생성"""
        hierarchy = {}
        
        try:
            # pre.xml URL 생성
            base_url = url.split('ix?doc=/')[1]
            pre_url = f"https://www.sec.gov/{base_url.replace('.htm', '_pre.xml')}"
            
            print(f"\nPresentation 파일 다운로드 중: {pre_url}")
            response = requests.get(pre_url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error: Presentation 파일 접근 실패 (Status: {response.status_code})")
                return None
            
            # pre.xml 파싱 (xml 파서 사용)
            pre_soup = BeautifulSoup(response.content, 'xml')
            
            # presentationLink 별로 처리
            for link in pre_soup.find_all('link:presentationLink'):
                section_name = self.get_section_name(link.get('xlink:role', ''))
                if not section_name:
                    continue
                
                if section_name not in hierarchy:
                    hierarchy[section_name] = {}
                
                # 태그 매핑 정보 수집
                tag_map = {}
                for loc in link.find_all('link:loc'):
                    label = loc.get('xlink:label')
                    href = loc.get('xlink:href')
                    if href and '#' in href:
                        tag = href.split('#')[-1]
                        tag_map[label] = tag
                
                # 계층 구조 수집
                current_section = hierarchy[section_name]
                for arc in link.find_all('link:presentationArc'):
                    from_label = arc.get('xlink:from')
                    to_label = arc.get('xlink:to')
                    
                    if from_label in tag_map and to_label in tag_map:
                        from_tag = tag_map[from_label]
                        to_tag = tag_map[to_label]
                        
                        # 상위 태그 처리
                        if from_tag not in current_section:
                            current_section[from_tag] = []
                        
                        # 하위 태그 데이터 구성
                        child_node = {
                            'concept': to_tag,
                            'data': []
                        }
                        
                        # XBRL 데이터에서 값 가져오기
                        search_tag = self.remove_namespace(to_tag).lower()
                        if search_tag in xbrl_data:
                            for value in xbrl_data[search_tag]:
                                # 새로운 JSON 구조에 맞게 데이터 포인트 구성
                                data_point = {
                                    "값": value.get('value', ''),
                                    "단위": value.get('unit', ''),
                                    "소수점": value.get('decimals', '0'),
                                    "컨텍스트": value.get('context', ''),
                                    "축": value.get('axis', []),
                                    "멤버": value.get('members', []),
                                    "Explicit Members": value.get('explicit_members', []),
                                    "기간": value.get('period', {})
                                }
                                child_node['data'].append(data_point)
                        
                        current_section[from_tag].append(child_node)
            
            # 빈 섹션 제거
            hierarchy = {k: v for k, v in hierarchy.items() if v}
            
            # JSON 파일로 저장
            output_file = os.path.join(self.data_dir, 'hierarchy.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(hierarchy, f, indent=2, ensure_ascii=False)
            
            return hierarchy
            
        except Exception as e:
            print(f"Error: 계층 구조 생성 중 오류 발생 - {str(e)}")
            traceback.print_exc()
            return None

    def get_section_name(self, role):
        """role URI에서 섹션 이름 추출 및 정제
        
        Args:
            role (str): role URI
            
        Returns:
            str: 정제된 섹션 이름
        """
        # 기업별 커스텀 role 패턴
        company_patterns = {
            'apple.com/role/': 'Apple',
            'microsoft.com/role/': 'Microsoft',
            'amazon.com/role/': 'Amazon',
            'google.com/role/': 'Google',
            'meta.com/role/': 'Meta',
            'nvidia.com/role/': 'NVIDIA',
            '/role/': 'Standard'  # 기본 패턴
        }
        
        # role에서 섹션 이름 추출
        section = None
        company = 'Standard'
        
        for pattern, company_name in company_patterns.items():
            if pattern in role.lower():
                section = role.split(pattern)[-1]
                company = company_name
                break
        
        if section:
            # 불필요한 접미사 제거
            suffixes = ['Details', 'Information', 'Disclosure', 'Table', 'Policy']
            for suffix in suffixes:
                if section.endswith(suffix):
                    section = section[:-len(suffix)]
            
            # CamelCase를 공백으로 분리하고 정제
            import re
            
            def clean_section_name(text):
                # 1. 대문자로 시작하는 단어들 분리
                words = re.findall('[A-Z][^A-Z]*|[a-z]+', text)
                
                # 2. 숫자와 문자 사이에 공백 추가
                processed_words = []
                for word in words:
                    sub_words = re.findall('[0-9]+|[^0-9]+', word)
                    processed_words.extend(sub_words)
                
                # 3. 특수문자 제거 및 공백으로 변환
                cleaned_words = [re.sub('[^a-zA-Z0-9]', ' ', word).strip() 
                               for word in processed_words]
                
                # 4. 빈 문자열 제거 및 단어 결합
                final_words = [word for word in cleaned_words if word]
                
                return ' '.join(final_words)
            
            section = clean_section_name(section)
            
            # 회사명이 Standard가 아닌 경우 접두어로 추가
            if company != 'Standard':
                section = f"{company} - {section}"
            
            return section.strip()
            
        return 'Other'

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

    
    def process_translation(self, data):
        """번역 결과 처리 및 정제
        
        Args:
            data (dict): 번역된 데이터
            
        Returns:
            dict: 정제된 번역 데이터
        """
        try:
            processed_data = {}
            
            for tag_name, values in data.items():
                processed_values = []
                
                for value in values:
                    processed_point = value.copy()  # 기존 데이터 복사
                    
                    # 번역 정보가 있는 경우 처리
                    if "번역" in processed_point:
                        translation = processed_point["번역"]
                        
                        # 태그 번역 처리
                        if "태그" in translation:
                            lines = translation["태그"].split('\n')
                            processed_point["번역"]["태그_설명"] = lines[0].strip() if lines else ""
                            processed_point["번역"]["태그_정의"] = lines[1].strip() if len(lines) > 1 else ""
                        
                        # 축 번역 처리
                        if "축" in translation:
                            axis_translations = translation["축"].split('\n')
                            processed_point["번역"]["축_설명"] = [
                                line.strip() for line in axis_translations if line.strip()
                            ]
                        
                        # 멤버 번역 처리
                        if "멤버" in translation:
                            member_translations = translation["멤버"].split('\n')
                            processed_point["번역"]["멤버_설명"] = [
                                line.strip() for line in member_translations if line.strip()
                            ]
                    
                    processed_values.append(processed_point)
                
                processed_data[tag_name] = processed_values
            
            # 정제된 번역 결과 저장
            output_file = os.path.join(self.data_dir, 'processed_translation.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, indent=2, ensure_ascii=False)
            
            return processed_data
            
        except Exception as e:
            print(f"번역 처리 중 오류 발생: {str(e)}")
            traceback.print_exc()
            return None

# 사용 예시
if __name__ == "__main__":
    # 데이터 디렉토리 설정
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    fetcher = SECFetcher("junghae2017@gmail.com", data_dir)
    
    # Apple의 CIK
    apple_cik = "320193"
    
    # 최신 10-Q URL 가져오기
    url = fetcher.get_latest_10q_url(apple_cik)
    if url:
        print(f"\n10-Q URL: {url}")
        
        # XBRL 데이터 가져오기
        data = fetcher.get_xbrl_data(url)
        if data:
            print("\n=== 주요 재무 데이터 ===")
            for item, values in data.items():
                print(f"\n{item}:")
                for value in values:
                    if isinstance(value['value'], (int, float)):
                        print(f"값: ${value['value']:,.2f}")
                    else:
                        print(f"값: {value['value']}")
                    print(f"컨텍스트: {value['context']}")
                    print(f"단위: {value['unit']}")
