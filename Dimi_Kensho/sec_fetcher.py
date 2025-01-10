import requests
from bs4 import BeautifulSoup
import re
import traceback
import json
from collections import defaultdict
import os

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
                    url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{int(cik)}/{accession_number}/{primary_doc}"
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
            
            # 모든 태그 수집
            self.xbrl_data = defaultdict(list)
            
            # us-gaap: 태그 찾기
            for element in soup.find_all(lambda tag: isinstance(tag.name, str) and tag.name.startswith('us-gaap:')):
                tag_name = element.name.split(':')[1]  # 'us-gaap:Revenue' -> 'Revenue'
                context_ref = element.get('contextRef', '')
                unit_ref = element.get('unitRef', '')
                decimals = element.get('decimals', '0')
                value = element.text.strip()
                
                try:
                    if decimals and value:
                        numeric_value = float(value)
                        if decimals.startswith('-'):
                            # 음수 decimals는 스케일을 의미
                            scale = abs(int(decimals))
                            if scale == 6:  # 백만 단위
                                adjusted_value = numeric_value / 1_000_000  # 백만 단위로 변환
                                display_value = f"${adjusted_value:,.0f}M"
                            elif scale == 9:  # 십억 단위
                                adjusted_value = numeric_value / 1_000_000_000  # 십억 단위로 변환
                                display_value = f"${adjusted_value:,.0f}B"
                            else:
                                adjusted_value = numeric_value
                                display_value = f"${numeric_value:,.0f}"
                        else:
                            # 양수 decimals는 소수점 자리수를 의미
                            adjusted_value = numeric_value
                            display_value = f"${numeric_value:,.2f}"
                    else:
                        adjusted_value = value
                        display_value = value
                except ValueError:
                    adjusted_value = value
                    display_value = value
                
                self.xbrl_data[tag_name].append({
                    'value': adjusted_value,
                    'display_value': display_value,
                    'context': context_ref,
                    'unit': unit_ref,
                    'decimals': decimals,
                    'raw_value': value,
                    'source': 'xbrl',
                    'attributes': element.attrs
                })
            
            # 통계 출력
            num_tags = sum(1 for items in self.xbrl_data.values() 
                          for item in items 
                          if isinstance(item.get('value'), (int, float)))
            text_tags = sum(1 for items in self.xbrl_data.values() 
                           for item in items 
                           if isinstance(item.get('value'), str))
            
            print(f"\n=== XBRL 데이터 통계 ===")
            print(f"총 태그 수: {len(self.xbrl_data)}")
            print(f"숫자 데이터: {num_tags}")
            print(f"텍스트 데이터: {text_tags}")
            
            # 주요 재무 지표 출력
            important_tags = [
                'Revenue',
                'NetIncomeLoss',
                'Assets',
                'Liabilities',
                'StockholdersEquity'
            ]
            
            print("\n=== 주요 재무 지표 ===")
            for tag in important_tags:
                if tag in self.xbrl_data:
                    print(f"\n{tag}:")
                    for value in self.xbrl_data[tag]:
                        print(f"  Context: {value['context']}")
                        print(f"  Value: {value['display_value']}")
                        print("  ---")
            
            return self.xbrl_data
            
        except Exception as e:
            print(f"XBRL 데이터 가져오기 실패: {str(e)}")
            traceback.print_exc()
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

    def print_hierarchy(self, hierarchy, xbrl_data):
        """계층 구조 출력 (통합 데이터 사용)"""
        def print_node(node, depth=0):
            indent = "  " * depth
            
            if isinstance(node, dict):
                if 'concept' in node:
                    full_tag = node['concept']
                    tag_name = full_tag.split(':')[1]  # 네임스페이스 제거
                    
                    # 통합 객체에서 값 찾기
                    value = get_latest_value(tag_name)
                    
                    if value is not None:
                        print(f"{indent}- {full_tag}: {value}")
                    else:
                        print(f"{indent}- {full_tag}")
                
                for key, value in node.items():
                    if key not in ['concept', 'order', 'data']:
                        print(f"{indent}{key}:")
                        print_node(value, depth + 1)
            
            elif isinstance(node, list):
                sorted_nodes = sorted(node, key=lambda x: x.get('order', 0) if isinstance(x, dict) else 0)
                for item in sorted_nodes:
                    print_node(item, depth)
        
        def get_latest_value(tag_name):
            """태그에서 가장 최근 컨텍스트의 값을 찾음"""
            if tag_name in self.integrated_data:
                # 숫자 값을 가진 항목만 필터링
                numeric_items = [
                    item for item in self.integrated_data[tag_name]
                    if isinstance(item.get('value'), (int, float))
                ]
                
                if numeric_items:
                    # 컨텍스트 번호로 정렬하여 가장 최근 값 사용
                    sorted_items = sorted(
                        numeric_items,
                        key=lambda x: int(x['context'].split('-')[1]) 
                        if x.get('context', '').startswith('c-') 
                        else float('inf')
                    )
                    
                    item = sorted_items[0]
                    value = item['value']
                    unit = item.get('unit', '').lower()
                    return f"{value:,.0f} {unit}".strip()
            
            return None

        print("\n=== 계층 구조 출력 ===")
        for section_name, section_data in hierarchy.items():
            print(f"\n[{section_name}]")
            print_node(section_data)

    def create_hierarchy_json(self, xbrl_data, integrated_data):
        """XBRL 데이터에서 계층 구조 생성 및 데이터 채우기"""
        result = {}
        
        # XBRL 데이터에서 섹션과 태그 추출
        for tag, values in xbrl_data.items():
            if not values:  # 값이 없는 태그는 건너뛰기
                continue
            
            # 첫 번째 값의 컨텍스트 정보로 섹션 결정
            first_value = values[0]
            section = first_value.get('section', 'Other')  # 섹션 정보가 없으면 'Other'로
            
            # 섹션이 없으면 생성
            if section not in result:
                result[section] = {
                    "roots": [],
                    "tree": {}
                }
            
            # 태그 정보 추가
            tag_info = {
                "concept": tag,
                "order": len(result[section]["tree"]) + 1,  # 순서는 추가된 순서대로
                "data": integrated_data.get(tag.lower(), [])  # 통합 데이터에서 값 가져오기
            }
            
            # 태그를 트리에 추가
            parent = tag.split(':')[-1]  # 네임스페이스 제거
            if parent not in result[section]["tree"]:
                result[section]["tree"][parent] = []
                result[section]["roots"].append(parent)
            
            result[section]["tree"][parent].append(tag_info)
            
            if tag_info["data"]:
                print(f"\n찾은 데이터 - {tag}:")
                print(f"데이터 수: {len(tag_info['data'])}")
                print(f"첫 번째 항목: {tag_info['data'][0]}")
        
        # JSON 파일로 저장
        hierarchy_path = os.path.join(self.data_dir, 'hierarchy.json')
        with open(hierarchy_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        print(f"계층 구조가 저장되었습니다: {hierarchy_path}")
        return result

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


