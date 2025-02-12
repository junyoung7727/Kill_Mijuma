import json
import os
from sec_fetcher import SECFetcher
from create_html import create_html_report
from setup import setup_project_structure
from utils import get_cik_from_ticker
from financial_translator import FinancialTranslator
from utils import create_context_period_mapping


def ensure_data_directory():
    """데이터 디렉토리 생성"""
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return data_dir

def main():
    # 프로젝트 구조 설정
    setup_project_structure()
    
    # 데이터 디렉토리 확인
    data_dir = ensure_data_directory()
    
    # SEC Fetcher 초기화
    fetcher = SECFetcher('junghae2017@gmail.com', data_dir)
    
    # Apple의 CIK
    ticker = 'nvda'
    cik = get_cik_from_ticker(ticker.upper())
    
    # 최신 10-Q URL 가져오기
    url = fetcher.get_latest_10q_url(cik)

    # 컨텍스트 기간 매핑 생성
    create_context_period_mapping(url, data_dir)

    if url:
        # URL에서 분기 정보 추출 (예: aapl-20240629.htm)
        filing_date = url.split('/')[-1].split('.')[0].split('-')[1]  # 20240629
        year = filing_date[:4]
        month = filing_date[4:6]
        
        print(f"\n=== 의 {year}년 {month}월 분기 보고서 ===")
        print(f"10-Q URL: {url}")
        
        # XBRL 데이터 가져오기
        xbrl_data, soup = fetcher.get_xbrl_data(url)
        if xbrl_data and soup:
            # 커스텀 태그 가져오기
            custom_tags = fetcher.get_custom_tags(url)
            
            # 데이터 통합
            integrated_data = fetcher.integrate_data()
            
            # 계층 구조 생성 (섹션 정보 포함)
            hierarchy = fetcher.create_hierarchy_json(xbrl_data, integrated_data, soup, url)

            # # 계층 구조 출력 (섹션별로)
            # print("\n=== 섹션별 계층 구조 ===")
            # for section, data in hierarchy.items():
            #     print(f"\n섹션: {section}")
            #     fetcher.print_hierarchy(data, xbrl_data)
            
            # 모든 태그 추출
            translator = FinancialTranslator(data_dir)
            translator.translate_recent_statements()
            
            # HTML 생성
            create_html_report()

if __name__ == "__main__":
    main()