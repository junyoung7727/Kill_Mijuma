import requests
from bs4 import BeautifulSoup
import re
import traceback
import json
from collections import defaultdict
import os
import xml.etree.ElementTree as ET

class SECFetcher:
    def __init__(self, user_agent, data_dir):
        self.headers = {
            'User-Agent': user_agent
        }
        self.data_dir = data_dir
        self.xbrl_data = {}
        self.custom_tags = {}
        self.integrated_data = {}

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
            
            # XML 파싱
            soup = BeautifulSoup(response.content, 'lxml')
            
            # context 정보 수집
            context_data = {}
            for context in soup.find_all('context'):
                context_id = context.get('id', '')
                period = context.find('period')
                if period:
                    instant = period.find('instant')
                    if instant:
                        context_data[context_id] = {
                            "type": "instant",
                            "date": instant.text
                        }
                    else:
                        start_date = period.find('startdate')
                        end_date = period.find('enddate')
                        if start_date and end_date:
                            context_data[context_id] = {
                                "type": "period",
                                "start_date": start_date.text,
                                "end_date": end_date.text
                            }
            
            # Context 정보를 JSON 파일로 저장
            context_file = os.path.join(self.data_dir, 'context_data.json')
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(context_data, f, indent=2, ensure_ascii=False)
            
            print("\n=== Context 정보 ===")
            for context_id, info in context_data.items():
                if info["type"] == "instant":
                    print(f"Context ID: {context_id}, Date: {info['date']}")
                else:
                    print(f"Context ID: {context_id}, Period: {info['start_date']} to {info['end_date']}")
            
            # 모든 태그 수집
            self.xbrl_data = defaultdict(list)
            
            # us-gaap: 태그 찾기
            for element in soup.find_all(lambda tag: isinstance(tag.name, str) and tag.name.startswith('us-gaap:')):
                tag_name = element.name.split(':')[1].lower()  # 태그 이름을 소문자로 변환
                context_ref = element.get('contextref', '')  # contextRef 대신 contextref 사용
                unit_ref = element.get('unitref', '')
                decimals = element.get('decimals', '0')
                value = element.text.strip()
                
                # 값 처리
                try:
                    if decimals and decimals != 'INF':
                        adjusted_value = float(value) if value else 0
                        display_value = f"{adjusted_value:,.0f}" if adjusted_value else "0"
                    else:
                        adjusted_value = value
                        display_value = value
                except ValueError:
                    adjusted_value = value
                    display_value = value
                
                # 속성 정보 수집
                attributes = {}
                for attr, val in element.attrs.items():
                    # 속성 이름을 소문자로 변환
                    attr_lower = attr.lower()
                    attributes[attr_lower] = val
                
                self.xbrl_data[tag_name].append({
                    'value': adjusted_value,
                    'display_value': display_value,
                    'context': context_ref,  # contextRef 값 저장
                    'unit': unit_ref,
                    'decimals': decimals,
                    'raw_value': value,
                    'source': 'xbrl',
                    'attributes': attributes  # 모든 속성 저장
                })
            
            # 파일로 저장
            output_file = os.path.join(self.data_dir, 'xbrl_data.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self.xbrl_data), f, indent=2, ensure_ascii=False)
            
            return dict(self.xbrl_data)
            
        except Exception as e:
            print(f"Error: XBRL 데이터 처리 중 오류 발생 - {str(e)}")
            return None

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
            
            soup = BeautifulSoup(response.content, 'xml')
            
            # 커스텀 태그 수집
            for loc in soup.find_all('loc'):
                href = loc.get('xlink:href', '')
                if 'aapl-' in href:
                    tag_name = href.split('#aapl_')[1]
                    if tag_name not in self.custom_tags:
                        self.custom_tags[tag_name] = {
                            'label': loc.get('xlink:label', ''),
                            'type': 'custom',
                            'source': 'definition'
                        }
            
            return self.custom_tags
            
        except Exception as e:
            print(f"커스텀 태그 가져오기 실패: {str(e)}")
            traceback.print_exc()
            return None

    def integrate_data(self):
        """XBRL 데이터와 커스텀 태그 통합"""
        self.integrated_data = self.xbrl_data.copy()
        
        # 커스텀 태그 추가
        for tag_name, tag_info in self.custom_tags.items():
            if tag_name not in self.integrated_data:
                self.integrated_data[tag_name] = []
            self.integrated_data[tag_name].append(tag_info)
        
        return self.integrated_data

    def print_hierarchy(self, section_data, xbrl_data):
        """계층 구조 출력"""
        def print_node(node, depth=0):
            indent = "  " * depth
            
            if isinstance(node, dict):
                for key, value in node.items():
                    # 태그 처리 개선
                    tag_name = self.remove_namespace(key)
                    print(f"{indent}{tag_name}:")
                    if isinstance(value, (dict, list)):
                        print_node(value, depth + 1)
                    else:
                        print(f"{indent}  {value}")
                    
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, dict) and "concept" in item:
                        # concept 태그 처리
                        tag_name = self.remove_namespace(item["concept"])
                        print(f"{indent}{tag_name}:")
                        if item.get("data"):
                            for data in item["data"]:
                                print(f"{indent}  값: {data.get('value', '')}")
                    else:
                        print_node(item, depth)
                
            else:
                print(f"{indent}{node}")
        
        print("\n=== 계층 구조 출력 ===\n")
        print_node(section_data)

    def create_hierarchy_json(self, xbrl_data, integrated_data):
        """계층 구조 JSON 생성"""
        hierarchy = {}
        
        # pre.xml 파싱
        pre_tree = ET.parse(os.path.join(self.data_dir, 'pre.xml'))
        pre_root = pre_tree.getroot()
        
        ns = {
            'link': 'http://www.xbrl.org/2003/linkbase',
            'xlink': 'http://www.w3.org/1999/xlink'
        }
        
        # presentationLink 별로 처리
        for link in pre_root.findall('.//link:presentationLink', ns):
            # 섹션 이름 가져오기
            role = link.get('{http://www.w3.org/1999/xlink}role')
            section_name = self.get_section_name(role)
            
            if section_name not in hierarchy:
                hierarchy[section_name] = {}
            
            # 태그 매핑 정보 수집
            tag_map = {}
            for loc in link.findall('.//link:loc', ns):
                label = loc.get('{http://www.w3.org/1999/xlink}label')
                href = loc.get('{http://www.w3.org/1999/xlink}href')
                tag = href.split('#')[-1]  # 네임스페이스 유지
                tag_map[label] = tag
            
            # 계층 구조 수집
            current_section = hierarchy[section_name]
            for arc in link.findall('.//link:presentationArc', ns):
                from_label = arc.get('{http://www.w3.org/1999/xlink}from')
                to_label = arc.get('{http://www.w3.org/1999/xlink}to')
                order = float(arc.get('order', '1.0'))
                
                if from_label in tag_map and to_label in tag_map:
                    from_tag = tag_map[from_label]
                    to_tag = tag_map[to_label]
                    
                    if from_tag not in current_section:
                        current_section[from_tag] = []
                    
                    # 값 검색을 위해 네임스페이스만 제거
                    search_tag = self.remove_namespace(to_tag).lower()
                    
                    # 검색 과정 로깅
                    print(f"\n=== 태그 검색 ===")
                    print(f"원본 태그: {to_tag}")
                    print(f"xbrl_data: {xbrl_data.keys()}")

                    print(f"검색 태그: {search_tag}")
                    print(f"xbrl_data에 존재: {search_tag in xbrl_data}")
                    if search_tag in xbrl_data:
                        print(f"값 개수: {len(xbrl_data[search_tag])}")
                    
                    # XBRL 데이터에서 값 가져오기
                    xbrl_values = []
                    if search_tag in xbrl_data:
                        xbrl_values = xbrl_data[search_tag]
                    
                    # 자식 노드 추가
                    child_node = {
                        "concept": to_tag,
                        "order": order,
                        "data": []
                    }
                    
                    # XBRL 값들 추가
                    for value in xbrl_values:
                        data_point = {
                            "value": value.get("value", ""),
                            "display_value": value.get("display_value", ""),
                            "context": value.get("context", ""),
                            "unit": value.get("unit", ""),
                            "decimals": value.get("decimals", "0"),
                            "raw_value": value.get("raw_value", ""),
                            "source": "xbrl",
                            "attributes": {
                                "contextref": value.get("contextref", ""),
                                "id": value.get("id", "")
                            }
                        }
                        child_node["data"].append(data_point)
                    
                    current_section[from_tag].append(child_node)
        
        # JSON 파일로 저장
        output_file = os.path.join(self.data_dir, 'hierarchy.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy, f, indent=2, ensure_ascii=False)
        
        return hierarchy

    def get_section_name(self, role):
        """role URI에서 섹션 이름 추출"""
        # 기업별 커스텀 role 패턴
        company_patterns = [
            'apple.com/role/',          # 애플
            'microsoft.com/role/',      # 마이크로소프트
            'amazon.com/role/',         # 아마존
            'google.com/role/',         # 구글
            'meta.com/role/',           # 메타
            'nvidia.com/role/',         # 엔비디아
            '/role/'                    # 기타 기업 (일반적인 패턴)
        ]
        
        # role에서 섹션 이름 추출
        section = None
        for pattern in company_patterns:
            if pattern in role.lower():
                section = role.split(pattern)[-1]
                break
        
        if section:
            # Details, Information, Disclosure 등의 접미사 제거
            suffixes = ['Details', 'Information', 'Disclosure', 'Table']
            for suffix in suffixes:
                if section.endswith(suffix):
                    section = section[:-len(suffix)]
            
            # CamelCase를 공백으로 분리
            import re
            
            # 1. 대문자로 시작하는 단어들 분리
            words = re.findall('[A-Z][^A-Z]*|[a-z]+', section)
            
            # 2. 숫자와 문자 사이에 공백 추가
            processed_words = []
            for word in words:
                sub_words = re.findall('[0-9]+|[^0-9]+', word)
                processed_words.extend(sub_words)
            
            # 3. 특수문자 제거 및 공백으로 변환
            cleaned_words = [re.sub('[^a-zA-Z0-9]', ' ', word).strip() for word in processed_words]
            
            # 4. 빈 문자열 제거 및 단어 결합
            final_words = [word for word in cleaned_words if word]
            return ' '.join(final_words)
            
        return 'Other'

    def remove_namespace(self, tag):
        
        # 1. 콜론(:)으로 분리된 네임스페이스 처리
        if ':' in tag:
            tag = tag.split(':')[-1]
        
        # 2. 언더스코어(_)로 분리된 네임스페이스 처리
        if '_' in tag:
            parts = tag.split('_', 1)  # 최대 1번만 분리
            if parts[0].lower() in [
                'us-gaap', 'usgaap', 'us', 'gaap',  # GAAP 관련
                'dei', 'aapl', 'ecd', 'srt',        # 기본 패턴
                'msft', 'amzn', 'googl', 'meta',    # 기업 관련
                'ifrs', 'country', 'currency',       # 국제 표준
                'invest', 'risk', 'ref'             # 기타
            ]:
                return parts[1]
        
        # 3. 하이픈(-)으로 분리된 네임스페이스 처리
        if '-' in tag:
            parts = tag.split('-', 1)
            if parts[0].lower() in ['us', 'gaap']:
                return tag.replace('us-gaap_', '')
        
        return tag

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

