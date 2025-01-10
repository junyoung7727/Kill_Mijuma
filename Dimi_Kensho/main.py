import json
import os
from sec_fetcher import SECFetcher
from llm_translate import extract_all_tags, get_llm_translations, create_structured_json
from create_html import create_kr_html
from setup import setup_project_structure

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
    apple_cik = "320193"
    
    # 최신 10-Q URL 가져오기
    url = fetcher.get_latest_10q_url(apple_cik)
    if url:
        # URL에서 분기 정보 추출 (예: aapl-20240629.htm)
        filing_date = url.split('/')[-1].split('.')[0].split('-')[1]  # 20240629
        year = filing_date[:4]
        month = filing_date[4:6]
        
        print(f"\n=== Apple(AAPL)의 {year}년 {month}월 분기 보고서 ===")
        print(f"10-Q URL: {url}")
        
        # XBRL 데이터 가져오기
        xbrl_data = fetcher.get_xbrl_data(url)
        if xbrl_data:
            # 커스텀 태그 가져오기
            custom_tags = fetcher.get_custom_tags(url)
            
            # 데이터 통합
            integrated_data = fetcher.integrate_data()
            
            # 계층 구조 생성 (섹션 정보 포함)
            hierarchy = fetcher.create_hierarchy_json(xbrl_data, integrated_data)
            
            # context 정보가 포함된 새로운 hierarchy 생성
            hierarchy_with_context = fetcher.create_hierarchy_with_context(hierarchy)

            # 계층 구조 출력 (섹션별로)
            print("\n=== 섹션별 계층 구조 ===")
            for section, data in hierarchy.items():
                print(f"\n섹션: {section}")
                fetcher.print_hierarchy(data, xbrl_data)
            
            # 모든 태그 추출
            all_tags = extract_all_tags(hierarchy)
            
            # LLM 번역 가져오기
            translations = get_llm_translations(all_tags, data_dir)
            
            # 구조화된 JSON 생성
            structured_json = create_structured_json(translations, hierarchy, data_dir)
            
            # HTML 생성
            create_kr_html(data_dir)

if __name__ == "__main__":
    main()