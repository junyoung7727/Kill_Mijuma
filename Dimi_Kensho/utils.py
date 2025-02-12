import requests
import json
import re
from bs4 import BeautifulSoup
from collections import defaultdict
import traceback
import os
from datetime import datetime

def get_cik_from_ticker(ticker):
    """
    주식 티커 심볼로 CIK 번호를 찾는 함수
    
    Args:
        ticker (str): 주식 티커 심볼 (예: 'AAPL', 'MSFT')
        
    Returns:
        str: CIK 번호 (10자리 문자열)
        None: 티커를 찾을 수 없는 경우
    """
    # SEC의 회사 검색 API URL
    url = "https://www.sec.gov/files/company_tickers.json"
    
    try:
        # SEC 요구사항: User-Agent 헤더 필수
        headers = {
            'User-Agent': 'junghae2017@gmail.com'
        }
        
        # API 호출
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # HTTP 에러 체크
        
        # JSON 데이터 파싱
        data = response.json()
        
        # 티커로 CIK 검색
        ticker = ticker.upper()  # 대문자로 변환
        for entry in data.values():
            if entry['ticker'] == ticker:
                # CIK를 10자리 문자열로 변환 (앞에 0 채우기)
                cik = str(entry['cik_str']).zfill(10)
                return cik
        
        print(f"Error: 티커 '{ticker}'에 대한 CIK를 찾을 수 없습니다.")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error: SEC API 호출 중 오류 발생: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: JSON 파싱 중 오류 발생: {e}")
        return None
    except Exception as e:
        print(f"Error: 예상치 못한 오류 발생: {e}")
        return None

def extract_context_dimensions(soup):
    """
    XBRL BeautifulSoup 객체에서 context ID별 축 정보를 추출
    
    Args:
        soup: BeautifulSoup 객체
    Returns:
        dict: context ID를 키로 하는 축 정보 딕셔너리
    """
    context_dimensions = {}
    
    # 시작일과 종료일 찾기
    start_date_tag = soup.find('StartDate')
    end_date_tag = soup.find('EndDate')
    
    report_period = {
        'StartDate': start_date_tag.text if start_date_tag else None,
        'EndDate': end_date_tag.text if end_date_tag else None
    }
    
    print("\n=== 보고서 기간 ===")
    print(f"시작일: {report_period['StartDate']}")
    print(f"종료일: {report_period['EndDate']}")
    
    # context별 축 정보 추출
    for context in soup.find_all('context'):
        context_id = context['id']
        dimensions = []
        
        # 기간 정보 추출
        period = context.find('period')
        period_info = {}
        if period:
            instant = period.find('instant')
            if instant and instant.text:
                period_info = {
                    'type': 'instant',
                    'date': instant.text
                }
            else:
                start_date = period.find('StartDate')
                end_date = period.find('EndDate')
                if start_date and end_date:
                    period_info = {
                        'type': 'duration',
                        'StartDate': start_date.text,
                        'EndDate': end_date.text
                    }
        
        # 축 정보 추출
        segment = context.find('segment')
        if segment:
            for member in segment.find_all('xbrldi:explicitMember'):
                dimensions.append({
                    'axis': member['dimension'],
                    'member': member.text.strip()
                })
        
        context_dimensions[context_id] = {
            'period': period_info,
            'dimensions': dimensions
        }
    
    return context_dimensions, report_period

