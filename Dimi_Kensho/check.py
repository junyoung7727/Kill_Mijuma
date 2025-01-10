import os
import xml.etree.ElementTree as ET
import urllib.request
import re

def remove_namespace(tag):
    """태그에서 네임스페이스 제거"""
    if ':' in tag:
        tag = tag.split(':')[-1]
    if '_' in tag:
        parts = tag.split('_')
        if len(parts) > 1 and parts[0].lower() in ['us', 'gaap', 'dei', 'aapl', 'ecd', 'srt']:
            tag = '_'.join(parts[1:])
    return tag

def check_xbrl_structure(cik, filing_date, ticker):
    """XBRL 데이터 구조 확인"""
    # SEC EDGAR URL 설정
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing_date}"
    
    # 날짜 추출 (예: 20231230)
    date = filing_date.split('-')[0][-8:]  # 마지막 8자리를 날짜로 사용
    
    # 파일명 패턴 (예: aapl-20231230_pre.xml)
    pre_url = f"{base_url}/{ticker.lower()}-{date}_pre.xml"
    htm_url = f"{base_url}/{ticker.lower()}-{date}.htm"
    
    print(f"\n=== CIK: {cik}, Filing Date: {filing_date}, Ticker: {ticker} ===")
    print(f"PRE URL: {pre_url}")
    print(f"HTM URL: {htm_url}")
    
    try:
        print("\n=== presentationLink의 태그 매핑 확인 ===")
        headers = {'User-Agent': 'junghae2017@gmail.com'}
        req = urllib.request.Request(pre_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            tree = ET.parse(response)
            root = tree.getroot()
            
            ns = {
                'link': 'http://www.xbrl.org/2003/linkbase',
                'xlink': 'http://www.w3.org/1999/xlink'
            }
            
            # 섹션 카운트
            section_count = 0
            
            for link in root.findall('.//link:presentationLink', ns):
                role = link.get('{http://www.w3.org/1999/xlink}role')
                section_name = get_section_name(role)
                if section_name != 'Other':
                    section_count += 1
                print(f"\n=== 섹션: {section_name} ===")
                print(f"원본 role: {role}")
                
                # 태그 매핑 샘플 출력 (처음 5개만)
                print("\n태그 매핑 샘플:")
                for loc in list(link.findall('.//link:loc', ns))[:5]:
                    label = loc.get('{http://www.w3.org/1999/xlink}label')
                    href = loc.get('{http://www.w3.org/1999/xlink}href')
                    original_tag = href.split('#')[-1]
                    clean_tag = remove_namespace(original_tag)
                    print(f"원본: {original_tag} -> 정제: {clean_tag}")
                
                print("-" * 50)
            
            print(f"\n총 섹션 수: {section_count}")
            print(f"'Other'가 아닌 섹션 수: {section_count}")
            
    except Exception as e:
        print(f"오류 발생: {e}")

def get_section_name(role):
    """role URI에서 섹션 이름 추출"""
    if 'apple.com/role/' in role:
        # 애플 커스텀 role 처리
        section = role.split('/role/')[-1]
        if 'Details' in section:
            # 상세 정보 섹션
            section = section[:-7]  # 'Details' 제거
            # CamelCase를 공백으로 분리
            words = re.findall('[A-Z][^A-Z]*|[a-z]+', section)
            return ' '.join(words)
            
    elif 'sec.gov/ecd/role/' in role:
        # SEC 표준 role 처리
        section = role.split('/role/')[-1]
        # CamelCase를 공백으로 분리
        return ' '.join(word.capitalize() for word in section.split())
        
    return 'Other'

if __name__ == "__main__":
    # 테스트할 기업들 (CIK, filing_date, ticker)
    companies = [
        ("320193", "000032019324000012", "AAPL"),    # 애플 (2023-12-30)
        ("789019", "000078901924000012", "MSFT"),    # 마이크로소프트
        ("1018724", "000101872424000012", "AMZN"),   # 아마존
    ]
    
    for cik, filing_date, ticker in companies:
        check_xbrl_structure(cik, filing_date, ticker)