def extract_dates_from_def(def_url, headers):
    """
    def.xml 파일에서 날짜 정보만 추출
    
    Args:
        def_url (str): def.xml 파일의 URL
        headers (dict): 요청 헤더
    Returns:
        dict: instant와 duration 날짜 정보
    """
    try:
        response = requests.get(def_url, headers=headers)
        response.raise_for_status()
        def_soup = BeautifulSoup(response.content, 'xml')
        
        dates = {
            'instant': set(),
            'duration': []
        }
        
        # definitionLink 요소에서 날짜 정보 찾기
        for def_link in def_soup.find_all('definitionLink'):
            role = def_link.get('xlink:role', '')
            
            # instant 날짜 찾기
            if 'AsOf' in role:
                date_match = re.search(r'AsOf(\d{8})', role)
                if date_match:
                    date = date_match.group(1)
                    formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
                    dates['instant'].add(formatted_date)
            
            # duration 날짜 찾기
            if '_To_' in role:
                date_match = re.search(r'(\d{8})_To_(\d{8})', role)
                if date_match:
                    start_date = date_match.group(1)
                    end_date = date_match.group(2)
                    formatted_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
                    formatted_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
                    dates['duration'].append((formatted_start, formatted_end))
        
        # set을 list로 변환
        dates['instant'] = sorted(list(dates['instant']))
        # duration 날짜 정렬
        dates['duration'] = sorted(list(set(dates['duration'])))
        
        return dates
        
    except Exception as e:
        print(f"Error: def.xml 파일에서 날짜 추출 중 오류 발생 - {str(e)}")
        return None

def test_axis_extraction(soup):
    """
    XBRL 문서에서 축 정보만 추출하여 출력하는 테스트 함수
    
    Args:
        soup: BeautifulSoup 객체
    """
    print("\n=== 축(Axis) 정보 테스트 ===")
    
    # 모든 축과 멤버 값을 저장할 딕셔너리
    all_axes = defaultdict(set)
    
    # 각 context별 축 정보 수집
    for context in soup.find_all('context'):
        context_id = context['id']
        segment = context.find('segment')
        
        if segment:
            dimensions = []
            for member in segment.find_all('xbrldi:explicitMember'):
                axis = member['dimension']
                member_value = member.text.strip()
                
                # 네임스페이스 제거
                if ':' in axis:
                    axis = axis.split(':')[1]
                
                # 전체 축 목록에 추가
                all_axes[axis].add(member_value)
                dimensions.append((axis, member_value))
            
            if dimensions:
                print(f"\nContext ID: {context_id}")
                for axis, member in dimensions:
                    print(f"  - {axis}: {member}")
    
    # 전체 축 정보 요약
    print("\n=== 전체 축 정보 요약 ===")
    for axis, members in sorted(all_axes.items()):
        print(f"\n{axis}:")
        for member in sorted(members):
            print(f"  - {member}")

def extract_hierarchy_dimensions(def_soup):
    """
    def.xml 파일에서 계층 구조의 축 정보를 추출
    
    Args:
        def_soup: def.xml의 BeautifulSoup 객체
    Returns:
        dict: 축별 계층 구조 정보
    """
    hierarchy_dimensions = defaultdict(lambda: {
        'axis': None,
        'members': [],
        'explicit_members': set(),
        'children': []
    })
    
    # 태그 매핑 정보 수집
    loc_map = {}
    for loc in def_soup.find_all('loc'):
        label = loc.get('xlink:label')
        href = loc.get('xlink:href', '')
        if '#' in href:
            tag = href.split('#')[1]
            loc_map[label] = tag
    
    # definitionLink 요소에서 계층 구조 찾기
    for def_link in def_soup.find_all('definitionLink'):
        role = def_link.get('xlink:role', '')
        
        # 축 정보 찾기
        for arc in def_link.find_all('definitionArc'):
            arcrole = arc.get('xlink:arcrole', '')
            from_label = arc.get('xlink:from')
            to_label = arc.get('xlink:to')
            
            if from_label in loc_map and to_label in loc_map:
                from_tag = loc_map[from_label]
                to_tag = loc_map[to_label]
                
                # 네임스페이스 처리
                if ':' in from_tag:
                    from_tag = from_tag.split(':')[1]
                if ':' in to_tag:
                    to_tag = to_tag.split(':')[1]
                
                # dimension-domain 관계 처리 (축과 멤버)
                if 'dimension-domain' in arcrole:
                    hierarchy_dimensions[from_tag]['axis'] = from_tag
                    hierarchy_dimensions[from_tag]['members'].append(to_tag)
                
                # domain-member 관계 처리 (멤버 계층)
                elif 'domain-member' in arcrole:
                    hierarchy_dimensions[from_tag]['children'].append(to_tag)
                    # Explicit Member 추가
                    if to_tag.endswith('Member'):
                        hierarchy_dimensions[from_tag]['explicit_members'].add(to_tag)
    
    # set을 list로 변환
    for dim in hierarchy_dimensions.values():
        dim['explicit_members'] = sorted(list(dim['explicit_members']))
    
    return dict(hierarchy_dimensions)

def test_hierarchy_dimensions(def_url, headers):
    """
    계층 구조 축 정보를 테스트하는 함수
    """
    try:
        response = requests.get(def_url, headers=headers)
        response.raise_for_status()
        def_soup = BeautifulSoup(response.content, 'xml')
        
        hierarchy = extract_hierarchy_dimensions(def_soup)
        
        print("\n=== 계층 구조 축 정보 ===")
        for parent, info in hierarchy.items():
            if info['axis']:  # 축 정보가 있는 경우
                print(f"\n축(Axis): {parent}")
                if info['members']:
                    print("멤버(Members):")
                    for member in info['members']:
                        print(f"  - {member}")
                if info['explicit_members']:
                    print("명시적 멤버(Explicit Members):")
                    for exp_member in info['explicit_members']:
                        print(f"  - {exp_member}")
                if info['children']:
                    print("하위 항목(Children):")
                    for child in info['children']:
                        print(f"  - {child}")
        
        return hierarchy
        
    except Exception as e:
        print(f"Error: 계층 구조 추출 중 오류 발생 - {str(e)}")
        traceback.print_exc()
        return None

def get_xbrl_xml_url(sec_report_url: str) -> str:
    """
    SEC 보고서 URL을 원본 XBRL XML 파일 URL로 변환합니다.
    
    예시:
    Input: https://www.sec.gov/ix?doc=/Archives/edgar/data/0001045810/000104581024000316/nvda-20241027.htm
    Output: https://www.sec.gov/Archives/edgar/data/0001045810/000104581024000316/nvda-20241027.xml
    """
    try:
        # ix?doc= 부분 제거
        if 'ix?doc=' in sec_report_url:
            base_url = sec_report_url.split('ix?doc=')[0] + sec_report_url.split('ix?doc=')[1]
        else:
            base_url = sec_report_url
        print(base_url)

        # .htm 확장자를 .xml로 변경
        if base_url.endswith('.htm'):
            xml_url = base_url[:-4] + '_htm.xml'
        elif base_url.endswith('.html'):
            xml_url = base_url[:-5] + '_html.xml'
        else:

            xml_url = base_url
            
        return xml_url
    except Exception as e:
        print(f"URL 변환 중 오류 발생: {str(e)}")
        return ""

def create_context_period_mapping(sec_report_url: str, data_dir: str, output_file: str = "context_data.json") -> dict:
    """
    SEC 보고서에서 각 컨텍스트 ID에 대한 정확한 기간 정보를 추출하여 JSON으로 저장합니다.
    
    생성되는 JSON 형식:
    {
        "c-121": {
            "type": "period",
            "start_date": "2022-09-25",
            "end_date": "2023-09-30"
        },
        "c-124": {
            "type": "instant",
            "date": "2023-09-30"
        }
    }
    """
    # URL을 XBRL XML 파일 URL로 변환
    xml_url = get_xbrl_xml_url(sec_report_url)
    if not xml_url:
        print("XML URL 생성 실패")
        return {}
        
    print(f"XML 파일 URL: {xml_url}")
    
    headers = {
        "User-Agent": "junghae2017@gmail.com"
    }

    try:
        response = requests.get(xml_url, headers=headers)
        if response.status_code != 200:
            print(f"문서 다운로드 실패: {response.status_code}")
            return {}

        soup = BeautifulSoup(response.content, "lxml")
        contexts = soup.find_all(lambda tag: tag.name and tag.name.lower().endswith('context'))
        
        context_periods = {}
        
        for ctx in contexts:
            ctx_id = ctx.get('id', '')
            # c-숫자 형식의 컨텍스트 ID만 처리
            if not re.match(r'^c-\d+$', ctx_id):
                continue
                
            period = ctx.find(lambda tag: tag.name and tag.name.lower().endswith('period'))
            if not period:
                continue
                
            # instant 타입 처리
            instant = period.find(lambda tag: tag.name and tag.name.lower().endswith('instant'))
            if instant:
                context_periods[ctx_id] = {
                    "type": "instant",
                    "date": instant.get_text().strip()
                }
                continue
                
            # duration 타입 처리 (period로 표시)
            start = period.find(lambda tag: tag.name and tag.name.lower().endswith('startdate'))
            end = period.find(lambda tag: tag.name and tag.name.lower().endswith('enddate'))
            if start and end:
                context_periods[ctx_id] = {
                    "type": "period",
                    "start_date": start.get_text().strip(),
                    "end_date": end.get_text().strip()
                }

        if not context_periods:
            print("경고: 추출된 컨텍스트가 없습니다. HTML 형식으로 다시 시도합니다.")
            # HTML 형식으로 다시 시도
            soup = BeautifulSoup(response.content, "lxml")
            contexts = soup.find_all(lambda tag: tag.get('id', '').startswith('c-'))
            
            for ctx in contexts:
                ctx_id = ctx.get('id', '')
                if not re.match(r'^c-\d+$', ctx_id):
                    continue
                    
                period = ctx.find(class_='period')
                if not period:
                    continue
                    
                # instant 타입 처리
                instant = period.find(class_='instant')
                if instant:
                    context_periods[ctx_id] = {
                        "type": "instant",
                        "date": instant.get_text().strip()
                    }
                    continue
                    
                # period 타입 처리
                start = period.find(class_='startDate')
                end = period.find(class_='endDate')
                if start and end:
                    context_periods[ctx_id] = {
                        "type": "period",
                        "start_date": start.get_text().strip(),
                        "end_date": end.get_text().strip()
                    }

        # 결과를 컨텍스트 ID 순서로 정렬
        sorted_contexts = dict(sorted(context_periods.items(), key=lambda x: int(x[0].split('-')[1])))
        
        # JSON 파일로 저장
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(sorted_contexts, f, ensure_ascii=False, indent=2)
            
        print(f"\n컨텍스트 기간 정보가 저장되었습니다: {output_path}")
        print(f"총 {len(sorted_contexts)}개의 컨텍스트 기간 정보가 추출되었습니다.")
        
        # 샘플 출력
        print("\n처음 5개 컨텍스트 기간 정보:")
        for i, (ctx_id, period_info) in enumerate(list(sorted_contexts.items())[:5]):
            if period_info["type"] == "instant":
                print(f"{ctx_id}: {period_info['date']}")
            else:
                print(f"{ctx_id}: {period_info['start_date']} ~ {period_info['end_date']}")
                
        return sorted_contexts

    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return {}

# 사용 예시
if __name__ == "__main__":
    test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN']
    
    print("\n=== CIK 검색 테스트 ===")
    for ticker in test_tickers:
        cik = get_cik_from_ticker(ticker)
        if cik:
            print(f"{ticker}: {cik}") 

    # 테스트용 URL (예: 애플의 최신 10-Q)
    url = "https://www.sec.gov/ix?doc=/Archives/edgar/data/0001045810/000104581024000316/nvda-20241027.htm"
    headers = {
        'User-Agent': 'junghae2017@gmail.com'
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            test_axis_extraction(soup)
        else:
            print(f"Error: XML 파일 접근 실패 (Status: {response.status_code})")
    except Exception as e:
        print(f"Error: 테스트 실행 중 오류 발생 - {str(e)}") 

    # 계층 구조 테스트
    # 예시 SEC 보고서 링크 (사용 환경에 맞게 변경)
    sec_url = "https://www.sec.gov/ix?doc=/Archives/edgar/data/0001045810/000104581024000316/nvda-20241027.htm"
    context_periods = create_context_period_mapping(
        sec_report_url=sec_url,
        data_dir="data"
    ) 